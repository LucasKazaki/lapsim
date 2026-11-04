"""Source-file audit regressions; no simulator imports, processes or physics."""
from hashlib import sha256
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lite_readiness", ROOT / "scripts/check_lite_readiness.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class LiteSourceReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "research/light"
        (self.archive / "awd-standing-v15").mkdir(parents=True)
        self.source = self.archive / "sample.py"
        self.source.write_bytes(b"# archived source\n")
        self.manifest = {"schema": "lapsim.public-light-archival-source-manifest.v1",
                         "source_files": 1, "status": "NOT_RUNNABLE_NOT_QUALIFIED",
                         "source_entries": [{"path": "research/light/sample.py",
                                             "bytes": self.source.stat().st_size,
                                             "sha256": sha256(self.source.read_bytes()).hexdigest()}]}
        self.save_manifest()
        (self.archive / "STATUS.json").write_text(json.dumps({"publication_role": "archive"}), encoding="utf-8")
        self.registry = self.archive / "awd-standing-v15/registry-core.json"
        self.registry.write_text(json.dumps({"policies": [
            {"id": str(i), "native_qualification": "UNRUN", "campaign_eligible": False}
            for i in range(7)]}), encoding="utf-8")

    def save_manifest(self):
        (self.archive / "SOURCE_MANIFEST.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_intact_archive_remains_blocked_without_runtime_authority(self):
        report = AUDIT.audit(self.root)
        self.assertEqual(report["archive_integrity"], "passed")
        self.assertEqual(report["files_matched"], 1)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["runtime_checks_executed"])
        self.assertFalse(report["execution_authority"])

    def test_windows_line_endings_cannot_be_silently_normalized(self):
        self.source.write_bytes(b"# archived source\r\n")
        report = AUDIT.audit(self.root)
        self.assertEqual(report["archive_integrity"], "failed")
        self.assertFalse(report["files"][0]["matches"])

    def test_escaping_manifest_path_is_rejected(self):
        self.manifest["source_entries"][0]["path"] = "research/light/../../outside.py"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "inside research/light"):
            AUDIT.audit(self.root)

    def test_duplicate_manifest_path_is_rejected(self):
        self.manifest["source_entries"] *= 2
        self.manifest["source_files"] = 2
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "duplicate manifest path"):
            AUDIT.audit(self.root)

    def test_local_qualified_flags_do_not_grant_readiness(self):
        value = json.loads(self.registry.read_text(encoding="utf-8"))
        for policy in value["policies"]:
            policy.update(native_qualification="PASSED", campaign_eligible=True)
        self.registry.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(AUDIT.audit(self.root)["status"], "blocked")

    def test_report_never_overwrites_existing_evidence(self):
        report = self.root / "report.json"
        report.write_text("old evidence", encoding="utf-8")
        with patch.object(AUDIT, "audit", return_value={"status": "blocked"}), redirect_stderr(io.StringIO()):
            self.assertEqual(AUDIT.main(["--output", str(report)]), 1)
        self.assertEqual(report.read_text(encoding="utf-8"), "old evidence")

    def test_saved_report_and_stdout_agree_and_return_blocked(self):
        report = self.root / "work/report.json"
        expected = AUDIT.audit(self.root)
        stdout = io.StringIO()
        with patch.object(AUDIT, "audit", return_value=expected), redirect_stdout(stdout):
            self.assertEqual(AUDIT.main(["--output", str(report)]), 2)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")), expected)
        self.assertEqual(json.loads(stdout.getvalue()), expected)

    def test_malformed_metadata_fails_without_traceback(self):
        (self.archive / "STATUS.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON objects"):
            AUDIT.audit(self.root)


if __name__ == "__main__":
    unittest.main()
