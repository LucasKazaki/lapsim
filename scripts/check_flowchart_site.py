#!/usr/bin/env python3
"""Validate the repository-owned LapSim static flowchart site.

The check uses only the Python standard library so it can run in a fresh
checkout before GitHub Pages publication.
"""

from __future__ import annotations

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


EXPECTED_SCRIPTS = [
    "data/core.js",
    "data/01-entrypoints.js",
    "data/02-inputs.js",
    "data/03-distance-pipeline.js",
    "data/04-vehicle-cell.js",
    "data/05-component-physics.js",
    "data/06-racing-line.js",
    "data/07-planar-model.js",
    "data/08-results.js",
    "data/09-verification.js",
    "data.js",
    "app.js",
]


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value for name, value in attrs}
        if tag.lower() == "script" and attributes.get("src"):
            self.scripts.append(str(attributes["src"]))
        elif tag.lower() == "link" and attributes.get("href"):
            rel = str(attributes.get("rel") or "").lower().split()
            if "stylesheet" in rel:
                self.stylesheets.append(str(attributes["href"]))
        elif tag.lower() == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))


def fail(message: str) -> None:
    raise AssertionError(message)


def local_path(base: Path, reference: str) -> Path | None:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or reference.startswith("//"):
        return None
    if not parsed.path or parsed.path.startswith("/"):
        return None
    return (base / parsed.path).resolve()


def validate_html(repo_root: Path, site_root: Path) -> dict[str, int]:
    index_path = site_root / "index.html"
    parser = AssetParser()
    parser.feed(index_path.read_text(encoding="utf-8"))

    if parser.scripts != EXPECTED_SCRIPTS:
        fail(
            "Flowchart script order changed. Expected "
            f"{EXPECTED_SCRIPTS!r}, found {parser.scripts!r}."
        )
    if parser.stylesheets != ["styles.css"]:
        fail(f"Expected only styles.css, found {parser.stylesheets!r}.")

    for reference in [*parser.scripts, *parser.stylesheets]:
        path = local_path(site_root, reference)
        if path is None:
            fail(f"Runtime asset must be repository-local: {reference}")
        if site_root not in path.parents and path != site_root:
            fail(f"Runtime asset escapes the flowchart directory: {reference}")
        if not path.is_file():
            fail(f"Missing runtime asset: {reference}")

    repository_link = local_path(site_root, "../../README.md")
    if repository_link != repo_root / "README.md" or not repository_link.is_file():
        fail("The local Repository README link does not resolve to README.md.")

    root_index = repo_root / "index.html"
    root_text = root_index.read_text(encoding="utf-8")
    if "docs/simulator_flowchart/" not in root_text:
        fail("Root index.html does not redirect to the flowchart.")
    if "https://lucaskazaki.github.io/lapsim/docs/simulator_flowchart/" not in root_text:
        fail("Root index.html is missing the canonical public URL.")
    if not (repo_root / ".nojekyll").is_file():
        fail("The Pages source is missing .nojekyll.")

    return {
        "scripts": len(parser.scripts),
        "stylesheets": len(parser.stylesheets),
        "links": len(parser.links),
    }


def validate_required_files(repo_root: Path, site_root: Path) -> None:
    required = {
        repo_root / "index.html",
        repo_root / ".nojekyll",
        site_root / "index.html",
        site_root / "styles.css",
        site_root / "app.js",
        site_root / "data.js",
        site_root / "README.md",
        *(site_root / script for script in EXPECTED_SCRIPTS[:-2]),
    }
    missing = sorted(str(path.relative_to(repo_root)) for path in required if not path.is_file())
    if missing:
        fail("Missing required flowchart files: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository checkout root.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    site_root = repo_root / "docs" / "simulator_flowchart"
    validate_required_files(repo_root, site_root)
    counts = validate_html(repo_root, site_root)
    print(
        "Flowchart static-site validation passed: "
        f"{counts['scripts']} scripts, {counts['stylesheets']} stylesheet, "
        f"{counts['links']} document links."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"Flowchart validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
