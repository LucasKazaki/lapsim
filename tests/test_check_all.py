"""JUnit aggregation preserves failures and rejects hostile XML declarations."""

import importlib.util
from pathlib import Path

from defusedxml.common import DefusedXmlException
import pytest

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
