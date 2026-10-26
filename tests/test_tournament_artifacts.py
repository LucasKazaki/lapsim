"""Artifact export fails closed and refreshed evidence cannot inherit old labels."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tournament_artifact_builder", ROOT / "scripts/build_tournament_review.py"
)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class TournamentArtifactTests(unittest.TestCase):
    def test_missing_indexed_viewer_preserves_previous_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "output"
            output.mkdir()
            previous = output / "data.json"
            previous.write_text("previous valid export", encoding="utf-8")
            (root / "review-index.json").write_text(
                json.dumps(
                    {
                        "cases": [{"id": "missing-winner"}],
                        "final_selection": {"development": {"excluded": []}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                FileNotFoundError, "missing-winner.viewer.json"
            ):
                BUILDER.build(root, output, "abcdef012345", "123456789abc")
            self.assertEqual(
                previous.read_text(encoding="utf-8"), "previous valid export"
            )
            self.assertFalse((output / "data.js").exists())

    def test_refreshed_provenance_uses_input_date_and_identities(self):
        data = {
            "schema": "lapsim.static-tournament-review.v1",
            "acceptance_commit": "abcdef0123456789",
            "numerical_checkpoint": "123456789abcdef0",
            "evidence_utc": "2027-02-03T10:15:00+01:00",
            "coverage": "Refreshed snapshot: two indexed records.",
        }
        labels = BUILDER.provenance_labels(data)
        self.assertEqual(labels["evidence"], "03 Feb 2027 | evidence 09:15 UTC")
        self.assertEqual(labels["source"], "Source abcdef0 / numerical 1234567")
        self.assertEqual(labels["coverage"], data["coverage"])
        renderer = (ROOT / "scripts/render_tournament_review.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Source 4e1eeaf", renderer)
        self.assertNotIn("26 Oct 2026 | evidence 18:15", renderer)
        self.assertIn('labels["source"]', renderer)
        self.assertIn('labels["evidence"]', renderer)

    def test_unversioned_provenance_is_rejected(self):
        for metadata in (
            {},
            {
                "schema": "lapsim.static-tournament-review.v1",
                "acceptance_commit": "unknown",
            },
        ):
            with self.assertRaises(ValueError):
                BUILDER.provenance_labels(metadata)

    def test_policy_origins_use_recorded_parents_and_heldout_mapping(self):
        index = {
            "generation": {
                "ancestry": {
                    "seed": 4082610,
                    "parents": ["elite-a", "elite-b", "elite-c"],
                    "parents_used": ["elite-a", "elite-c"],
                },
                "cases": ["immigrant-tech"],
            },
            "final_selection": {"heldout": [{"id": "heldout-1", "parent": "elite-c"}]},
        }

        def origin(identity, case_id="development"):
            return BUILDER.policy_origin(
                {"id": case_id, "profile": {"profile_id": identity}}, index
            )

        self.assertEqual(
            origin("r11-structured-offspring")["parents_used"], ["elite-a", "elite-c"]
        )
        self.assertNotIn("elite-b", origin("r11-structured-offspring")["label"])
        self.assertEqual(origin("r11-sample-4082603-2")["kind"], "seeded_sample")
        self.assertEqual(
            origin("r11-sample-4082611-0", "immigrant-tech")["kind"], "immigrant"
        )
        self.assertEqual(origin("unknown", "heldout-1")["parent"], "elite-c")
        self.assertEqual(
            origin("synthetic-four-awd-experimental")["kind"], "recorded_baseline"
        )
        self.assertEqual(origin("unknown")["kind"], "unavailable")


if __name__ == "__main__":
    unittest.main()
