"""JUnit aggregation preserves failures and rejects hostile XML declarations."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

SPEC = importlib.util.spec_from_file_location(
    "lapsim_check_all",
    Path(__file__).resolve().parents[1] / "scripts/check_all.py",
)
assert SPEC is not None and SPEC.loader is not None
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)


def test_aggregate_preserves_counts_and_failures(tmp_path):
    report = tmp_path / "module.xml"
    report.write_text(
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="1" time="2"><testcase name="failing"><failure>failure evidence</failure></testcase></testsuite></testsuites>'
    )
    destination = tmp_path / "aggregate.xml"
    totals = CHECKS.merge_reports([report], destination)
    assert totals == {"tests": 3, "failures": 1, "errors": 0, "skipped": 1}
    assert "failure evidence" in destination.read_text()


def test_xml_doctype_and_entities_are_rejected(tmp_path):
    report = tmp_path / "untrusted.xml"
    report.write_text(
        '<!DOCTYPE testsuites [<!ENTITY payload "expanded">]><testsuites><testsuite name="&payload;"/></testsuites>'
    )
    with pytest.raises(DefusedXmlException):
        CHECKS.merge_reports([report], tmp_path / "aggregate.xml")


def test_oversized_report_is_rejected_before_parsing(tmp_path):
    report = tmp_path / "oversized.xml"
    with report.open("wb") as output:
        output.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="16 MiB"):
        CHECKS.merge_reports([report], tmp_path / "aggregate.xml")


@pytest.mark.parametrize("explicit", (False, True))
@pytest.mark.parametrize("failed", (False, True))
def test_main_default_or_explicit_output_preserves_real_aggregation(
    tmp_path, monkeypatch, explicit, failed
):
    """Only module execution is stubbed; the normal aggregate writer remains real."""
    root = tmp_path / "source checkout"
    (root / "tests").mkdir(parents=True)
    for name in ("test_alpha.py", "test_beta.py"):
        (root / "tests" / name).write_text("# Discovered, never executed.\n")
    output = tmp_path / "requested reports" if explicit else root / "work"
    argv = ["check_all.py"]
    if explicit:
        argv.extend(["--output-dir", str(output)])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(CHECKS, "__file__", str(root / "scripts/check_all.py"))
    monkeypatch.setattr(
        CHECKS,
        "sys",
        SimpleNamespace(**{**vars(sys), "platform": "posix", "argv": argv}),
    )
    calls = []

    def module_report(path, source, reports, environment):
        calls.append((path.name, source, reports))
        assert reports.is_dir()
        assert all(
            environment[name] == "1"
            for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        )
        if path.name == "test_alpha.py":
            xml = (
                '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="1" time="1.5">'
                '<testcase name="alpha"/><testcase name="explicit skipped"><skipped/></testcase>'
                "</testsuite></testsuites>"
            )
        else:
            failure = "<failure>measured beta failure</failure>" if failed else ""
            xml = (
                f'<testsuites><testsuite tests="1" failures="{int(failed)}" errors="0" skipped="0" time="0.5">'
                f'<testcase name="beta">{failure}</testcase></testsuite></testsuites>'
            )
        (reports / (path.stem + ".xml")).write_text(xml, encoding="utf-8")
        return path.name == "test_beta.py" and failed

    monkeypatch.setattr(CHECKS, "run_module", module_report)
    assert CHECKS.main() == int(failed)
    assert calls == [
        ("test_alpha.py", root, output / "test-modules"),
        ("test_beta.py", root, output / "test-modules"),
    ]
    report = output / "test-results.xml"
    aggregate = SafeET.parse(
        report, forbid_dtd=True, forbid_entities=True, forbid_external=True
    ).getroot()
    assert {name: int(aggregate.get(name)) for name in ("tests", "failures", "errors", "skipped")} == {
        "tests": 3,
        "failures": int(failed),
        "errors": 0,
        "skipped": 1,
    }
    assert float(aggregate.get("time")) == 2.0
    assert [case.get("name") for case in aggregate.iter("testcase")] == [
        "alpha",
        "explicit skipped",
        "beta",
    ]
    assert len(list(aggregate.iter("failure"))) == int(failed)
    assert len(list(aggregate.iter("skipped"))) == 1
    if explicit:
        assert not (root / "work/test-results.xml").exists()
