"""Compile and check the portable C prototype against the real Python owners.

Standard library only. GCC/Clang-compatible host compiler required. This builds
in a temporary folder; it has no target compiler, firmware, or live transport.
"""
from __future__ import annotations

import argparse
import ctypes as ct
from dataclasses import replace
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import traceback

from allocation_contract import allocation_contract_fault
from allocator import AllocationInput, AllocationResult, AllocatorConfig, allocate_propulsive_torque
from bench_replay import load_scenario
from command_guard import (CommandGuardConfig, CommandGuardInput, CommandGuardResult,
                           CommandGuardState)
from control_pipeline import ControlSample, PipelineConfig, replay_control_pipeline
from fault_state import FaultPolicy, FaultSnapshot
from torque_numeric import NUMERIC_CONTRACT_VERSION

ROOT = Path(__file__).resolve().parent
STATES = {"ready": 1, "limited": 2, "inhibited": 3, "recovery_pending": 4}
STATE_NAMES = {value: key for key, value in STATES.items()}
UINT32_MAX = 2**32 - 1
SOURCE_FILES = ("allocation_contract.py", "allocator.py", "fault_state.py", "control_pipeline.py", "c_parity.py",
                "bench_replay.py", "command_guard.py", "guard_request_contract.py", "guard_overlap_observation.py",
                "guard_trusted_clear.py", "torque_numeric.py", "bench-scenario.example.json", "native/torque_contract.c", "native/torque_contract.h",
                "cycle_clock.py", "native/torque_clock.c", "native/torque_clock.h",
                "native/torque_pedal.c", "native/torque_pedal.h")


class Scalar(ct.Structure):
    _fields_ = [("value", ct.c_double), ("numeric", ct.c_uint8)]


class Text(ct.Structure):
    _fields_ = [("kind", ct.c_uint8), ("value", ct.c_char * 64)]


class Allocation(ct.Structure):
    _fields_ = [("type_valid", ct.c_uint8), ("status", ct.c_uint8),
                ("wheel_vector_valid", ct.c_uint8), ("wheels", Scalar * 4),
                ("requested", Scalar), ("delivered", Scalar), ("fault", Text)]


class Guard(ct.Structure):
    _fields_ = [("status", ct.c_uint8), ("output_valid", ct.c_uint8),
                ("output", Scalar * 4), ("reason", Text)]


class Snapshot(ct.Structure):
    _fields_ = [("state", ct.c_uint8), ("recovery_streak", ct.c_uint32), ("generation", ct.c_uint32)]


class Policy(ct.Structure):
    _fields_ = [("valid_samples_to_recover", ct.c_uint32)]


class Cycle(ct.Structure):
    _fields_ = [("allocation", Allocation), ("guard", Guard), ("clock_fault", Text),
                ("restart_requested", ct.c_uint8)]


class Decision(ct.Structure):
    _fields_ = [("next", Snapshot), ("command_allowed", ct.c_uint8), ("command", ct.c_double * 4),
                ("reason", ct.c_char * 64), ("contract_code", ct.c_uint32)]


def scalar(value: object) -> Scalar:
    if type(value) not in (int, float):
        return Scalar(0., 0)
    try:
        return Scalar(float(value), 1)
    except (ValueError, OverflowError):
        return Scalar(0., 0)


def text(value: object) -> Text:
    if value is None:
        return Text(0, b"")
    if type(value) is not str:
        return Text(2, b"")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        return Text(2, b"")
    if len(encoded) > 63 or b"\0" in encoded:
        return Text(2, b"")
    return Text(1, encoded)


def allocation(candidate: object) -> Allocation:
    result = Allocation()
    if type(candidate) is not AllocationResult:
        return result
    result.type_valid = 1
    if type(candidate.status) is str:
        result.status = {"ok": 1, "saturated": 2, "fault": 3}.get(candidate.status, 0)
    wheels = candidate.wheel_torque_nm
    if type(wheels) in (tuple, list) and len(wheels) == 4:
        result.wheel_vector_valid = 1
        for index, value in enumerate(wheels):
            result.wheels[index] = scalar(value)
    result.requested = scalar(candidate.requested_nm)
    result.delivered = scalar(candidate.delivered_nm)
    result.fault = text(candidate.fault)
    return result


