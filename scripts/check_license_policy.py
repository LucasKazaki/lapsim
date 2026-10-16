"""Validate the repository's source-available licensing policy and packaging hooks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"Required licensing file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.split())


def require(text: str, phrase: str, source: str) -> None:
    if normalized(phrase) not in normalized(text):
        raise AssertionError(f"{source} is missing required text: {phrase!r}")


def forbid(text: str, phrase: str, source: str) -> None:
    if normalized(phrase) in normalized(text):
        raise AssertionError(f"{source} contains obsolete text: {phrase!r}")


def main() -> int:
    required = (
        "LICENSE",
        "LICENSE_SCOPE.md",
        "NOTICE",
        "CONTRIBUTING.md",
        "docs/licensing.md",
        "docs/release.md",
        "START-HERE.txt",
        "scripts/build_windows.py",
    )
    documents = {name: read(name) for name in required}

    license_text = documents["LICENSE"]
    require(license_text, "LSCRL-1.0", "LICENSE")
    require(license_text, "NOT AN OPEN-SOURCE LICENSE", "LICENSE")
    require(license_text, '"Competition Use"', "LICENSE")
    require(license_text, '"Authorized UMD Team"', "LICENSE")
    require(license_text, "material conditions of every license grant", "LICENSE")
    require(license_text, "artificial-intelligence or machine-learning system", "LICENSE")
    require(license_text, "No patent, trademark, trade-secret", "LICENSE")
    require(license_text, "automatically and immediately", "LICENSE")
    require(license_text, "injunctive or other equitable relief", "LICENSE")

    scope = documents["LICENSE_SCOPE.md"]
    require(scope, "4b55928cffbc8a5a3dbf8f489dec791f7d791269", "LICENSE_SCOPE.md")
    require(scope, "not presently covered", "LICENSE_SCOPE.md")
    require(scope, "Public visibility is not permission", "LICENSE_SCOPE.md")
    require(scope, "qualified counsel", "LICENSE_SCOPE.md")

    notice = documents["NOTICE"]
    require(notice, "respective copyright holders", "NOTICE")
    require(notice, "No trademark license is granted", "NOTICE")

    guide = documents["docs/licensing.md"]
    require(guide, "source-available, not open source", "docs/licensing.md")
    require(guide, "What a public license cannot do", "docs/licensing.md")
    require(guide, "Another Formula SAE team runs the simulator", "docs/licensing.md")

    release = documents["docs/release.md"]
    forbid(release, "does not declare a project license", "docs/release.md")
    require(release, "LICENSE_SCOPE.md", "docs/release.md")
    require(release, "source-available, not open source", "docs/release.md")

    start = documents["START-HERE.txt"]
    require(start, "competition-use restriction", "START-HERE.txt")
    require(start, "not open source", "START-HERE.txt")

    builder = documents["scripts/build_windows.py"]
    forbid(builder, "does not declare a redistribution license", "scripts/build_windows.py")
    for required_name in (
        '"LICENSE"',
        '"LICENSE_SCOPE.md"',
        '"NOTICE"',
        '"CONTRIBUTING.md"',
        '"docs/licensing.md"',
    ):
        require(builder, required_name, "scripts/build_windows.py")
    require(builder, "Refusing to build a distributable archive without legal notices", "scripts/build_windows.py")

    print("License policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
