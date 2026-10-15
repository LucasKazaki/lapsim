"""Export the exact bench viewer and synthetic fixture as a standalone HTML file.

This file works without a server or Python installation. It displays evidence;
the controller itself must still be reproduced with its original Python source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def export(output: Path) -> None:
    web = ROOT / "web"
    page = (web / "bench.html").read_text(encoding="utf-8")
    css = (web / "bench.css").read_text(encoding="utf-8")
    page = page.replace('<link rel="stylesheet" href="bench.css">', f"<style>{css}</style>")
    page = re.sub(r'  <script src="bench(?:-data)?\.js(?:\?[^\"]*)?" defer></script>\n', "", page)
    scripts = "\n".join((web / name).read_text(encoding="utf-8") for name in ("bench-data.js", "bench.js"))
    fixture = json.loads((web / "examples/enme408-synthetic-replay.json").read_text(encoding="utf-8"))
    embedded = json.dumps(fixture, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    content = f'<script type="application/json" id="embedded-replay">{embedded}</script>\n<script>{scripts}</script>\n'
    page = page.replace("</body>", content + "</body>")
    page = page.replace('href="index.html"', 'href="https://lapsim-team-lab.kazagpt.chatgpt.site/"')
    page = page.replace('href="map/index.html"', 'href="https://lapsim-team-lab.kazagpt.chatgpt.site/map/index.html"')
    page = page.replace('href="bench.html"', 'href="#review"')
    sources = [path for path in web.rglob("*") if path.is_file()] + [Path(__file__)]
    if any(output.resolve() == source.resolve() or (output.exists() and output.samefile(source))
           for source in sources):
        raise ValueError("choose an output outside the viewer's source files")
    output.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args().output)
