"""A recipient rebuilding a source snapshot retains the documented handoff."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest


def test_no_git_rebuild_preserves_handoff_and_hashes(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("snapshot_build", root / "scripts/build_windows.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    snapshot = tmp_path / "source snapshot"
    snapshot.mkdir()
    names = (
        "README.md", "START-HERE.txt", "AGENTS.md", "ENME408_IMPLEMENTATION_PLAN.md",
        "pyproject.toml", "setup.py", "requirements-build.lock", "build_lapsim.cmd",
        "setup_lapsim.cmd", "setup_lapsim.ps1", "launch_lapsim.cmd", "packaging/LapSim.spec",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
        "docs/controller_testing_contract.md", "docs/team_release_contract.md",
        "controller/reference/native/torque_allocator.c", "controller/import-manifest.json",
        "web/index.html", "web/basic.html", "web/basic.js", "web/worker.js",
        "web/examples/enme408-synthetic-replay.json", "web/examples/enme408-native-c-replay.json",
        "web/control.html", "web/control.css", "web/control.js",
        "firmware/bench/main.c", "firmware/bench/startup.c", "firmware/bench/f405-qemu.ld",
    )
    for name in names:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"snapshot content: {name}\n", encoding="utf-8")
    # Use the actual reviewed bytes, then contaminate the recipient's copy.
    shutil.copytree(root / "web", snapshot / "web", dirs_exist_ok=True)
    private = snapshot / "web/examples/private-capture.json"
    private.write_text('"private sentinel"', encoding="utf-8")
    (snapshot / "web/private-notes.txt").write_text("private notes", encoding="utf-8")
    (snapshot / "build-info.json").write_text('{"code_commit":"upstream-identity"}')
    monkeypatch.setattr(builder, "ROOT", snapshot)
    monkeypatch.setattr(builder, "version", lambda name: "test-version")

    class NoDependencyFiles:
        requires = ()
        files = ()

        def __init__(self, name):
            self.metadata = {"Name": name}

    monkeypatch.setattr(builder, "distribution", NoDependencyFiles)
    assets = builder.stage_assets()
    identity = json.loads((assets / "build-info.json").read_text())
    assert identity["code_commit"] == "upstream-identity"
    assert identity["dirty_worktree"] is True
    for name in names:
        assert (assets / name).read_bytes() == (snapshot / name).read_bytes()
        assert name in identity["files_sha256"]
    assert not (assets / "web/examples/private-capture.json").exists()
    assert not (assets / "web/private-notes.txt").exists()
    assert private.read_text(encoding="utf-8") == '"private sentinel"'


@pytest.mark.parametrize("mutation", ["replace", "remove", "missing_frontend", "missing_directory"])
def test_snapshot_rejects_changed_or_missing_reviewed_replay(tmp_path, monkeypatch, mutation):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("snapshot_replay_guard", root / "scripts/build_windows.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    shutil.copytree(root / "web", tmp_path / "web")
    replay = tmp_path / "web/examples/enme408-native-c-replay.json"
    if mutation == "replace":
        replay.write_bytes(b"private replacement")
    elif mutation == "remove":
        replay.unlink()
    elif mutation == "missing_frontend":
        (tmp_path / "web/app.js").unlink()
    else:
        shutil.rmtree(tmp_path / "web")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="unreviewed|missing required"):
        builder.stage_assets()


@pytest.fixture
def archive_build(tmp_path, monkeypatch):
    """Run real archive assembly; no PyInstaller, pytest child or EXE is launched."""
    source = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "verification_archive_build", source / "scripts/build_windows.py"
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original_stage_assets = builder.stage_assets
    root = tmp_path / "source checkout"
    output = tmp_path / "shared output"
    (root / "work").mkdir(parents=True)
    generator = root / "docs/simulator_flowchart/generate_inventory.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("# Inventory command is observed, never executed.\n")
    poison = {
        root
        / "work/test-results.xml": b'<testsuites><testsuite name="unrelated old suite" tests="1"/></testsuites>',
        root
        / "work/foreign-results.xml": b'<testsuites><testsuite name="unrelated future timestamp" tests="1"/></testsuites>',
        root / "work/test-suite.log": b"unrelated shell tee output\n",
        root / "work/physics-operating-sweep.json": b'{"unrelated":"sweep"}',
        root / "work/gui-recovery.log": b"unrelated desktop workflow\n",
        output
        / "prior verification run/test-results.xml": b'<testsuites><testsuite name="prior output run" tests="1"/></testsuites>',
    }
    for path, raw in poison.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    # A recent timestamp cannot establish which invocation produced evidence.
    future = root / "work/foreign-results.xml"
    os.utime(future, ns=(4_000_000_000_000_000_000, 4_000_000_000_000_000_000))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in poison}
    identity = {
        "code_commit": "recorded-packaged-source",
        "dirty_worktree": True,
        "source_sha256": "a" * 64,
    }
    state = SimpleNamespace(
        builder=builder,
        root=root,
        output=output,
        originals=before,
        identity=identity,
        mode="passed",
        real_stage_assets=False,
        calls=[],
        test_commands=[],
        report_paths=[],
        fresh_reports=[],
        portable_commands=[],
    )

    def stage_assets(*args, **kwargs):
        state.calls.append("stage assets")
        if state.real_stage_assets:
            return original_stage_assets(*args, **kwargs)
        assets = root / "build/assets"
        assets.mkdir(parents=True, exist_ok=True)
        (assets / "build-info.json").write_text(json.dumps(identity), encoding="utf-8")
        (assets / "README.txt").write_text("packaged source sentinel\n")
        return assets

    def external_command(*args, **kwargs):
        argv = [str(arg) for arg in args]
        if argv[1].endswith("check_all.py"):
            state.calls.append("full tests")
            state.test_commands.append(argv)
            if "--output-dir" in argv:
                reports = Path(argv[argv.index("--output-dir") + 1])
            else:
                reports = root / "work"
            reports.mkdir(parents=True, exist_ok=True)
            report = reports / "test-results.xml"
            state.report_paths.append(report)
            if state.mode != "missing":
                number = len(state.test_commands)
                failure = (
                    "<failure>current build failed</failure>"
                    if state.mode == "failed"
                    else ""
                )
                raw = (
                    f'<testsuites><testsuite name="fresh build {number}" tests="2" '
                    f'failures="{int(state.mode == "failed")}" errors="0" skipped="1">'
                    f'<testcase name="current invocation {number}">{failure}</testcase>'
                    '<testcase name="explicit skip"><skipped/></testcase>'
                    "</testsuite></testsuites>"
                ).encode()
                report.write_bytes(raw)
                state.fresh_reports.append(raw)
            if state.mode == "failed":
                raise subprocess.CalledProcessError(17, argv)
        elif argv[1] == str(generator):
            state.calls.append("inventory generation")
        elif argv[1:3] == ["-m", "PyInstaller"]:
            state.calls.append("PyInstaller")
            destination = Path(argv[argv.index("--distpath") + 1])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "LapSim.exe").write_bytes(b"stub executable; never executed")
        else:
            pytest.fail("Unexpected external build command: " + repr(argv))

    def portable_command(argv, **kwargs):
        state.portable_commands.append([str(arg) for arg in argv])
        assert len(argv) == 3 and argv[1] == "--self-test"
        assert Path(argv[0]).read_bytes() == b"stub executable; never executed"
        Path(argv[2]).write_text(
            json.dumps({"status": "passed", "frozen": True}), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "stage_assets", stage_assets)
    monkeypatch.setattr(builder, "run", external_command)
    monkeypatch.setattr(builder, "subprocess", SimpleNamespace(run=portable_command))
    monkeypatch.setattr(
        builder,
        "sys",
        SimpleNamespace(**{**vars(sys), "platform": "win32", "maxsize": 2**63 - 1}),
    )
    monkeypatch.setattr(
        builder, "sysconfig", SimpleNamespace(get_platform=lambda: "win-amd64")
    )
    monkeypatch.setattr(
        builder, "os", SimpleNamespace(name=os.name, environ=dict(os.environ))
    )

    def invoke(*, skip):
        argv = ["build_windows.py", "--output-dir", str(state.output)]
        if skip:
            argv.append("--skip-tests")
        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setattr(builder.sys, "argv", argv)
        return builder.main()

    state.invoke = invoke
    return state


def assert_build_inputs_preserved(build):
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in build.originals
    } == build.originals


def read_build_verification(build, *, status):
    with ZipFile(build.output / "LapSim-Windows-x64.zip") as archive:
        receipt = json.loads(archive.read("verification/build-verification.json"))
        assert receipt["schema"] == "lapsim.build-verification.v1"
        assert receipt["full_suite"]["status"] == status
        assert receipt["source_scope"] == (
            "When run, full repository tests precede inventory generation; "
            "packaged snapshot identity is separate."
        )
        assert receipt["packaged_source"] == build.identity
        assert json.loads(archive.read("build-info.json")) == build.identity
        assert json.loads(archive.read("portable-self-test.json")) == {
            "status": "passed",
            "frozen": True,
        }
        checksums = json.loads(archive.read("checksums.json"))
        assert checksums["LapSim.exe"] == sha256(archive.read("LapSim.exe")).hexdigest()
        expected = {"verification/build-verification.json"}
        if status == "passed":
            expected.add("verification/test-results.xml")
            raw = archive.read("verification/test-results.xml")
            assert raw == build.fresh_reports[-1]
            assert receipt["full_suite"]["command"] == [
                "python",
                "scripts/check_all.py",
                "--output-dir",
                "<build-owned-report-directory>",
            ]
            assert receipt["full_suite"]["command_scope"] == (
                "Sanitized logical command; actual argv is retained only in local build evidence."
            )
            assert receipt["full_suite"]["report"] == {
                "path": "verification/test-results.xml",
                "sha256": sha256(raw).hexdigest(),
            }
        else:
            assert receipt["full_suite"]["command"] is None
            assert receipt["full_suite"]["report"] is None
        public_text = (
            json.dumps(receipt, ensure_ascii=False)
            .replace("\\\\", "/")
            .replace("\\", "/")
            .casefold()
        )
        for private_path in (
            build.root.parent,
            build.root,
            build.output,
            Path(sys.executable),
        ):
            assert private_path.is_absolute()
            assert private_path.as_posix().casefold() not in public_text
        assert {
            name for name in archive.namelist() if name.startswith("verification/")
        } == expected
    return receipt


def test_skip_tests_zip_excludes_ambient_and_prior_output_evidence(archive_build):
    build = archive_build
    assert build.invoke(skip=True) == 0
    with ZipFile(build.output / "LapSim-Windows-x64.zip") as archive:
        members = set(archive.namelist())
        # Expose the observed stale attachment before checking the new receipt.
        assert "verification/test-results.xml" not in members
        assert {name for name in members if name.startswith("verification/")} == {
            "verification/build-verification.json"
        }
    read_build_verification(build, status="skipped")
    assert build.test_commands == []
    assert build.calls == ["inventory generation", "stage assets", "PyInstaller"]
    assert len(build.portable_commands) == 1
    assert_build_inputs_preserved(build)


def test_full_build_bundles_only_its_fresh_report_and_exact_command(archive_build):
    build = archive_build
    assert build.invoke(skip=False) == 0
    read_build_verification(build, status="passed")
    assert len(build.report_paths) == 1
    report = build.report_paths[0]
    assert report.parent != build.output and report.is_relative_to(build.output)
    assert report.is_file() and report.read_bytes() == build.fresh_reports[0]
    assert build.test_commands[0][1] == str(build.root / "scripts/check_all.py")
    assert build.test_commands[0][-2:] == ["--output-dir", str(report.parent)]
    assert build.calls == [
        "full tests",
        "inventory generation",
        "stage assets",
        "PyInstaller",
    ]
    assert_build_inputs_preserved(build)


def test_successful_runner_without_fresh_report_cannot_package_ambient_report(
    archive_build,
):
    build = archive_build
    build.mode = "missing"
    with pytest.raises(
        (RuntimeError, FileNotFoundError), match=r"report|JUnit|verification"
    ):
        build.invoke(skip=False)
    assert build.calls == ["full tests"]
    assert not (build.output / "LapSim-Windows-x64.zip").exists()
    assert build.report_paths[0].parent.is_relative_to(build.output)
    assert build.report_paths[0].parent.is_dir()
    assert_build_inputs_preserved(build)


def test_failed_runner_preserves_its_evidence_and_does_not_build(archive_build):
    build = archive_build
    build.mode = "failed"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        build.invoke(skip=False)
    assert caught.value.returncode == 17
    assert build.calls == ["full tests"]
    assert not (build.output / "LapSim-Windows-x64.zip").exists()
    report = build.report_paths[0]
    assert report.is_relative_to(build.output)
    assert report.read_bytes() == build.fresh_reports[0]
    assert b"current build failed" in report.read_bytes()
    assert_build_inputs_preserved(build)


@pytest.mark.parametrize("skip_second", (False, True))
def test_reused_output_never_adopts_previous_build_report(archive_build, skip_second):
    build = archive_build
    assert build.invoke(skip=False) == 0
    first = build.report_paths[0]
    assert first.is_relative_to(build.output)
    original = first.read_bytes(), first.stat().st_mtime_ns
    assert build.invoke(skip=skip_second) == 0
    read_build_verification(build, status="skipped" if skip_second else "passed")
    assert (first.read_bytes(), first.stat().st_mtime_ns) == original
    if skip_second:
        assert len(build.test_commands) == 1
    else:
        assert len(build.test_commands) == 2
        assert build.report_paths[1].parent != first.parent
        assert build.fresh_reports[0] != build.fresh_reports[1]
    assert_build_inputs_preserved(build)


@pytest.mark.parametrize("skip", (False, True), ids=("full", "skip"))
@pytest.mark.parametrize(
    "inherit_literal", (False, True), ids=("normal-env", "literal-env")
)
@pytest.mark.parametrize(
    "source_change",
    ("clean", "tracked", "untracked-sibling"),
)
def test_own_verification_does_not_contaminate_real_git_source_identity(
    archive_build, monkeypatch, skip, source_change, inherit_literal
):
    build = archive_build
    build.real_stage_assets = True
    # Deliberately relative, nonignored, and containing pathspec metacharacters.
    build.output = Path("release [candidate]")
    monkeypatch.chdir(build.root)
    source = Path(__file__).resolve().parents[1]
    for name in (
        "README.md",
        "START-HERE.txt",
        "AGENTS.md",
        "ENME408_IMPLEMENTATION_PLAN.md",
        "pyproject.toml",
        "setup.py",
        "requirements-build.lock",
        "build_lapsim.cmd",
        "setup_lapsim.cmd",
        "setup_lapsim.ps1",
        "launch_lapsim.cmd",
        "packaging/LapSim.spec",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
    ):
        target = build.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    shutil.copytree(source / "web", build.root / "web")
    # Build/work were already generated or private scratch in the original fixture.
    # The selected release directory is intentionally absent from this ignore list.
    (build.root / ".gitignore").write_text("/build/\n/work/\n", encoding="utf-8")
    hooks = build.root / "work/no-hooks"
    hooks.mkdir()
    pathspec_environment = (
        "GIT_LITERAL_PATHSPECS",
        "GIT_GLOB_PATHSPECS",
        "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    )
    # Prevent inherited Git routing/configuration from affecting the temporary repo.
    for name in (
        *pathspec_environment,
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_TEMPLATE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delitem(build.builder.os.environ, name, raising=False)
    empty_global = build.root / "work/empty-global.gitconfig"
    empty_global.write_text("", encoding="utf-8")
    for name, value in (
        ("GIT_CONFIG_GLOBAL", str(empty_global)),
        ("GIT_CONFIG_NOSYSTEM", "1"),
    ):
        monkeypatch.setenv(name, value)
        monkeypatch.setitem(build.builder.os.environ, name, value)

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "-c",
                "init.defaultBranch=fixture",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=Synthetic Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                f"core.hooksPath={hooks}",
                *args,
            ],
            cwd=build.root,
            text=True,
        ).strip()

    git("init", "--quiet")
    git("add", "--all")
    git("commit", "--quiet", "--no-gpg-sign", "-m", "Synthetic clean build source")
    commit = git("rev-parse", "HEAD")
    assert git("status", "--porcelain", "--untracked-files=all") == ""
    if source_change == "tracked":
        readme = build.root / "README.md"
        readme.write_bytes(
            readme.read_bytes() + b"\nintentional tracked source change\n"
        )
    sibling = None
    if source_change == "untracked-sibling":
        # A prefix-wide or whole-output exclusion would incorrectly hide this.
        sibling = build.root / build.output / "verification-user-evidence/report.txt"
        sibling.parent.mkdir(parents=True)
        sibling.write_bytes(b"pre-existing user evidence, not owned by this build\n")
    expected_dirty = source_change in ("tracked", "untracked-sibling")
    assert bool(git("status", "--porcelain", "--untracked-files=all")) is expected_dirty
    tracked = [build.root / name for name in git("ls-files", "-z").split("\0") if name]
    source_before = {
        name: (name.read_bytes(), name.stat().st_mtime_ns) for name in tracked
    }
    sibling_before = (
        (sibling.read_bytes(), sibling.stat().st_mtime_ns) if sibling else None
    )
    if inherit_literal:
        # Inherited only after the real temporary repository is prepared.
        monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
        monkeypatch.setitem(build.builder.os.environ, "GIT_LITERAL_PATHSPECS", "1")
    # Real staging/source enumeration/Git/copy/hash/identity; only installed
    # dependency metadata enumeration follows the existing synthetic test seam.
    monkeypatch.setattr(build.builder, "version", lambda name: "test-version")
    monkeypatch.setattr(
        build.builder,
        "distribution",
        lambda name: SimpleNamespace(metadata={"Name": name}, requires=(), files=()),
    )
    monkeypatch.setattr(
        build.builder,
        "subprocess",
        SimpleNamespace(
            run=build.builder.subprocess.run, check_output=subprocess.check_output
        ),
    )
    assert build.invoke(skip=skip) == 0
    with ZipFile(build.output / "LapSim-Windows-x64.zip") as archive:
        identity = json.loads(archive.read("build-info.json"))
        verification = json.loads(archive.read("verification/build-verification.json"))
    assert identity["code_commit"] == commit
    assert verification["packaged_source"]["code_commit"] == commit
    assert (
        identity["dirty_worktree"],
        verification["packaged_source"]["dirty_worktree"],
    ) == (expected_dirty, expected_dirty)
    assert verification["packaged_source"]["source_sha256"] == identity["source_sha256"]
    assert git("rev-parse", "HEAD") == commit
    assert {
        name: (name.read_bytes(), name.stat().st_mtime_ns) for name in tracked
    } == source_before
    if sibling is not None:
        assert (sibling.read_bytes(), sibling.stat().st_mtime_ns) == sibling_before
    assert_build_inputs_preserved(build)


@pytest.mark.parametrize("skip", (False, True), ids=("full", "skip"))
@pytest.mark.parametrize("descendant", (False, True), ids=("assets", "descendant"))
def test_output_in_asset_staging_is_rejected_before_mutation(
    archive_build, capsys, skip, descendant
):
    build = archive_build
    assets = build.root / "build/assets"
    staging_sentinel = assets / "existing/staging-sentinel.bin"
    staging_sentinel.parent.mkdir(parents=True)
    staging_sentinel.write_bytes(b"existing asset bytes must survive refusal\n")
    source_sentinel = build.root / "README.md"
    source_sentinel.write_bytes(b"existing source bytes must survive refusal\n")
    input_sentinel = build.root / "work/supplied-record.json"
    input_sentinel.write_bytes(b"existing input bytes; never loaded\n")
    build.output = assets / "release" if descendant else assets
    assert build.output.exists() is (not descendant)
    # Exercise real staging in this test's temporary source root; retain the
    # fixture's full-suite/PyInstaller/copied-EXE external-command stubs.
    build.real_stage_assets = True

    def snapshot():
        files = {
            path.relative_to(build.root).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in build.root.rglob("*")
            if path.is_file()
        }
        directories = {
            path.relative_to(build.root).as_posix()
            for path in build.root.rglob("*")
            if path.is_dir()
        }
        return files, directories

    before = snapshot()
    try:
        with pytest.raises(SystemExit) as rejected:
            build.invoke(skip=skip)
        assert rejected.value.code == 2
        assert "Output directory must be outside asset staging tree" in (
            capsys.readouterr().err
        )
    finally:
        # Also retain the independent preservation oracle if an old builder
        # reaches staging and raises for an unrelated missing fixture asset.
        assert snapshot() == before
        assert build.output.exists() is (not descendant)
        assert build.calls == []
        assert build.test_commands == []
        assert build.portable_commands == []
        assert_build_inputs_preserved(build)
