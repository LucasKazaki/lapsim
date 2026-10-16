"""Actual five-owner compiled C in the same causal plant runner (TC-S12)."""

import json
import os
import shlex
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from lapsim.experiments.closed_loop import (
    ClosedLoopScenario,
    DriverPoint,
    replay_closed_loop,
    run_closed_loop,
)
from lapsim.experiments.controller_backend import PythonController, controller_module
from lapsim.experiments.dynamics_record import _content_id
from lapsim.experiments.native_controller import (
    NativeController,
    build_native_controller,
)


@pytest.fixture(scope="module")
def binary(tmp_path_factory):
    receipt = build_native_controller(
        tmp_path_factory.mktemp("native-parent") / "actual-build"
    )
    return Path(receipt["binary"])


def test_incremental_native_matches_every_frozen_source_composition(binary):
    for label, cfg, samples in controller_module(
        "allocator_parity"
    ).composition_scenarios():
        native = NativeController(binary, cfg.period_ms, cfg.allocator.max_input_age_ms)
        reference = PythonController(cfg.period_ms, cfg.allocator.max_input_age_ms)
        native.config = reference.config = cfg
        assert tuple(native.step(sample) for sample in samples) == tuple(
            reference.step(sample) for sample in samples
        ), label


def test_tc_s12_native_outputs_drive_the_real_loop_without_python_owner_fallback(
    binary, monkeypatch
):
    scenario = ClosedLoopScenario(
        duration_us=200_000, driver=(DriverPoint(0), DriverPoint(200_000, 0.7))
    )
    expected = run_closed_loop(scenario)["result"]
    native = NativeController(binary)

    def no_fallback(*args, **kwargs):
        raise AssertionError(
            "Python numerical owner was called during native execution"
        )

    for module, name in [
        ("allocator", "allocate_propulsive_torque"),
        ("command_guard", "apply_command_guard"),
        ("guard_trusted_clear", "apply_trusted_clear_guard"),
        ("fault_state", "observe_fault_state"),
        ("cycle_clock", "observe_cycle_clock"),
    ]:
        monkeypatch.setattr(controller_module(module), name, no_fallback)
    actual = run_closed_loop(
        replace(scenario, controller_backend_id="native_c"), native
    )
    assert actual["result"] == expected
    assert actual["controller_source"]["backend"] == "native_c"
    assert len(actual["controller_source"]["binary_sha256"]) == 64


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX multicall-symlink regression runs in Linux CI; Windows actual native build is tested above",
)
def test_multicall_compiler_launcher_keeps_invoked_name_and_builds_real_c(tmp_path):
    compiler = shutil.which("gcc")
    assert compiler is not None
    dispatcher = tmp_path / "multicall-dispatcher"
    dispatcher.write_text(
        '#!/bin/sh\n[ "$(basename "$0")" = "gcc" ] || exit 9\nexec '
        + shlex.quote(compiler)
        + ' "$@"\n'
    )
    dispatcher.chmod(0o755)
    launcher = tmp_path / "gcc"
    launcher.symlink_to(dispatcher)
    receipt = build_native_controller(tmp_path / "actual-build", str(launcher))
    assert receipt["compiler_invoked"] == str(launcher)
    assert Path(receipt["binary"]).is_file()


@pytest.mark.parametrize(
    "fault", ["missing", "binary", "source", "extra_source", "flags", "schema"]
)
def test_compatible_native_binary_with_wrong_receipt_is_rejected_before_load(
    binary, tmp_path, monkeypatch, fault
):
    copied = tmp_path / binary.name
    shutil.copyfile(binary, copied)
    receipt = json.loads((binary.parent / "build.json").read_text(encoding="utf-8"))
    if fault == "binary":
        receipt["binary_sha256"] = "0" * 64
    elif fault == "source":
        receipt["source_files_sha256"]["torque_guard.c"] = "0" * 64
    elif fault == "extra_source":
        receipt["source_files_sha256"]["unreviewed.c"] = "0" * 64
    elif fault == "flags":
        receipt["argv"].insert(1, "-ffast-math")
    elif fault == "schema":
        receipt["schema"] = "other"
    if fault != "missing":
        (tmp_path / "build.json").write_text(json.dumps(receipt), encoding="utf-8")

    def no_load(*args, **kwargs):
        raise AssertionError("invalid receipt reached native library loader")

    monkeypatch.setattr(controller_module("allocator_parity"), "AllocatorCore", no_load)
    with pytest.raises(ValueError, match="native|receipt"):
        NativeController(copied)


def test_native_run_binds_compiler_and_replay_rejects_rehashed_toolchain_change(binary):
    record = run_closed_loop(
        ClosedLoopScenario(
            duration_us=100_000,
            controller_backend_id="native_c",
            driver=(DriverPoint(0), DriverPoint(100_000, 0.2)),
        ),
        NativeController(binary),
    )
    receipt = json.loads((binary.parent / "build.json").read_text(encoding="utf-8"))
    assert (
        record["controller_source"]["native_build"]["compiler_version"]
        == receipt["compiler_version"]
    )
    assert record["controller_source"]["native_build"]["argv"] == receipt["argv"]
    assert replay_closed_loop(record, NativeController(binary))["model_agreement"]
    record["controller_source"]["native_build"]["compiler_version"] = (
        "invented toolchain"
    )
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError, match="artifact identity"):
        replay_closed_loop(record, NativeController(binary))
