"""Validate the repository's source-available licensing and release policy."""

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
        "README.md",
        "START-HERE.txt",
        "docs/licensing.md",
        "docs/release.md",
        "scripts/build_windows.py",
        "scripts/check_dco.py",
        "scripts/portable_entry.py",
        "src/lapsim/desktop.py",
        ".github/workflows/license-policy.yml",
    )
    documents = {name: read(name) for name in required}

    license_text = documents["LICENSE"]
    require(license_text, "LSCRL-1.0", "LICENSE")
    require(license_text, "NOT AN OPEN-SOURCE LICENSE", "LICENSE")
    require(license_text, '"Competition Use"', "LICENSE")
    require(license_text, '"Authorized UMD Team"', "LICENSE")
    require(license_text, '"Repository Maintainer"', "LICENSE")
    require(license_text, "material conditions of every license grant", "LICENSE")
    require(license_text, "artificial-intelligence or machine-learning system", "LICENSE")
    require(license_text, "grant each Repository Maintainer", "LICENSE")
    require(license_text, "publicly display, publicly perform, Distribute", "LICENSE")
    require(license_text, "does not require a separate Signed Writing", "LICENSE")
    require(license_text, "No patent, trademark, trade-secret", "LICENSE")
    require(license_text, "automatically and immediately", "LICENSE")
    require(license_text, "injunctive or other equitable relief", "LICENSE")

    scope = documents["LICENSE_SCOPE.md"]
    require(scope, "4b55928cffbc8a5a3dbf8f489dec791f7d791269", "LICENSE_SCOPE.md")
    require(scope, "not presently covered", "LICENSE_SCOPE.md")
    require(scope, "Public visibility is not permission", "LICENSE_SCOPE.md")
    require(scope, "not a Competition Program or Competing Team solely because", "LICENSE_SCOPE.md")
    require(scope, "Unrelated recruiting", "LICENSE_SCOPE.md")
    require(scope, "This specific interpretation controls", "LICENSE_SCOPE.md")
    require(scope, "qualified counsel", "LICENSE_SCOPE.md")

    notice = documents["NOTICE"]
    require(notice, "respective copyright holders", "NOTICE")
    require(notice, "No trademark license is granted", "NOTICE")

    contributing = documents["CONTRIBUTING.md"]
    require(contributing, "Section 9.2 rights", "CONTRIBUTING.md")
    require(contributing, "publish, distribute, and sublicense", "CONTRIBUTING.md")
    require(contributing, "every new non-merge commit", "CONTRIBUTING.md")
    require(contributing, "explicit one-time bootstrap adoption series", "CONTRIBUTING.md")
    require(contributing, "exception ends immediately", "CONTRIBUTING.md")
    require(contributing, "License and provenance policy", "CONTRIBUTING.md")

    readme = documents["README.md"]
    require(readme, "source-available, not open source", "README.md")
    require(readme, "Terps Racing uses are permitted", "README.md")
    require(readme, "competition program is prohibited", "README.md")
    require(readme, "LICENSE_SCOPE.md", "README.md")

    guide = documents["docs/licensing.md"]
    require(guide, "source-available, not open source", "docs/licensing.md")
    require(guide, "What a public license cannot do", "docs/licensing.md")
    require(guide, "employer separately sponsors or supplies", "docs/licensing.md")
    require(guide, "Engineers at that sponsor", "docs/licensing.md")
    require(guide, "Another Formula SAE team runs the simulator", "docs/licensing.md")

    release = documents["docs/release.md"]
    forbid(release, "does not declare a project license", "docs/release.md")
    require(release, "source-available, not open source", "docs/release.md")
    require(release, "public executable starts", "docs/release.md")
    require(release, "does **not** contain", "docs/release.md")
    require(release, "every directory named `output` or `outputs`", "docs/release.md")
    require(release, "selected course as synthetic", "docs/release.md")

    start = documents["START-HERE.txt"]
    require(start, "competition-use restriction", "START-HERE.txt")
    require(start, "not open source", "START-HERE.txt")
    require(start, "are not included in this public release", "START-HERE.txt")
    require(start, "public executable offers only analytic synthetic courses", "START-HERE.txt")

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
    require(builder, "EXCLUDED_RELEASE_PATHS", "scripts/build_windows.py")
    require(builder, "analysis/data/track/gnss_imu_endurance_track.csv", "scripts/build_windows.py")
    require(builder, "analysis/data/track/gnss_imu_endurance_track.json", "scripts/build_windows.py")
    require(builder, "EXCLUDED_RELEASE_PREFIXES", "scripts/build_windows.py")
    require(builder, "EXCLUDED_RELEASE_DIRECTORY_NAMES", "scripts/build_windows.py")
    require(builder, "excluded_staged_paths", "scripts/build_windows.py")
    require(builder, "Refusing to build a public archive containing excluded material", "scripts/build_windows.py")
    require(builder, "report.get(\"course_synthetic\")", "scripts/build_windows.py")
    require(builder, "scripts/check_license_policy.py", "scripts/build_windows.py")

    portable = documents["scripts/portable_entry.py"]
    require(portable, "public_options", "scripts/portable_entry.py")
    require(portable, "if spec.synthetic", "scripts/portable_entry.py")
    require(portable, "course_catalog.COURSE_OPTIONS = public_options", "scripts/portable_entry.py")

    desktop = documents["src/lapsim/desktop.py"]
    require(desktop, "release_spec = COURSE_OPTIONS[0]", "src/lapsim/desktop.py")
    require(desktop, '"course_synthetic": release_spec.synthetic', "src/lapsim/desktop.py")
    forbid(desktop, "load_team_endurance_track", "src/lapsim/desktop.py")

    dco = documents["scripts/check_dco.py"]
    require(dco, "bootstrap adoption series exempt", "scripts/check_dco.py")
    require(dco, "Signed-off-by", "scripts/check_dco.py")
    require(dco, "--no-merges", "scripts/check_dco.py")
    require(dco, "author_email", "scripts/check_dco.py")
    require(dco, "--policy-ref", "scripts/check_dco.py")

    workflow = documents[".github/workflows/license-policy.yml"]
    require(workflow, "pull_request:", ".github/workflows/license-policy.yml")
    require(workflow, "fetch-depth: 0", ".github/workflows/license-policy.yml")
    require(workflow, "scripts/check_dco.py", ".github/workflows/license-policy.yml")
    require(workflow, "github.event.pull_request.base.sha", ".github/workflows/license-policy.yml")
    require(workflow, "github.event.pull_request.head.sha", ".github/workflows/license-policy.yml")
    require(workflow, "github.event.repository.default_branch", ".github/workflows/license-policy.yml")
    require(workflow, "--policy-ref", ".github/workflows/license-policy.yml")

    print("License and public-release policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
