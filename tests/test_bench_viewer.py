"""Receipt gate, provenance and staging regressions for the actual web viewer."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

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
    result = subprocess.run([shutil.which("node"), "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_browser_build_stages_complete_bench_viewer(tmp_path):
    result = subprocess.run([sys.executable, "scripts/build_web.py", "--output-dir", str(tmp_path)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("bench.html", "bench.css", "bench.js", "bench-data.js", "examples/enme408-synthetic-replay.json"):
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
