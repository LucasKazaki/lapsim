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
        raise AssertionError(
            f"{source} is missing required text: {phrase!r}"
        )


def forbid(text: str, phrase: str, source: str) -> None:
    if normalized(phrase) in normalized(text):
        raise AssertionError(
            f"{source} contains prohibited or obsolete text: {phrase!r}"
        )


def main() -> int:
    required = (
        "LICENSE",
        "LICENSE_SCOPE.md",
        "NOTICE",
        "CONTRIBUTING.md",
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "LOCAL-WORKER.md",
        "START-HERE.txt",
        "docs/licensing.md",
        "docs/public_demo.md",
        "docs/release.md",
        "scripts/build_windows.py",
        "scripts/portable_entry.py",
        "src/lapsim/desktop.py",
        "scripts/check_dco.py",
        ".github/workflows/dco.yml",
        ".github/workflows/license-policy.yml",
    )
    documents = {name: read(name) for name in required}

    license_text = documents["LICENSE"]
    for phrase in (
        "LSCRL-1.0",
        "NOT AN OPEN-SOURCE LICENSE",
        '"Competition Use"',
        '"Authorized UMD Team"',
        '"Repository Maintainer"',
        "material conditions of every license grant",
        "artificial-intelligence or machine-learning system",
        "grant each Repository Maintainer",
        "publicly display, publicly perform, Distribute",
        "does not require a separate Signed Writing",
        "No patent, trademark, trade-secret",
        "automatically and immediately",
        "injunctive or other equitable relief",
    ):
        require(license_text, phrase, "LICENSE")

    scope = documents["LICENSE_SCOPE.md"]
    for phrase in (
        "4b55928cffbc8a5a3dbf8f489dec791f7d791269",
        "not presently covered",
        "Public visibility is not permission",
        "not a Competition Program or Competing Team solely because",
        "Unrelated recruiting",
        "This specific interpretation controls",
        "qualified counsel",
    ):
        require(scope, phrase, "LICENSE_SCOPE.md")

    notice = documents["NOTICE"]
    require(notice, "respective copyright holders", "NOTICE")
    require(notice, "No trademark license is granted", "NOTICE")

    contributing = documents["CONTRIBUTING.md"]
    for phrase in (
        "Section 9.2 rights",
        "publish, distribute, and sublicense",
        "Every non-merge commit",
        "scripts/check_dco.py",
        "sole bootstrap exception",
        "trusted base commit",
    ):
        require(contributing, phrase, "CONTRIBUTING.md")

    readme = documents["README.md"]
    require(readme, "source-available, not open source", "README.md")
    require(readme, "Terps Racing uses are permitted", "README.md")
    require(readme, "competition program is prohibited", "README.md")
    require(readme, "LICENSE_SCOPE.md", "README.md")

    guide = documents["docs/licensing.md"]
    for phrase in (
        "source-available, not open source",
        "What a public license cannot do",
        "employer separately sponsors or supplies",
        "Engineers at that sponsor",
        "Another Formula SAE team runs the simulator",
    ):
        require(guide, phrase, "docs/licensing.md")

    public_demo = documents["docs/public_demo.md"]
    for phrase in (
        "synthetic-data-only",
        "does not include team telemetry",
        "Another student vehicle competition program may not use",
        '"course_synthetic": true',
    ):
        require(public_demo, phrase, "docs/public_demo.md")

    release = documents["docs/release.md"]
    for phrase in (
        "synthetic-data-only",
        "explicit allowlist",
        "PUBLIC_DOCUMENTATION_FILES",
        "historical validation and verification reports",
        "docs/simulator_flowchart/QA.md",
        '"course_synthetic": true',
        "Rebuild from the full checkout",
        "LICENSE_SCOPE.md",
        "source-available, not open source",
    ):
        require(release, phrase, "docs/release.md")
    forbid(release, "mandatory fused course", "docs/release.md")

    start = documents["START-HERE.txt"]
    for phrase in (
        "competition-use restriction",
        "not open source",
        "synthetic analytic course",
        "contains no bundled team-derived GNSS/IMU course",
        "docs/public_demo.md",
        "historical validation report",
    ):
        require(start, phrase, "START-HERE.txt")

    builder = documents["scripts/build_windows.py"]
    for phrase in (
        "PUBLIC_DOCUMENTATION_FILES",
        "PUBLIC_SCRIPT_FILES",
        "PUBLIC_ROOT_FILES",
        "PUBLIC_DISTRIBUTION_EXCLUSIONS",
        "PUBLIC_DISTRIBUTION_EXCLUDED_PREFIXES",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
        "data/tires/hoosier_16x7p5-10_r20_upc.tir",
        "docs/simulator_flowchart/QA.md",
        "docs/evidence/",
        "leaked_excluded_files",
        "reviewed synthetic-data-only source snapshot",
        'and not _is_publicly_excluded(path.relative_to(ROOT))',
        'report.get("course_synthetic")',
        "scripts/check_license_policy.py",
    ):
        require(builder, phrase, "scripts/build_windows.py")
    for prohibited in (
        "git ls-files",
        '("docs", ("*.md"',
        '("tests",',
        '("data", ("*.tir"',
        '("analysis",',
        '("output/pdf"',
        'bundle.write(path, "verification/"',
    ):
        forbid(builder, prohibited, "scripts/build_windows.py")
    for required_name in (
        '"LICENSE"',
        '"LICENSE_SCOPE.md"',
        '"NOTICE"',
        '"CONTRIBUTING.md"',
        '"docs/licensing.md"',
        '"docs/public_demo.md"',
    ):
        require(builder, required_name, "scripts/build_windows.py")

    portable = documents["scripts/portable_entry.py"]
    require(
        portable,
        "public, synthetic-data-only distribution",
        "scripts/portable_entry.py",
    )
    require(portable, "if spec.synthetic", "scripts/portable_entry.py")
    require(
        portable,
        "course_catalog.COURSE_OPTIONS = public_options",
        "scripts/portable_entry.py",
    )

    desktop = documents["src/lapsim/desktop.py"]
    require(
        desktop,
        "release_spec = COURSE_OPTIONS[0]",
        "src/lapsim/desktop.py",
    )
    require(
        desktop,
        '"course_synthetic": release_spec.synthetic',
        "src/lapsim/desktop.py",
    )
    require(desktop, '"docs/public_demo.md"', "src/lapsim/desktop.py")
    forbid(desktop, "load_team_endurance_track", "src/lapsim/desktop.py")
    forbid(desktop, '"docs/engineering_handoff.md"', "src/lapsim/desktop.py")

    dco_script = documents["scripts/check_dco.py"]
    for phrase in (
        'POLICY_MARKER = "scripts/check_dco.py"',
        "bootstrap PR exempt",
        "Signed-off-by",
        "matching Signed-off-by trailer",
        '"--no-merges"',
    ):
        require(dco_script, phrase, "scripts/check_dco.py")
    forbid(dco_script, 'f"{ref}:CONTRIBUTING.md"', "scripts/check_dco.py")

    dco_workflow = documents[".github/workflows/dco.yml"]
    for phrase in (
        "pull_request_target:",
        "Check out the trusted base commit",
        "Fetch the proposed head commit without checking it out",
        'git fetch --no-tags origin "refs/pull/${PR_NUMBER}/head"',
        'test "$(git rev-parse FETCH_HEAD)" = "$HEAD_SHA"',
        "Run the validator from the trusted base checkout",
        'python scripts/check_dco.py --base "$BASE_SHA" --head "$HEAD_SHA"',
        "github.event.pull_request.base.sha",
        "github.event.pull_request.head.sha",
    ):
        require(dco_workflow, phrase, ".github/workflows/dco.yml")
    for prohibited in (
        '$RUNNER_TEMP/check_dco.py',
        'git show "$BASE_SHA:scripts/check_dco.py"',
    ):
        forbid(dco_workflow, prohibited, ".github/workflows/dco.yml")

    agent = documents["AGENTS.md"]
    require(agent, "LICENSE_SCOPE.md", "AGENTS.md")
    require(agent, "competition-sensitive", "AGENTS.md")
    require(agent, "check_license_policy.py", "AGENTS.md")

    claude = documents["CLAUDE.md"]
    require(claude, "AGENTS.md", "CLAUDE.md")
    require(claude, "check_license_policy.py", "CLAUDE.md")

    policy_workflow = documents[".github/workflows/license-policy.yml"]
    for phrase in (
        "scripts/check_license_policy.py",
        "scripts/portable_entry.py",
        "src/lapsim/desktop.py",
        ".github/workflows/dco.yml",
        "docs/public_demo.md",
    ):
        require(
            policy_workflow,
            phrase,
            ".github/workflows/license-policy.yml",
        )

    print("License policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
