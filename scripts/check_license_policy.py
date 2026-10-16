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
        "docs/licensing.md",
        "docs/release.md",
        "START-HERE.txt",
        "scripts/build_windows.py",
        "scripts/portable_entry.py",
        "src/lapsim/desktop.py",
        "scripts/check_dco.py",
        ".github/workflows/dco.yml",
        ".github/workflows/license-policy.yml",
    )
    documents = {name: read(name) for name in required}

    license_text = documents["LICENSE"]
    require(license_text, "LSCRL-1.0", "LICENSE")
    require(license_text, "NOT AN OPEN-SOURCE LICENSE", "LICENSE")
    require(license_text, '"Competition Use"', "LICENSE")
    require(license_text, '"Authorized UMD Team"', "LICENSE")
    require(license_text, '"Repository Maintainer"', "LICENSE")
    require(
        license_text,
        "material conditions of every license grant",
        "LICENSE",
    )
    require(
        license_text,
        "artificial-intelligence or machine-learning system",
        "LICENSE",
    )
    require(
        license_text,
        "grant each Repository Maintainer",
        "LICENSE",
    )
    require(
        license_text,
        "publicly display, publicly perform, Distribute",
        "LICENSE",
    )
    require(
        license_text,
        "does not require a separate Signed Writing",
        "LICENSE",
    )
    require(
        license_text,
        "No patent, trademark, trade-secret",
        "LICENSE",
    )
    require(
        license_text,
        "automatically and immediately",
        "LICENSE",
    )
    require(
        license_text,
        "injunctive or other equitable relief",
        "LICENSE",
    )

    scope = documents["LICENSE_SCOPE.md"]
    require(
        scope,
        "4b55928cffbc8a5a3dbf8f489dec791f7d791269",
        "LICENSE_SCOPE.md",
    )
    require(scope, "not presently covered", "LICENSE_SCOPE.md")
    require(
        scope,
        "Public visibility is not permission",
        "LICENSE_SCOPE.md",
    )
    require(
        scope,
        "not a Competition Program or Competing Team solely because",
        "LICENSE_SCOPE.md",
    )
    require(scope, "Unrelated recruiting", "LICENSE_SCOPE.md")
    require(
        scope,
        "This specific interpretation controls",
        "LICENSE_SCOPE.md",
    )
    require(scope, "qualified counsel", "LICENSE_SCOPE.md")

    notice = documents["NOTICE"]
    require(notice, "respective copyright holders", "NOTICE")
    require(notice, "No trademark license is granted", "NOTICE")

    contributing = documents["CONTRIBUTING.md"]
    require(contributing, "Section 9.2 rights", "CONTRIBUTING.md")
    require(
        contributing,
        "publish, distribute, and sublicense",
        "CONTRIBUTING.md",
    )
    require(
        contributing,
        "Every commit made after this policy is adopted",
        "CONTRIBUTING.md",
    )
    require(
        contributing,
        "sole bootstrap exception",
        "CONTRIBUTING.md",
    )
    require(contributing, "DCO sign-off", "CONTRIBUTING.md")

    readme = documents["README.md"]
    require(readme, "source-available, not open source", "README.md")
    require(readme, "Terps Racing uses are permitted", "README.md")
    require(
        readme,
        "competition program is prohibited",
        "README.md",
    )
    require(readme, "LICENSE_SCOPE.md", "README.md")

    guide = documents["docs/licensing.md"]
    require(
        guide,
        "source-available, not open source",
        "docs/licensing.md",
    )
    require(
        guide,
        "What a public license cannot do",
        "docs/licensing.md",
    )
    require(
        guide,
        "employer separately sponsors or supplies",
        "docs/licensing.md",
    )
    require(
        guide,
        "Engineers at that sponsor",
        "docs/licensing.md",
    )
    require(
        guide,
        "Another Formula SAE team runs the simulator",
        "docs/licensing.md",
    )

    release = documents["docs/release.md"]
    require(release, "synthetic-data-only", "docs/release.md")
    require(release, "analysis/data/", "docs/release.md")
    require(release, '"course_synthetic": true', "docs/release.md")
    require(release, "LICENSE_SCOPE.md", "docs/release.md")
    require(
        release,
        "source-available, not open source",
        "docs/release.md",
    )
    forbid(release, "mandatory fused course", "docs/release.md")

    start = documents["START-HERE.txt"]
    require(start, "competition-use restriction", "START-HERE.txt")
    require(start, "not open source", "START-HERE.txt")
    require(start, "synthetic analytic course", "START-HERE.txt")
    require(
        start,
        "contains no bundled team-derived GNSS/IMU course",
        "START-HERE.txt",
    )

    builder = documents["scripts/build_windows.py"]
    require(
        builder,
        "PUBLIC_DISTRIBUTION_EXCLUSIONS",
        "scripts/build_windows.py",
    )
    require(
        builder,
        "PUBLIC_DISTRIBUTION_EXCLUDED_PREFIXES",
        "scripts/build_windows.py",
    )
    require(
        builder,
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "scripts/build_windows.py",
    )
    require(
        builder,
        "analysis/data/track/gnss_imu_endurance_track.json",
        "scripts/build_windows.py",
    )
    require(
        builder,
        "leaked_excluded_files",
        "scripts/build_windows.py",
    )
    require(
        builder,
        "curated synthetic-data-only source snapshot",
        "scripts/build_windows.py",
    )
    require(
        builder,
        'report.get("course_synthetic")',
        "scripts/build_windows.py",
    )
    require(
        builder,
        "scripts/check_license_policy.py",
        "scripts/build_windows.py",
    )
    forbid(builder, "git ls-files", "scripts/build_windows.py")
    forbid(builder, '("output/pdf"', "scripts/build_windows.py")
    for required_name in (
        '"LICENSE"',
        '"LICENSE_SCOPE.md"',
        '"NOTICE"',
        '"CONTRIBUTING.md"',
        '"docs/licensing.md"',
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
    forbid(
        desktop,
        "load_team_endurance_track",
        "src/lapsim/desktop.py",
    )

    dco_script = documents["scripts/check_dco.py"]
    require(dco_script, "bootstrap PR exempt", "scripts/check_dco.py")
    require(dco_script, "Signed-off-by", "scripts/check_dco.py")
    require(
        dco_script,
        "matching Signed-off-by trailer",
        "scripts/check_dco.py",
    )

    dco_workflow = documents[".github/workflows/dco.yml"]
    require(dco_workflow, "pull_request:", ".github/workflows/dco.yml")
    require(dco_workflow, "fetch-depth: 0", ".github/workflows/dco.yml")
    require(
        dco_workflow,
        "scripts/check_dco.py",
        ".github/workflows/dco.yml",
    )
    require(
        dco_workflow,
        "github.event.pull_request.base.sha",
        ".github/workflows/dco.yml",
    )
    require(
        dco_workflow,
        "github.event.pull_request.head.sha",
        ".github/workflows/dco.yml",
    )

    agent = documents["AGENTS.md"]
    require(agent, "LICENSE_SCOPE.md", "AGENTS.md")
    require(agent, "competition-sensitive", "AGENTS.md")
    require(agent, "check_license_policy.py", "AGENTS.md")

    claude = documents["CLAUDE.md"]
    require(claude, "AGENTS.md", "CLAUDE.md")
    require(claude, "check_license_policy.py", "CLAUDE.md")

    policy_workflow = documents[".github/workflows/license-policy.yml"]
    require(
        policy_workflow,
        "scripts/check_license_policy.py",
        ".github/workflows/license-policy.yml",
    )
    require(
        policy_workflow,
        "scripts/portable_entry.py",
        ".github/workflows/license-policy.yml",
    )
    require(
        policy_workflow,
        "src/lapsim/desktop.py",
        ".github/workflows/license-policy.yml",
    )
    require(
        policy_workflow,
        ".github/workflows/dco.yml",
        ".github/workflows/license-policy.yml",
    )

    print("License policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
