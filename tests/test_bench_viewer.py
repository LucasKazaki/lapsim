"""Receipt gate, provenance and staging regressions for the actual web viewer."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to exercise the actual receipt validator")
def test_actual_receipt_validator_and_gate_counterexamples():
    # Run the same shipped JS module, rather than mirroring its decisions in Python.
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const api = require('./web/bench-data.js');
const demo = JSON.parse(fs.readFileSync('./web/examples/enme408-synthetic-replay.json','utf8'));
assert.equal(api.validateReceipt(demo),demo);
assert.deepEqual(api.summarize(demo),{cycles:18,allowed:9,held:9,recovering:5});
assert.deepEqual(api.eventIndices(demo),[0,1,4,5,6,7,8,9,11,12,13,14,15,16,17]);
const rejected = change => {
  const bad=structuredClone(demo);change(bad);assert.throws(()=>api.validateReceipt(bad));
};
rejected(x=>{x.schema='other'});
rejected(x=>{x.records[0].command_nm=[1,0,0,0]});
rejected(x=>{x.records[1].fault.next_state='inhibited'});
rejected(x=>{x.records[1].guard.status='inhibited'});
rejected(x=>{x.records[1].clock_fault='cycle_period_mismatch'});
rejected(x=>{x.records[1].command_nm=[6,5,5,5]});
rejected(x=>{x.records[1].command_nm=[-1,5,5,5]});
rejected(x=>{x.records[1].command_nm=[NaN,5,5,5]});
rejected(x=>{x.records[1].allocator.wheel_torque_nm=[1e308,1e308,1e308,1e308]});
rejected(x=>{x.records[0].restart_requested='false'});
rejected(x=>{x.records[0].sequence=1});
rejected(x=>{x.records[0].now_ms=Number.MAX_SAFE_INTEGER+1});
rejected(x=>{x.source_sha256['allocator.py']='forged'});
rejected(x=>{x.records=Array(4097).fill(x.records[0])});
// Metrics are recomputed from events, not trusted from a hand-edited summary.
demo.summary.allowed_cycles=999;
assert.equal(api.summarize(demo).allowed,9);
console.log('Actual validator: demo plus 15 malformed/gate counterexamples passed');
'''
    result = subprocess.run([shutil.which("node"), "-e", script], check=False, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_browser_build_stages_complete_bench_viewer(tmp_path):
    result = subprocess.run([sys.executable, "scripts/build_web.py", "--output-dir", str(tmp_path)],
                            check=False, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("bench.html", "bench.css", "bench.js", "bench-data.js", "examples/enme408-synthetic-replay.json",
                 "examples/enme408-native-c-replay.json"):
        assert (tmp_path / name).read_bytes() == (ROOT / "web" / name).read_bytes()
    manifest = json.loads((tmp_path / "assets/runtime-manifest.json").read_text())
    assert manifest["archiveBytes"] > 0


def test_standalone_viewer_embeds_the_actual_sources_and_fixture(tmp_path):
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("bench_export", ROOT / "scripts/export_bench_viewer.py")
    exporter = module_from_spec(spec)
    spec.loader.exec_module(exporter)
    output = tmp_path / "review.html"
    exporter.export(output)
    page = output.read_text(encoding="utf-8")
    assert '<script src=' not in page
    assert '<link rel="stylesheet"' not in page
    assert 'id="embedded-replay"' in page
    assert (ROOT / "web/bench.js").read_text(encoding="utf-8") in page
    assert (ROOT / "web/bench-data.js").read_text(encoding="utf-8") in page
    assert page.index('id="embedded-replay"') < page.index("(() => {")
    with pytest.raises(ValueError):
        exporter.export(ROOT / "web/bench.html")


def _exporter():
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("bench_export_custom", ROOT / "scripts/export_bench_viewer.py")
    exporter = module_from_spec(spec)
    spec.loader.exec_module(exporter)
    return exporter


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js exercises the shipped validator")
def test_actual_native_c_fixture_passes_shipped_viewer():
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),api=require('./web/bench-data.js');
const x=JSON.parse(fs.readFileSync('./web/examples/enme408-native-c-replay.json','utf8'));
assert.equal(api.validateReceipt(x),x);
assert.deepEqual(api.summarize(x),{cycles:18,allowed:9,held:9,recovering:5});
assert.ok(x.label.startsWith('Native C replay: '));
assert.ok(x.provenance.includes('Compiled C host replay'));
assert.equal(x.native_execution.engine,'compiled C host; five owners');
assert.match(x.native_execution.run_sha256,/^[a-f0-9]{64}$/);
assert.equal(x.native_execution.repeat_agreement,true);
assert.ok(x.records.some(r=>r.command_allowed&&r.command_nm.some(v=>v>0)));
const bad=structuredClone(x);bad.records[0].command_nm[0]=1;
assert.throws(()=>api.validateReceipt(bad));
'''
    result = subprocess.run([shutil.which("node"), "-e", script], check=False, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_custom_non18_export_is_escaped_and_preserves_input(tmp_path):
    import re
    exporter = _exporter()
    data = json.loads((ROOT / "web/examples/enme408-synthetic-replay.json").read_bytes())
    data["records"] = data["records"][:3]
    data["label"] = "Native C replay: custom three cycles"
    data["provenance"] = '</script><script>throw new Error("data only")</script>\U0001f600'
    receipt, output = tmp_path / "custom.json", tmp_path / "review.html"
    original = json.dumps(data, ensure_ascii=True).encode()
    receipt.write_bytes(original)
    exporter.export(output, receipt)
    page = output.read_text(encoding="utf-8")
    embedded = re.search(r'id="embedded-replay">(.*?)</script>', page, re.DOTALL).group(1)
    assert "<" not in embedded
    assert json.loads(embedded) == data
    assert receipt.read_bytes() == original
    assert "Load embedded replay" in page
    assert "accept(embedded.textContent,'Embedded replay')" in page
    assert (ROOT / "web/bench-data.js").read_text(encoding="utf-8") in page
    with pytest.raises(ValueError):
        exporter.export(receipt, receipt)
    assert receipt.read_bytes() == original


def test_custom_receipt_hardlink_alias_cannot_be_overwritten(tmp_path):
    import os
    receipt, output = tmp_path / "receipt.json", tmp_path / "alias.html"
    original = (ROOT / "web/examples/enme408-synthetic-replay.json").read_bytes()
    receipt.write_bytes(original)
    os.link(receipt, output)
    with pytest.raises(ValueError):
        _exporter().export(output, receipt)
    assert receipt.read_bytes() == original


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'['*2000+b'0'+b']'*2000])
def test_custom_malformed_receipt_has_no_output(tmp_path, raw):
    receipt, output = tmp_path / "bad.json", tmp_path / "review.html"
    receipt.write_bytes(raw)
    with pytest.raises((ValueError, RecursionError)):
        _exporter().export(output, receipt)
    assert not output.exists()
