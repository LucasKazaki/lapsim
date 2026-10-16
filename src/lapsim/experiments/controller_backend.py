"""Incremental imported controller owners, isolated from application imports.

Original files are unchanged. Their sibling imports execute in a private
namespace; no sibling checkout or process-wide sys.path mutation is needed.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any

from lapsim.resources import repository_root

_LOCK = RLock()
_PREFIX = "_lapsim_enme408_reference"
ZERO = (0.0,) * 4
BROWSER_PYTHON_OWNERS = (
    "allocator",
    "torque_numeric",
    "allocation_contract",
    "command_guard",
    "fault_state",
    "cycle_clock",
    "guard_trusted_clear",
    "guard_overlap_observation",
    "guard_request_contract",
    "control_pipeline",
)
_INVENTORY_SHA256 = "90da35d8fa1386a1d7a12b024d2b5a32431c3d5dc36a91d6f5150599c430596e"
_PATCHES_SHA256 = "8e6e6c782e34b371bdce59147d2566da04fcbf80c890aabf35e0ecbe568dd251"


def _inventory(root: Path) -> dict:
    raw = (root.parent / "import-manifest.json").read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("controller inventory exceeds its size limit")
    manifest = json.loads(raw)
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if sha256(canonical).hexdigest() != _INVENTORY_SHA256:
        raise ValueError("reviewed controller inventory identity mismatch")
    expected = {
        Path(name).name
        for name in manifest["files"]
        if name.startswith("reference/") and name.endswith(".py")
    }
    if sys.platform == "emscripten":
        expected = {name + ".py" for name in BROWSER_PYTHON_OWNERS}
    if {p.name for p in root.glob("*.py")} != expected:
        raise ValueError("unmanifested or missing controller Python module")
    files = {name: dict(facts) for name, facts in manifest["files"].items()}
    patches_path = root.parent / "integration/relocation-patches.json"
    if patches_path.is_file():
        patches = json.loads(patches_path.read_bytes())
        encoded = json.dumps(
            patches, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if sha256(encoded).hexdigest() != _PATCHES_SHA256:
            raise ValueError("reviewed controller relocation patch identity mismatch")
        for name, facts in patches["patches"].items():
            files[name]["sha256"] = facts["current_sha256"]
    return files


def controller_module(name: str) -> ModuleType:
    root = repository_root() / "controller/reference"
    if not root.is_dir():
        raise RuntimeError(
            "The self-contained ENME408 controller source is unavailable"
        )
    inventory = _inventory(root)
    local = {
        Path(name).stem
        for name in inventory
        if name.startswith("reference/") and name.endswith(".py")
    }
    if name not in local:
        raise ValueError("unknown imported controller module")

    def load(module_name: str) -> ModuleType:
        qualified = _PREFIX + "." + module_name
        source = root / (module_name + ".py")
        with _LOCK:
            raw = source.read_bytes()
            if (
                source.is_symlink()
                or sha256(raw).hexdigest()
                != inventory["reference/" + module_name + ".py"]["sha256"]
            ):
                raise ValueError("reviewed controller module identity mismatch")
            if qualified in sys.modules:
                existing = sys.modules[qualified]
                filename = getattr(existing, "__file__", None)
                if (
                    not isinstance(filename, str)
                    or Path(filename).resolve() != source.resolve()
                ):
                    raise RuntimeError(
                        "Controller module already belongs to another checkout"
                    )
                return existing
            spec = importlib.util.spec_from_file_location(qualified, source)
            if spec is None or spec.loader is None:
                raise RuntimeError("Controller source loader is unavailable")
            module = importlib.util.module_from_spec(spec)

            def scoped_import(
                import_name, globals=None, locals=None, fromlist=(), level=0
            ):
                if level == 0 and import_name in local:
                    return load(import_name)
                return builtins.__import__(
                    import_name, globals, locals, fromlist, level
                )

            module.__dict__["__builtins__"] = dict(
                vars(builtins), __import__=scoped_import
            )
            sys.modules[qualified] = module
            try:
                # Execute the verified source bytes, never a mutable bytecode
                # cache or a second read after the identity check.
                exec(compile(raw, str(source), "exec"), module.__dict__)  # noqa: S102 -- Execute only byte-verified local owners.
            except BaseException:
                sys.modules.pop(qualified, None)
                raise
            return module

    return load(name)


def controller_source_identity() -> dict[str, Any]:
    root = repository_root()
    inventory = _inventory(root / "controller/reference")
    paths = sorted((root / "controller/reference").glob("*.py"))
    paths += sorted((root / "controller/reference/native").glob("torque_*.[ch]"))
    hashes = {}
    for path in paths:
        relative = path.relative_to(root / "controller").as_posix()
        digest = sha256(path.read_bytes()).hexdigest()
        if digest != inventory[relative]["sha256"]:
            raise ValueError("reviewed controller source identity mismatch")
        hashes[path.relative_to(root).as_posix()] = digest
    return {
        "backend": "python_reference",
        "runtime_source_scope": "browser_python_owner_subset_v1"
        if sys.platform == "emscripten"
        else "full_imported_reference_and_native_core_inputs",
        "source_files_sha256": hashes,
        "numeric_contract": "binary64 ordinary nearest rounding; no fast math",
    }


class PythonController:
    """One call advances each imported stateful owner once, outside the plant."""

    backend_id = "python_reference"

    def __init__(self, period_ms: int = 10, maximum_age_ms: int = 50):
        self.api = {
            name: controller_module(name)
            for name in (
                "allocator",
                "command_guard",
                "fault_state",
                "cycle_clock",
                "guard_trusted_clear",
                "control_pipeline",
            )
        }
        a, g, f, c = (
            self.api[name]
            for name in ("allocator", "command_guard", "fault_state", "cycle_clock")
        )
        self.config = self.api["control_pipeline"].PipelineConfig(
            a.AllocatorConfig(maximum_age_ms),
            g.CommandGuardConfig(8000.0, 0.25, 0.05),
            f.FaultPolicy(2),
            period_ms,
        )
        self.guard_state = g.CommandGuardState(ZERO)
        self.fault_state = f.FaultSnapshot(f.INHIBITED)
        self.clock_state = c.CycleClockState()
        self.sequence = 0
        self.closed = False
        self.identity = controller_source_identity()

    def step(self, sample: Any) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("controller session is closed")
        a, g, f, c = (
            self.api[name]
            for name in ("allocator", "command_guard", "fault_state", "cycle_clock")
        )
        if type(sample) is not self.api["control_pipeline"].ControlSample:
            raise ValueError("expected imported ControlSample")
        if type(sample.restart_requested) is not bool:
            raise ValueError("restart_requested must be boolean")
        if sample.restart_requested:
            self.guard_state = g.CommandGuardState(
                ZERO, self.guard_state.pedal_overlap_latched
            )
        candidate = a.allocate_propulsive_torque(
            sample.allocation, self.config.allocator
        )
        guarded = self.api["guard_trusted_clear"].apply_trusted_clear_guard(
            candidate, sample.guard, self.config.guard, self.guard_state
        )
        clock = c.observe_cycle_clock(
            self.clock_state,
            sample.allocation.now_ms,
            sample.guard.dt_s,
            self.config.period_ms,
        )
        self.clock_state = clock.next_state
        effective = candidate
        if clock.fault or guarded.status == "inhibited":
            reason = clock.fault or (
                candidate.fault if candidate.status == "fault" else guarded.reason
            )
            effective = a.AllocationResult(
                ZERO, candidate.requested_nm, 0.0, "fault", reason
            )
        self.fault_state, event = f.observe_fault_state(
            self.fault_state,
            effective,
            self.config.fault,
            sequence=self.sequence,
            restart_requested=sample.restart_requested,
        )
        allowed = (
            event.reference_gate_allowed
            and guarded.status != "inhibited"
            and clock.fault is None
        )
        command = guarded.output_nm if allowed else ZERO
        latch = guarded.next_state.pedal_overlap_latched or (
            clock.fault is not None and self.guard_state.pedal_overlap_latched
        )
        self.guard_state = g.CommandGuardState(command, latch)
        row = {
            "sequence": self.sequence,
            "now_ms": clock.now_ms,
            "restart_requested": sample.restart_requested,
            "allocator": asdict(candidate),
            "guard": {
                "status": guarded.status,
                "reason": guarded.reason,
                "output_nm": list(guarded.output_nm),
                "pedal_overlap_latched": latch,
            },
            "fault": event.as_record(),
            "clock_fault": clock.fault,
            "command_allowed": allowed,
            "command_nm": list(command),
            "command_reason": guarded.reason if allowed else event.reason,
        }
        self.sequence += 1
        return row

    def sample(
        self,
        now_ms: int,
        timestamp_ms: int,
        request_nm: float,
        limits: tuple,
        available: tuple,
        accelerator: float,
        brake: bool,
        valid: bool,
        enabled: bool,
        restart: bool = False,
    ) -> Any:
        return self.api["control_pipeline"].ControlSample(
            self.api["allocator"].AllocationInput(
                now_ms, timestamp_ms, request_nm, limits, available, enabled
            ),
            self.api["command_guard"].CommandGuardInput(
                self.config.period_ms / 1000, accelerator, brake, valid, valid, enabled
            ),
            restart,
        )

    def close(self) -> None:
        self.closed = True