def guard(result: CommandGuardResult) -> Guard:
    packed = Guard()
    if type(result) is not CommandGuardResult:
        return packed
    if type(result.status) is str:
        packed.status = {"ok": 1, "limited": 2, "inhibited": 3}.get(result.status, 0)
    if type(result.output_nm) in (tuple, list) and len(result.output_nm) == 4:
        packed.output_valid = 1
        for index, value in enumerate(result.output_nm):
            packed.output[index] = scalar(value)
    packed.reason = text(result.reason)
    return packed


def uint32(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= UINT32_MAX:
        raise ValueError(f"{label} is outside the C uint32 domain")
    return value


def find_compiler(explicit: str | None = None) -> str:
    if explicit is None and os.environ.get("CC"):
        explicit = os.environ["CC"]
    if explicit:
        found = shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
        if not found:
            raise ValueError(f"compiler was not found: {explicit}")
        return str(Path(found).resolve())
    for name in ("gcc", "clang", "cc"):
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
    # Known installed MSYS2 toolchain on this Windows workstation; callers can
    # override it with --cc / CC. No automatic acquisition or target selection.
    installed = Path("C:/msys64/mingw64/bin/gcc.exe")
    if sys.platform == "win32" and installed.is_file():
        return str(installed)
    raise ValueError("a GCC/Clang-compatible host compiler is required (--cc or CC)")


def build_library(folder: Path, compiler: str | None = None):
    compiler = find_compiler(compiler)
    version = subprocess.run([compiler, "--version"], check=True, capture_output=True,
                             text=True, errors="replace", timeout=15).stdout.splitlines()[0]
    suffix = ".dll" if sys.platform == "win32" else ".so"
    target = folder / ("torque_contract" + suffix)
    flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fno-fast-math", "-fexcess-precision=standard", "-shared"]
    # MinGW otherwise hashes the temporary output path into its preferred
    # image base, changing identical-source binary hashes. Keep ASLR enabled;
    # only the linker's preferred base and PE timestamp are made repeatable.
    flags += (["-static-libgcc", "-Wl,--no-insert-timestamp", "-Wl,--image-base,0x180000000"]
              if sys.platform == "win32" else ["-fPIC"])
    args = [compiler, *flags, "torque_contract.c", "torque_clock.c", "torque_pedal.c", "-o", str(target), "-lm"]
    build_env = dict(os.environ)
    # GCC's cc1/as/linker helpers live below the toolchain directory on
    # Windows; give only this subprocess its sibling runtime DLL search path.
    build_env["PATH"] = str(Path(compiler).parent) + os.pathsep + build_env.get("PATH", "")
    completed = subprocess.run(args, cwd=ROOT / "native", capture_output=True,
                               text=True, errors="replace", timeout=60, env=build_env)
    if completed.returncode:
        raise ValueError(f"C build failed (exit {completed.returncode}):\n" + completed.stdout + completed.stderr)
    return target, {"compiler": compiler, "version": version, "flags": flags,
                    "binary_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "build_diagnostics": completed.stdout + completed.stderr}


class Core:
    def __init__(self, library: Path):
        self.library = ct.CDLL(str(library.resolve()))
        lib = self.library
        lib.tc_abi_version.argtypes, lib.tc_abi_version.restype = [], ct.c_uint32
        lib.tc_numeric_contract_version.argtypes, lib.tc_numeric_contract_version.restype = [], ct.c_uint32
        lib.tc_abi_sizeof.argtypes, lib.tc_abi_sizeof.restype = [ct.c_uint32], ct.c_size_t
        lib.tc_validate_allocation.argtypes = [ct.POINTER(Allocation)]
        lib.tc_validate_allocation.restype = ct.c_uint32
        lib.tc_contract_reason.argtypes, lib.tc_contract_reason.restype = [ct.c_uint32], ct.c_char_p
        lib.tc_decide.argtypes = [ct.POINTER(Snapshot), ct.POINTER(Cycle), ct.POINTER(Policy), ct.POINTER(Decision)]
        lib.tc_decide.restype = ct.c_uint32
        lib.tc_init_snapshot.argtypes, lib.tc_init_snapshot.restype = [ct.POINTER(Snapshot)], None
        if lib.tc_abi_version() != 1:
            raise ValueError("C ABI version mismatch")
        if lib.tc_numeric_contract_version() != NUMERIC_CONTRACT_VERSION:
            raise ValueError("C numeric contract version mismatch")
        kinds = (Scalar, Text, Allocation, Guard, Snapshot, Policy, Cycle, Decision)
        self.sizes = {kind.__name__: ct.sizeof(kind) for kind in kinds}
        for number, kind in enumerate(kinds, 1):
            if lib.tc_abi_sizeof(number) != ct.sizeof(kind):
                raise ValueError(f"C ABI size mismatch for {kind.__name__}")

    def validate(self, candidate: object) -> str | None:
        packed = allocation(candidate)
        code = self.library.tc_validate_allocation(ct.byref(packed))
        return self.library.tc_contract_reason(code).decode("ascii") if code else None

    def decide_raw(self, previous: Snapshot, cycle: Cycle, policy: Policy):
        output = Decision()
        code = self.library.tc_decide(ct.byref(previous), ct.byref(cycle), ct.byref(policy), ct.byref(output))
        if code:
            raise ValueError("C decision call rejected an argument")
        return output


def _packed_signature(value):
    """Architecture-independent description, excluding struct padding."""
    if isinstance(value, Scalar):
        return {"numeric": value.numeric, "value_hex": value.value.hex()}
    if isinstance(value, Text):
        return {"kind": value.kind, "bytes_hex": bytes(value.value).hex()}
    if isinstance(value, ct.Array):
        return [_packed_signature(item) for item in value]
    if isinstance(value, ct.Structure):
        return {name: _packed_signature(getattr(value, name)) for name, _ in value._fields_}
    if isinstance(value, float):
        return value.hex()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _digest_add(digest, value):
    digest.update(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n")


def contract_cases(seed=408, random_cases=2000):
    good = AllocationResult((10.,) * 4, 40., 40., "ok", None)
    cases = [("ordinary", good), ("wrong_object", None),
             ("negative_fault_request", replace(good, wheel_torque_nm=(0.,) * 4, requested_nm=-5.,
                                                delivered_nm=0., status="fault", fault="negative_request_unsupported"))]
    for label, values in (
        ("status", [None, [], {}, True, "", "OK", "fault", "saturated"]),
        ("requested_nm", [None, True, "40", -1., math.nan, math.inf, 10**400, 0., 20.]),
        ("delivered_nm", [None, False, "40", -1., math.nan, math.inf, 10**400, 0., 20.]),
        ("wheel_torque_nm", [None, b"1234", (10.,) * 3, (10.,) * 5, (True, 10., 10., 10.),
                             (math.nan, 10., 10., 10.), (1e308,) * 4, (10**400, 0., 0., 0.)]),
        ("fault", [[], {}, False, "", "external_interlock_open", "aggregate_limit"]),
    ):
        for index, value in enumerate(values):
            field = "status" if label == "status" else label
            cases.append((f"{label}_{index}", replace(good, **{field: value})))
    for base in (0., math.ulp(0.), 1e-320, sys.float_info.min, 1e-12, .3, 1., 40., 1e100, sys.float_info.max):
        requested = base
        for step in range(12):
            cases.append((f"ulp_{base.hex()}_{step}", AllocationResult((base, 0., 0., 0.), requested, base, "ok", None)))
            requested = math.nextafter(requested, 0.)
        cases.append((f"sum_{base.hex()}", AllocationResult((base/4.,) * 4, base, base, "ok", None)))
    class Trap(float):
        def __float__(self):
            raise AssertionError("custom numeric conversion must never run")
    class PretendOK:
        def __eq__(self, other):
            raise AssertionError("custom status comparison must never run")
    cases.extend((("numeric_subclass", replace(good, requested_nm=Trap(40.))),
                  ("status_spoof", replace(good, status=PretendOK())),
                  ("utf8_diagnostic", replace(good, wheel_torque_nm=(0.,) * 4, delivered_nm=0.,
                                               status="fault", fault="stale_μ"))))
    # A local-model review proposed accepting this vector. The independent
    # Python source contract rejects its real sum discrepancy; keep the exact
    # counterexample rather than changing policy to follow model output.
    cases.append(("local_model_DBL_MIN_sum_mismatch", AllocationResult(
        (sys.float_info.min, 0., 0., 0.), 2*sys.float_info.min, 2*sys.float_info.min, "ok", None)))
    unit = math.ulp(1.5)
    for direction, delivered in (("below", 1.5-8*unit), ("above", 1.5+9*unit)):
        cases.append(("independent_mixed_scale_" + direction,
                      AllocationResult((1.5, unit/2, unit/2, 0.), 2., delivered, "ok", None)))
    rng = random.Random(seed)
    for index in range(random_cases):
        inp = AllocationInput(1000, 1000 if index % 11 else 0, rng.uniform(0., 1000.),
                              tuple(rng.uniform(0., 200.) for _ in range(4)),
                              tuple(bool(rng.getrandbits(1)) for _ in range(4)), index % 17 != 0)
        candidate = allocate_propulsive_torque(inp, AllocatorConfig(50))
        if index % 5 == 0 and candidate.status != "fault":
            candidate = replace(candidate, requested_nm=candidate.delivered_nm * .5)
        if index % 7 == 0:
            candidate = replace(candidate, fault="external_interlock_open")
        cases.append((f"seeded_{index}", candidate))
    return cases


def pipeline_scenarios(seed=408, sequences=128, length=64):
    raw = (ROOT / "bench-scenario.example.json").read_bytes()
    _, config, samples = load_scenario(raw)
    yield "published_example", config, samples
    rng = random.Random(seed)
    for sequence in range(sequences):
        samples = []
        tick = 0
        for index in range(length):
            # Some sequences deliberately stay healthy so positive/recovery
            # behavior is exercised alongside adversarial heavily held runs.
            ordinary = sequence % 4 == 0
            tick += 50 if ordinary or rng.random() > .03 else rng.choice((0, 25, 100))
            now = tick
            stamp = now if ordinary or rng.random() > .06 else max(0, now-100)
            request = rng.uniform(0., 250.) if ordinary or rng.random() > .03 else -5.
            inp = AllocationInput(now, stamp, request, tuple(rng.uniform(10., 100.) for _ in range(4)),
                                  (True,) * 4, ordinary or rng.random() > .02)
            guard_input = CommandGuardInput(.05 if ordinary or rng.random() > .02 else 100.,
                rng.uniform(0., .5) if ordinary else rng.random(),
                False if ordinary else rng.random() < .15,
                ordinary or rng.random() > .04, ordinary or rng.random() > .03,
                ordinary or rng.random() > .02)
            samples.append(ControlSample(inp, guard_input, index > 0 and rng.random() < .03))
        yield f"seeded_sequence_{sequence}", config, samples


def run_parity(core: Core, *, random_cases=2000, sequences=128):
    contract_digest, decision_digest = hashlib.sha256(), hashlib.sha256()
    contract_codes = {}
    count = 0
    for label, candidate in contract_cases(random_cases=random_cases):
        expected, actual = allocation_contract_fault(candidate), core.validate(candidate)
        if expected != actual:
            raise AssertionError(f"C/Python allocation disagreement {label}: {expected!r} vs {actual!r}")
        _digest_add(contract_digest, {"label": label, "candidate": _packed_signature(allocation(candidate)), "reason": actual})
        contract_codes[actual or "accepted"] = contract_codes.get(actual or "accepted", 0) + 1
        count += 1
    stats = {"cycles": 0, "allowed_cycles": 0, "held_cycles": 0, "clock_fault_cycles": 0, "restarts": 0}
    states = {}
    for label, config, samples in pipeline_scenarios(sequences=sequences):
        rows = replay_control_pipeline(samples, config)
        snapshot = Snapshot()
        core.library.tc_init_snapshot(ct.byref(snapshot))
        policy = Policy(uint32(config.fault.valid_samples_to_recover, "recovery policy"))
        for row in rows:
            result = AllocationResult(**row["allocator"])
            guard_row = row["guard"]
            guarded = CommandGuardResult(tuple(guard_row["output_nm"]),
                CommandGuardState(tuple(guard_row["output_nm"]), guard_row["pedal_overlap_latched"]),
                guard_row["status"], guard_row["reason"])
            cycle = Cycle(allocation(result), guard(guarded), text(row["clock_fault"]), row["restart_requested"])
            output = core.decide_raw(snapshot, cycle, policy)
            actual = {"next_state": STATE_NAMES[output.next.state], "recovery_streak": output.next.recovery_streak,
                      "generation": output.next.generation, "command_allowed": bool(output.command_allowed),
                      "command_nm": list(output.command), "reason": bytes(output.reason).decode("utf-8")}
            expected = {"next_state": row["fault"]["next_state"], "recovery_streak": row["fault"]["recovery_streak"],
                        "generation": row["fault"]["generation"], "command_allowed": row["command_allowed"],
                        "command_nm": row["command_nm"], "reason": row["fault"]["reason"]}
            if actual != expected:
                raise AssertionError(f"C/Python decision disagreement in {label} cycle {row['sequence']}: {expected!r} vs {actual!r}")
            if not output.command_allowed and any(value != 0. for value in output.command):
                raise AssertionError("inhibited C command is not exactly zero")
            _digest_add(decision_digest, {"scenario": label, "sequence": row["sequence"],
                "previous": _packed_signature(snapshot), "input": _packed_signature(cycle), "result": actual})
            snapshot = output.next
            stats["cycles"] += 1
            stats["allowed_cycles"] += bool(output.command_allowed)
            stats["held_cycles"] += not output.command_allowed
            stats["clock_fault_cycles"] += row["clock_fault"] is not None
            stats["restarts"] += row["restart_requested"]
            states[actual["next_state"]] = states.get(actual["next_state"], 0) + 1
    return {"allocation_cases": count, "allocation_reasons": contract_codes,
            "allocation_results_sha256": contract_digest.hexdigest(),
            "decision_results_sha256": decision_digest.hexdigest(), "decision_states": states, **stats}


def check_boundaries(core: Core):
    """Compiled C-only representability and pointer/counter guard cases.

    These intentionally extend the unbounded Python data model. They claim
    fail-closed behavior, not parity for values the C interface cannot encode.
    """
    checks = []
    candidate = AllocationResult((10.,) * 4, 40., 40., "ok", None)
    guarded = CommandGuardResult((10.,) * 4, CommandGuardState((10.,) * 4), "ok", None)
    def fresh():
        return Snapshot(1, 0, 0), Cycle(allocation(candidate), guard(guarded), text(None), 0), Policy(2)
    def require(condition, label):
        if not condition:
            raise AssertionError("C boundary failed: " + label)
        checks.append(label)
    def held(snapshot, cycle, policy, reason, label):
        result = core.decide_raw(snapshot, cycle, policy)
        require(result.command_allowed == 0 and tuple(result.command) == (0.,) * 4 and
                result.next.state == 3 and result.next.recovery_streak == 0 and
                bytes(result.reason).decode() == reason, label)
        return result
    previous, cycle, policy = fresh()
    allowed = core.decide_raw(previous, cycle, policy)
    require(bool(allowed.command_allowed) and tuple(allowed.command) == (10.,) * 4, "ordinary_ready_command")
    for field in ("status", "output_valid"):
        previous, cycle, policy = fresh()
        setattr(cycle.guard, field, 255)
        held(previous, cycle, policy, "invalid_guard_result", "guard_" + field)
    for value in (Scalar(math.nan, 1), Scalar(math.inf, 1), Scalar(10., 255), Scalar(20., 1)):
        previous, cycle, policy = fresh()
        cycle.guard.output[0] = value
        held(previous, cycle, policy, "invalid_guard_result", "invalid_guard_scalar_" + str(len(checks)))
    previous, cycle, policy = fresh()
    cycle.guard.status, cycle.guard.reason = 3, text("guard_inhibit")
    held(previous, cycle, policy, "invalid_guard_result", "inhibited_guard_cannot_carry_positive_output")
    for change, label in (("clock_invalid", "invalid_clock_tag"), ("clock_empty", "empty_clock_fault"),
                          ("restart", "invalid_restart_boolean")):
        previous, cycle, policy = fresh()
        if change == "clock_invalid": cycle.clock_fault.kind = 255
        elif change == "clock_empty": cycle.clock_fault = text("")
        else: cycle.restart_requested = 255
        held(previous, cycle, policy, "invalid_cycle_flags", label)
    previous, cycle, policy = fresh()
    previous.state = 255
    held(previous, cycle, policy, "invalid_snapshot_state", "invalid_snapshot")
    previous, cycle, policy = fresh()
    policy.valid_samples_to_recover = 0
    held(previous, cycle, policy, "invalid_recovery_policy", "zero_recovery_policy")
    previous, cycle, policy = fresh()
    previous.generation, cycle.restart_requested = UINT32_MAX, 1
    result = held(previous, cycle, policy, "counter_overflow", "restart_generation_overflow")
    require(result.next.generation == UINT32_MAX, "generation_never_wraps")
    for state in (3, 4):
        previous, cycle, policy = fresh()
        previous.state, previous.recovery_streak = state, UINT32_MAX
        held(previous, cycle, policy, "counter_overflow", "recovery_streak_overflow_state_" + str(state))
    previous.recovery_streak, policy.valid_samples_to_recover = UINT32_MAX-1, UINT32_MAX
    result = core.decide_raw(previous, cycle, policy)
    require(bool(result.command_allowed) and result.next.recovery_streak == UINT32_MAX,
            "last_representable_recovery_count")
    for tag in (0, 2, 255):
        packed = allocation(candidate)
        packed.requested.numeric = tag
        code = core.library.tc_validate_allocation(ct.byref(packed))
        require(code == 6, "numeric_tag_" + str(tag))
    for tag in (0, 2):
        for field, expected_code in (("type_valid", 1), ("wheel_vector_valid", 3)):
            packed = allocation(candidate)
            setattr(packed, field, tag)
            require(core.library.tc_validate_allocation(ct.byref(packed)) == expected_code,
                    field + "_tag_" + str(tag))
    packed = allocation(candidate)
    ct.memset(ct.addressof(packed.fault)+Text.value.offset, 65, 64)
    require(core.library.tc_validate_allocation(ct.byref(packed)) == 0, "none_fault_ignores_buffer")
    for packed in (allocation(replace(candidate, fault=[])), allocation(replace(candidate, fault="x"*64)),
                   allocation(replace(candidate, fault="abc\0def"))):
        code = core.library.tc_validate_allocation(ct.byref(packed))
        require(code == 7, "unrepresentable_diagnostic_" + str(len(checks)))
    packed = allocation(candidate)
    packed.fault.kind = 1
    ct.memset(ct.addressof(packed.fault)+Text.value.offset, 65, 64)
    require(core.library.tc_validate_allocation(ct.byref(packed)) == 7, "unterminated_text_buffer")
    previous, cycle, policy = fresh()
    output = Decision()
    ct.memset(ct.addressof(output), 255, ct.sizeof(output))
    code = core.library.tc_decide(None, ct.byref(cycle), ct.byref(policy), ct.byref(output))
    require(code == 1 and output.command_allowed == 0 and tuple(output.command) == (0.,)*4 and
            output.next.state == 3, "null_input_initializes_exact_zero")
    require(core.library.tc_decide(ct.byref(previous), ct.byref(cycle), ct.byref(policy), None) == 1,
            "null_output_rejected")
    require(core.library.tc_validate_allocation(None) == 1, "null_allocation_rejected")
    require(core.library.tc_abi_sizeof(999) == 0, "unknown_abi_kind")
    core.library.tc_init_snapshot(None)
    return checks


def _worker(library, sender):
    try:
        core = Core(Path(library))
        boundaries = check_boundaries(core)
        first, second = run_parity(core), run_parity(core)
        if first != second:
            raise AssertionError("repeated C/Python experiment changed its deterministic results")
        sender.send({"results": first, "abi_sizes": core.sizes, "boundary_checks": boundaries})
    except BaseException:
        sender.send({"error": traceback.format_exc()})
    finally:
        sender.close()


def verify_in_child(library: Path):
    """Let the OS release the loaded DLL before parent-owned temp cleanup.

    A child also confines any unexpected native crash to this finite test, not
    the calling process. No private ctypes unload hooks or retained jobs used.
    """
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(str(library), sender))
    process.start()
    sender.close()
    try:
        if not receiver.poll(120):
            raise RuntimeError("C parity child did not return within 120 seconds")
        result = receiver.recv()
        process.join(10)
        if process.is_alive() or process.exitcode != 0:
            raise RuntimeError(f"C parity child did not exit cleanly: {process.exitcode}")
        if "error" in result:
            raise RuntimeError(result["error"])
        return result
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    sources = [ROOT/name for name in SOURCE_FILES]
    if any(args.output.resolve() == source.resolve() or
           (args.output.exists() and args.output.samefile(source)) for source in sources):
        parser.error("output must not overwrite a reference source or its hardlink")
    with tempfile.TemporaryDirectory(prefix="enme408-c-parity-") as directory:
        library, build = build_library(Path(directory), args.cc)
        result = verify_in_child(library)
        receipt = {"schema": "enme408-portable-c-parity/v2", "scope": "host prototype; no target/hardware validation",
                   "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
                   "abi_version": 1, "abi_sizes": result["abi_sizes"], "seed": 408, "repeat_agreement": True,
                   "build": build, "results": result["results"], "boundary_checks": result["boundary_checks"],
                   "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
                   "limits": ["binary64 without fast-math", "UTF-8 diagnostic identifiers <=63 bytes without embedded NUL",
                              "uint32 counters; overflow inhibits", "upstream allocator/guard not ported; clock verified separately",
                              "no MCU timing, memory budget, transport, motor mapping or shutdown certification"]}
    # Publish a receipt only after the child exits and temporary build cleanup
    # succeeds; a failed lifecycle must not masquerade as a successful CLI run.
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result["results"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
