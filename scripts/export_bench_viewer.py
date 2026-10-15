"""Export the exact bench viewer and a supplied/default replay as standalone HTML.

This file works without a server or Python installation. It displays evidence;
the controller itself must be reproduced with its matching recorded source.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export(output: Path, receipt: Path | None = None) -> None:
    web = ROOT / "web"
    page = (web / "bench.html").read_text(encoding="utf-8")
    css = (web / "bench.css").read_text(encoding="utf-8")
    page = page.replace('<link rel="stylesheet" href="bench.css">', f"<style>{css}</style>")
    page = re.sub(r'  <script src="bench(?:-data)?\.js(?:\?[^\"]*)?" defer></script>\n', "", page)
    scripts = "\n".join((web / name).read_text(encoding="utf-8") for name in ("bench-data.js", "bench.js"))
    receipt = receipt or web / "examples/enme408-synthetic-replay.json"
    with receipt.open("rb") as stream:
        raw = stream.read(20_000_001)
    if len(raw) > 20_000_000:
        raise ValueError("receipt exceeds the viewer's 20 MB loader limit")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    fixture = json.loads(raw, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
    embedded = json.dumps(fixture, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    if len(embedded.encode("utf-8")) > 20_000_000:
        raise ValueError("encoded receipt exceeds the viewer's 20 MB loader limit")
    content = f'<script type="application/json" id="embedded-replay">{embedded}</script>\n<script>{scripts}</script>\n'
    page = page.replace("</body>", content + "</body>")
    page = page.replace('href="index.html"', 'href="https://lapsim-team-lab.kazagpt.chatgpt.site/"')
    page = page.replace('href="map/index.html"', 'href="https://lapsim-team-lab.kazagpt.chatgpt.site/map/index.html"')
    page = page.replace('href="bench.html"', 'href="#review"')
    sources = [path for path in web.rglob("*") if path.is_file()] + [Path(__file__), receipt]
    if any(output.resolve() == source.resolve() or (output.exists() and output.samefile(source))
           for source in sources):
        raise ValueError("choose an output outside the viewer's source files")
    output.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, help="embed this replay instead of the original synthetic example")
    args = parser.parse_args()
    try:
        export(args.output, args.receipt)
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        parser.exit(2, f"bench viewer export: {exc}\n")
