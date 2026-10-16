"""Actual five-owner compiled C in the same causal plant runner (TC-S12)."""

from dataclasses import replace
import os
from pathlib import Path
import shlex
import shutil

import pytest

from lapsim.experiments.closed_loop import (
    ClosedLoopScenario,
    DriverPoint,
    run_closed_loop,
)
from lapsim.experiments.controller_backend import PythonController, controller_module
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
