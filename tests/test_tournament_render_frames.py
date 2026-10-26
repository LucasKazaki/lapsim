"""Exercise production frame logic without a font, encoder or raster dependency."""

import ast
import bisect
from copy import deepcopy
import json
import math
from pathlib import Path
import textwrap
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CaptureDraw:
    def __init__(self):
        self.texts = []

    def text(self, position, value, **kwargs):
        self.texts.append(value)

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class TournamentRenderFrameTests(unittest.TestCase):
    def setUp(self):
        source = ast.parse(
            (ROOT / "scripts/render_tournament_review.py").read_text(encoding="utf-8")
        )
        functions = ast.Module(
            body=[
                node
                for node in source.body
                if isinstance(node, ast.FunctionDef)
                and node.name in {"sample", "frame"}
            ],
            type_ignores=[],
        )
        self.draw = CaptureDraw()
        image = object()
        draw = self.draw

        class Image:
            @staticmethod
            def new(*args):
                return image

        class ImageDraw:
            @staticmethod
            def Draw(*args):
                return draw

        self.data = json.loads(
            (ROOT / "web/tournament-review/data.json").read_text(encoding="utf-8")
        )
        self.context: dict[str, Any] = {
            "Image": Image,
            "ImageDraw": ImageDraw,
            "W": 960,
            "H": 540,
            "fonts": dict.fromkeys([11, 12, 13, 15, 17, 20, 26, 30]),
            "colors": ["#75ddff", "#ffb968"],
            "math": math,
            "bisect": bisect,
            "textwrap": textwrap,
            "labels": {
                "coverage": "Fixture coverage",
                "evidence": "Fixture evidence",
                "source": "Fixture source",
            },
            "groups": self.data["groups"],
        }
        exec(compile(functions, "production-render-functions", "exec"), self.context)

    def render(self, group):
        self.context["times"] = {
            r["id"]: [s[0] for s in r["samples"]] for r in group["runs"]
        }
        self.draw.texts.clear()
        self.context["frame"](group, 1, 0)
        return "\n".join(self.draw.texts)

    def test_first_lap_failure_is_failed_at_termination(self):
        group = deepcopy(self.data["groups"][0])
        failed = group["runs"][0]
        failed.update(
            id="early-failure",
            accepted=False,
            status="failed",
            completed_laps=0,
            laps=[],
        )
        rendered = self.render(group)
        self.assertIn("FAILED", rendered)
        self.assertIn("lap 0/10", rendered)
        self.assertNotIn("early-failure  * FASTEST", rendered)

    def test_all_ineligible_chapter_has_no_winner_and_other_chapter_renders(self):
        group = deepcopy(self.data["groups"][0])
        for run in group["runs"]:
            run.update(accepted=False, status="failed", completed_laps=0, laps=[])
        rendered = self.render(group)
        self.assertIn("No eligible completed run; no winner selected", rendered)
        self.assertNotIn("* FASTEST", rendered)
        self.assertIn("Fastest ", self.render(self.data["groups"][2]))

    def test_completed_excluded_run_is_labeled_excluded(self):
        group = deepcopy(self.data["groups"][0])
        group["runs"][0]["selection_eligible"] = False
        self.assertIn("FINISHED / EXCLUDED", self.render(group))

    def test_hud_uses_recorded_target_laps(self):
        group = deepcopy(self.data["groups"][0])
        for run in group["runs"]:
            run.update(target_laps=1, completed_laps=1, laps=run["laps"][:1])
        rendered = self.render(group)
        self.assertIn("lap 1/1", rendered)
        self.assertNotIn("/10", rendered)


if __name__ == "__main__":
    unittest.main()
