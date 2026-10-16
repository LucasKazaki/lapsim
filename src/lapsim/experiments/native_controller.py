"""Explicit five-owner host C backend with preserved compiler launcher identity."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from lapsim.resources import repository_root

from .controller_backend import (
    ZERO,
    PythonController,
    controller_module,
    controller_source_identity,
)


def find_runtime_compiler(explicit: str | None = None) -> str:
    """Normalize an invocation path without dereferencing its final symlink."""
    selected = explicit or os.environ.get("CC")
    candidates = [selected] if selected else ["gcc", "clang", "cc"]
    if not selected and sys.platform == "win32":
        candidates.append("C:/msys64/mingw64/bin/gcc.exe")
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return os.path.abspath(found)
    raise ValueError(
        "a GCC/Clang-compatible host compiler is required; no native fallback"
    )


def build_native_controller(output: Path, compiler: str | None = None) -> dict:
    """Build original C owners into a new attempt; retain the exact commands."""
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    compiler = find_runtime_compiler(compiler)
    root = repository_root() / "controller/reference/native"
    native = controller_module("allocator_parity")
    recipe = native.frozen_protocol()["planned_verification"]
    flags = [
        *recipe["host_common_flags"],
        *recipe["host_platform_flags"][
            "Windows" if sys.platform == "win32" else "other_supported_hosts"
        ],
    ]
    binary = output / (
        "lapsim_controller.dll" if sys.platform == "win32" else "lapsim_controller.so"
    )
    sources = [
        "torque_contract.c",
        "torque_clock.c",
        "torque_pedal.c",
        "torque_guard.c",
        "torque_allocator.c",
    ]
    command = [compiler, *flags, *sources, "-o", str(binary), "-lm"]
    environment = dict(os.environ)
    environment["PATH"] = (
        str(Path(compiler).parent) + os.pathsep + environment.get("PATH", "")
    )
    version = subprocess.run(
        [compiler, "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
        env=environment,
    )
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    (output / "compiler-stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "compiler-stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode or not binary.is_file():
        raise ValueError("native build failed; inspect retained compiler logs")
    receipt = {
        "schema": "lapsim.native-controller-build.v1",
        "compiler_invoked": compiler,
        "compiler_version": version.stdout.splitlines()[0],
        "argv": command,
        "binary": str(binary),
        "binary_sha256": sha256(binary.read_bytes()).hexdigest(),
        "source_files_sha256": {
            p.name: sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.glob("torque_*.[ch]"))
        },
        "numeric_contract": "binary64, ordinary nearest rounding, retained subnormals; frozen host flags",
    }
    (output / "build.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


class NativeController(PythonController):
    """All proposed results and state transitions come from compiled C owners."""

    backend_id = "native_c"

    def __init__(self, binary: Path, period_ms: int = 10, maximum_age_ms: int = 50):
        super().__init__(period_ms, maximum_age_ms)
        self.native = controller_module("allocator_parity")
        self.guard_api = controller_module("guard_parity")
        self.clock_api = controller_module("clock_parity")
        self.pedal_api = controller_module("pedal_parity")
        self.gate_api = controller_module("c_parity")
        self.core = self.native.AllocatorCore(binary)
        self.native_clock = self.clock_api.ClockState()
        self.native_gate = self.gate_api.Snapshot(3, 0, 0)
        self.identity = {
            **controller_source_identity(),
            "backend": "native_c",
            "binary_sha256": sha256(binary.read_bytes()).hexdigest(),
            "execution": "actual host shared library; no Python output fallback",
        }

    def step(self, sample: Any) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("native controller session is closed")
        if (
            type(sample) is not self.api["control_pipeline"].ControlSample
            or type(sample.restart_requested) is not bool
        ):
            raise ValueError("expected a typed controller sample")
        g = self.api["command_guard"]
        a = self.api["allocator"]
        if sample.restart_requested:
            self.guard_state = g.CommandGuardState(
                ZERO, self.guard_state.pedal_overlap_latched
            )
        raw = self.core.allocate_raw(
            self.native.allocator_input(sample.allocation),
            self.native.allocator_config(self.config.allocator),
        )
        candidate = self.native.decoded(raw)
        base = self.guard_api.decoded(
            self.core.apply_raw(
                raw,
                self.guard_api.guard_input(sample.guard),
                self.guard_api.config(self.config.guard),
                self.guard_api.state(self.guard_state),
            )
        )
        clock = self.core.step(
            self.native_clock,
            self.clock_api.clock_input(sample.allocation.now_ms, sample.guard.dt_s),
            self.clock_api.clock_policy(self.config.period_ms),
        )
        clock_data = self.clock_api.unpack(clock)
        reconciled = self.core.reconcile(
            self.pedal_api.facts(
                candidate,
                sample.guard,
                self.config.guard,
                self.guard_state,
                base,
                bool(clock.fault.kind),
            )
        )
        guarded = self.pedal_api.adapted(base, reconciled)
        observed = candidate
        if clock_data["fault"] or guarded.status == "inhibited":
            reason = clock_data["fault"] or (
                candidate.fault if candidate.status == "fault" else guarded.reason
            )
            observed = a.AllocationResult(
                ZERO, candidate.requested_nm, 0.0, "fault", reason
            )
        gate_candidate = (
            self.gate_api.allocation(observed) if guarded.status == "inhibited" else raw
        )
        decision = self.core.decide_raw(
            self.native_gate,
            self.gate_api.Cycle(
                gate_candidate,
                self.gate_api.guard(guarded),
                clock.fault,
                sample.restart_requested,
            ),
            self.gate_api.Policy(self.config.fault.valid_samples_to_recover),
        )
        reason = bytes(decision.reason).decode("ascii")
        allowed = bool(decision.command_allowed)
        command = list(decision.command)
        row = {
            "sequence": self.sequence,
            "now_ms": clock_data["now_ms"],
            "restart_requested": sample.restart_requested,
            "allocator": asdict(candidate),
            "guard": {
                "status": guarded.status,
                "reason": guarded.reason,
                "output_nm": list(guarded.output_nm),
                "pedal_overlap_latched": bool(reconciled.next_latched),
            },
            "fault": {
                "sequence": self.sequence,
                "generation": decision.next.generation,
                "restart_requested": sample.restart_requested,
                "previous_state": self.gate_api.STATE_NAMES[self.native_gate.state],
                "next_state": self.gate_api.STATE_NAMES[decision.next.state],
                "allocator_status": observed.status,
                "allocator_fault": observed.fault,
                "requested_nm": observed.requested_nm,
                "delivered_nm": observed.delivered_nm,
                "wheel_torque_nm": list(observed.wheel_torque_nm),
                "recovery_streak": decision.next.recovery_streak,
                "reference_gate_allowed": allowed,
                "reason": reason,
            },
            "clock_fault": clock_data["fault"],
            "command_allowed": allowed,
            "command_nm": command,
            "command_reason": guarded.reason if allowed else reason,
        }
        self.guard_state = g.CommandGuardState(
            tuple(command), bool(reconciled.next_latched)
        )
        self.native_clock = clock.next
        self.native_gate = decision.next
        self.sequence += 1
        return row


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cc")
    args = parser.parse_args()
    try:
        print(json.dumps(build_native_controller(args.output_dir, args.cc), indent=2))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, "native controller: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
