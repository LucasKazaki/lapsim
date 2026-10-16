"""Offline compiled base-guard ownership and composed proposed-command parity."""
from __future__ import annotations

import argparse
import ctypes as ct
from dataclasses import replace
import hashlib
import itertools
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import traceback

from allocator import AllocationInput, AllocationResult, AllocatorConfig, allocate_propulsive_torque
from command_guard import (CommandGuardConfig, CommandGuardInput, CommandGuardState,
                           CommandGuardResult, apply_command_guard)
from control_pipeline import ControlSample, PipelineConfig, replay_control_pipeline
from fault_state import FaultPolicy
from c_parity import (ROOT, Allocation, Guard, Scalar, Snapshot, Policy, Cycle,
                      STATE_NAMES, allocation, scalar, guard, find_compiler,
                      _digest_add, _packed_signature)
from clock_parity import ClockState, clock_input, clock_policy, unpack, composition_scenarios
from pedal_parity import (PedalCore, facts, adapted, boolean, source_adapter_cases,
                          SOURCE_FILES as PEDAL_SOURCES)

PROTOCOL = ROOT / "../research/TC-03F-base-command-guard-protocol.json"
PROTOCOL_SHA256 = "dae91039428cd0e4d55596d5e99734acebc59378100b2984fda80e1e80babff2"
VERSION, SEED = 1, 411
ZERO = (0.0,) * 4
SOURCE_FILES = (*PEDAL_SOURCES, "guard_parity.py", "native/torque_guard.c",
                "native/torque_guard.h", "native/guard_sanitizer_probe.c",
                "../research/TC-03F-base-command-guard-protocol.json")


class GuardConfig(ct.Structure):
    _fields_ = [("type_valid", ct.c_uint8), ("max_rise", Scalar),
                ("trip", Scalar), ("clear", Scalar)]


class GuardInput(ct.Structure):
    _fields_ = [("type_valid", ct.c_uint8), ("dt_s", Scalar), ("accelerator", Scalar),
                ("brake", ct.c_uint8), ("comms", ct.c_uint8),
                ("sensors", ct.c_uint8), ("interlock", ct.c_uint8)]


class GuardState(ct.Structure):
    _fields_ = [("type_valid", ct.c_uint8), ("previous_vector_valid", ct.c_uint8),
                ("previous_latched", ct.c_uint8), ("previous", Scalar * 4)]


class GuardResult(ct.Structure):
    _fields_ = [("guard", Guard), ("next", GuardState), ("contract_code", ct.c_uint32)]


def config(value):
    result = GuardConfig()
    result.type_valid = type(value) is CommandGuardConfig
    if result.type_valid:
        result.max_rise, result.trip, result.clear = map(scalar,
            (value.max_rise_nm_per_s, value.pedal_overlap_trip_fraction, value.pedal_clear_fraction))
    return result


def guard_input(value):
    result = GuardInput()
    result.type_valid = type(value) is CommandGuardInput
    if result.type_valid:
        result.dt_s, result.accelerator = scalar(value.dt_s), scalar(value.accelerator_fraction)
        result.brake, result.comms, result.sensors, result.interlock = map(boolean,
            (value.brake_active, value.critical_comms_ok, value.sensor_agreement_ok, value.external_interlock))
    return result


def state(value):
    result = GuardState()
    result.type_valid = type(value) is CommandGuardState
    if result.type_valid:
        result.previous_latched = boolean(value.pedal_overlap_latched)
        vector = value.previous_output_nm
        if type(vector) in (tuple, list) and len(vector) == 4:
            result.previous_vector_valid = 1
            for index, number in enumerate(vector): result.previous[index] = scalar(number)
    return result


def decoded(result):
    reason = bytes(result.guard.reason.value).decode("ascii") if result.guard.reason.kind else None
    return CommandGuardResult(tuple(s.value for s in result.guard.output),
        CommandGuardState(tuple(s.value for s in result.next.previous), bool(result.next.previous_latched)),
        {1: "ok", 2: "limited", 3: "inhibited"}[result.guard.status], reason)


def signature(result):
    return {"output_hex": [float(v).hex() for v in result.output_nm],
        "previous_hex": [float(v).hex() for v in result.next_state.previous_output_nm],
        "latched": result.next_state.pedal_overlap_latched, "status": result.status, "reason": result.reason}


def frozen_protocol():
    raw = PROTOCOL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("frozen command-guard protocol changed")
    protocol = json.loads(raw)
    for name, identity in protocol["sources"].items():
        normalized = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(normalized).hexdigest() != identity["lf_normalized_sha256"]:
            raise ValueError("frozen guard owner changed: " + name)
    return protocol


def build_guard_library(folder, compiler=None):
    """Separate four-unit build; historical three-unit builder stays intact."""
    frozen_protocol()
    compiler = find_compiler(compiler)
    version = subprocess.run([compiler, "--version"], capture_output=True, text=True,
                             errors="replace", check=True, timeout=15).stdout.splitlines()[0]
    target = folder / ("torque_guard.dll" if sys.platform == "win32" else "torque_guard.so")
    flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fno-fast-math",
             "-fno-finite-math-only", "-ffp-contract=off", "-fexcess-precision=standard", "-shared"]
    flags += (["-static-libgcc", "-Wl,--no-insert-timestamp", "-Wl,--image-base,0x180000000"]
              if sys.platform == "win32" else ["-fPIC"])
    args = [compiler, *flags, "torque_contract.c", "torque_clock.c", "torque_pedal.c",
            "torque_guard.c", "-o", str(target), "-lm"]
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(args, cwd=ROOT / "native", env=env, capture_output=True,
                            text=True, errors="replace", timeout=60)
    if result.returncode: raise ValueError("guard C build failed:\n" + result.stdout + result.stderr)
    return target, {"compiler": compiler, "version": version, "flags": flags, "argv": args,
        "binary_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "build_diagnostics": result.stdout + result.stderr}


class GuardCore(PedalCore):
    def __init__(self, library):
        super().__init__(library)
        lib = self.library
        lib.tc_command_guard_version.argtypes, lib.tc_command_guard_version.restype = [], ct.c_uint32
        lib.tc_command_guard_abi_sizeof.argtypes, lib.tc_command_guard_abi_sizeof.restype = [ct.c_uint32], ct.c_size_t
        lib.tc_init_command_guard_state.argtypes, lib.tc_init_command_guard_state.restype = [ct.POINTER(GuardState)], None
        lib.tc_apply_command_guard.argtypes = [ct.POINTER(Allocation), ct.POINTER(GuardInput),
            ct.POINTER(GuardConfig), ct.POINTER(GuardState), ct.POINTER(GuardResult)]
        lib.tc_apply_command_guard.restype = ct.c_uint32
        if lib.tc_command_guard_version() != VERSION: raise ValueError("command guard version mismatch")
        self.guard_sizes = {kind.__name__: ct.sizeof(kind) for kind in (GuardConfig, GuardInput, GuardState, GuardResult)}
        for number, kind in enumerate((GuardConfig, GuardInput, GuardState, GuardResult), 1):
            if lib.tc_command_guard_abi_sizeof(number) != ct.sizeof(kind): raise ValueError("guard ABI size mismatch")

    def apply_raw(self, candidate, inp, cfg, previous):
        result = GuardResult()
        if self.library.tc_apply_command_guard(ct.byref(candidate), ct.byref(inp),
                ct.byref(cfg), ct.byref(previous), ct.byref(result)):
            raise ValueError("required guard pointer rejected")
        return result

    def apply(self, candidate, inp, cfg, previous):
        return self.apply_raw(allocation(candidate), guard_input(inp), config(cfg), state(previous))


def ordinary():
    return (AllocationResult((10.,) * 4, 40., 40., "ok", None),
        CommandGuardInput(.05, .3, False, True, True, True),
        CommandGuardConfig(100., .6, .2), CommandGuardState(ZERO))


def one_slot(value, status="ok"):
    return AllocationResult((value, 0., 0., 0.), value, value, status,
                            "aggregate_limit" if status == "saturated" else None)


def direct_cases():
    yield from source_adapter_cases()
    cand, inp, cfg, previous = ordinary()
    yield replace(cand, delivered_nm=41.), inp, cfg, previous
    yield AllocationResult(ZERO, -1., 0., "fault", "invalid_request"), inp, cfg, previous
    malformed = (None, True, "0", math.nan, math.inf, -math.inf, -1., 10**400)
    for bad in malformed:
        for field in ("dt_s", "accelerator_fraction", "brake_active", "critical_comms_ok", "sensor_agreement_ok", "external_interlock"):
            yield cand, replace(inp, **{field: bad}), cfg, previous
        for field in ("max_rise_nm_per_s", "pedal_overlap_trip_fraction", "pedal_clear_fraction"):
            yield cand, inp, replace(cfg, **{field: bad}), previous
        for index in range(4):
            values = [0.] * 4; values[index] = bad
            yield cand, inp, cfg, replace(previous, previous_output_nm=values)
            yield replace(cand, wheel_torque_nm=values), inp, cfg, previous
        for field in ("requested_nm", "delivered_nm", "status", "fault"):
            yield replace(cand, **{field: bad}), inp, cfg, previous
    for vector in (None, b"0000", {}, (), [0.] * 3, [0.] * 5):
        yield cand, inp, cfg, replace(previous, previous_output_nm=vector)
        yield replace(cand, wheel_torque_nm=vector), inp, cfg, previous
    # Multiple faults prove precedence rather than merely individual rejection.
    for bits in itertools.product((False, True), repeat=8):
        candidate = None if bits[7] else cand
        input_value = replace(inp, dt_s=0. if bits[4] else .05,
            accelerator_fraction=2. if bits[5] else .3, brake_active=2 if bits[6] else False)
        policy = replace(cfg, max_rise_nm_per_s=0. if bits[1] else 100.,
            pedal_clear_fraction=.6 if bits[2] else .2)
        prior = replace(previous, pedal_overlap_latched=2 if bits[0] else False,
            previous_output_nm=() if bits[3] else ZERO)
        yield candidate, input_value, policy, prior
    neighbors = (0., math.nextafter(.2, -math.inf), .2, math.nextafter(.2, math.inf),
                 math.nextafter(.6, -math.inf), .6, math.nextafter(.6, math.inf), 1.)
    for trip, clear, accel, brake, latch in itertools.product((.2, .6, 1.),
            (0., .2, .6), neighbors, (False, True), (False, True)):
        yield cand, replace(inp, accelerator_fraction=accel, brake_active=brake), replace(cfg,
            pedal_overlap_trip_fraction=trip, pedal_clear_fraction=clear), replace(previous, pedal_overlap_latched=latch)
    maximum = sys.float_info.max
    for rate, dt, prior, target, status in itertools.product(
            (5e-324, sys.float_info.min, 1e-12, 100., maximum),
            (5e-324, sys.float_info.min, .05, 1., maximum),
            (0., 1., maximum * .75),
            (5e-324, 1e-12, math.nextafter(1e-12, math.inf), maximum), ("ok", "saturated")):
        yield one_slot(target, status), replace(inp, dt_s=dt), replace(cfg, max_rise_nm_per_s=rate), CommandGuardState((prior, 0., 0., 0.))
    yield AllocationResult((-0.,) * 4, -0., -0., "ok", None), inp, cfg, previous


def corner_cases():
    cand, inp, cfg, previous = ordinary()
    maximum = sys.float_info.max
    yield "negative_zero", AllocationResult((-0.,) * 4, -0., -0., "ok", None), inp, cfg, previous
    yield "addition_overflow", one_slot(maximum), replace(inp, dt_s=1.), replace(cfg,
        max_rise_nm_per_s=maximum * .75), CommandGuardState((maximum * .75, 0., 0., 0.))
    yield "underflow_epsilon_label", one_slot(5e-324), replace(inp, dt_s=5e-324), replace(cfg,
        max_rise_nm_per_s=5e-324), previous
    yield "above_epsilon_label", one_slot(math.nextafter(1e-12, math.inf)), replace(inp, dt_s=1.), replace(cfg,
        max_rise_nm_per_s=5e-324), previous
    yield "immediate_decrease", one_slot(1.), replace(inp, dt_s=5e-324), replace(cfg,
        max_rise_nm_per_s=5e-324), CommandGuardState((10., 0., 0., 0.))
    yield "raw_fault_clear", AllocationResult(ZERO, -1., 0., "fault", "invalid_request"), replace(inp,
        accelerator_fraction=.1), cfg, CommandGuardState(ZERO, True)
    yield "trip_before_comms", cand, replace(inp, accelerator_fraction=.8, brake_active=True,
        critical_comms_ok=False), cfg, previous
    yield "raw_invalid_dt_missed_trip", cand, replace(inp, dt_s=0., accelerator_fraction=.8,
        brake_active=True), cfg, previous


def guarded_composition_scenarios():
    yield from composition_scenarios()
    cfg = PipelineConfig(AllocatorConfig(50), CommandGuardConfig(100., .6, .2), FaultPolicy(2), 50)
    changes = ({}, {}, {"accelerator_fraction": .8, "brake_active": True, "critical_comms_ok": False},
        {"accelerator_fraction": .1, "critical_comms_ok": False}, {"accelerator_fraction": .1},
        {"accelerator_fraction": .8}, {"dt_s": 0., "accelerator_fraction": .8, "brake_active": True},
        {"accelerator_fraction": .1}, {"accelerator_fraction": .8, "brake_active": True},
        {"accelerator_fraction": .1, "external_interlock": False},
        {"accelerator_fraction": .1, "sensor_agreement_ok": False},
        {"accelerator_fraction": .1}, {"accelerator_fraction": .1}, {"accelerator_fraction": .8})
    samples = []
    for index, overrides in enumerate(changes):
        tick = index * 50
        source_tick = 0 if index == 11 else tick
        samples.append(ControlSample(AllocationInput(tick, source_tick, 40., (100.,) * 4, (True,) * 4, True),
            replace(CommandGuardInput(.05, .3, False, True, True, True), **overrides), index == 12))
    yield "native_base_guard_cross_fault_recovery", cfg, tuple(samples)


def assert_result(expected, raw, label):
    actual = decoded(raw)
    if signature(expected) != signature(actual):
        raise AssertionError(f"base guard disagreement {label}: {signature(expected)!r} vs {signature(actual)!r}")
    if raw.guard.output_valid != 1 or raw.next.type_valid != 1 or raw.next.previous_vector_valid != 1:
        raise AssertionError("C result schema is not valid")
    if any(s.numeric != 1 for s in (*raw.guard.output, *raw.next.previous)):
        raise AssertionError("C result numeric tags are not valid")
    if actual.status == "inhibited" and any(float(v).hex() != "0x0.0p+0" for v in (*actual.output_nm, *actual.next_state.previous_output_nm)):
        raise AssertionError("inhibit is not exact positive zero")
    return actual


def run_guard_parity(core):
    digest, composed_digest = hashlib.sha256(), hashlib.sha256()
    counts = {"direct_cases": 0, "stateful_cycles": 0, "composed_cycles": 0, "allowed_cycles": 0,
              "held_cycles": 0, "clock_fault_cycles": 0, "base_inhibits": 0}
    reasons = {}
    for index, values in enumerate(direct_cases()):
        expected = apply_command_guard(*values)
        raw = core.apply(*values)
        actual = assert_result(expected, raw, index)
        _digest_add(digest, {"direct": index, "result": signature(actual), "contract": raw.contract_code})
        counts["direct_cases"] += 1
        counts["base_inhibits"] += actual.status == "inhibited"
        reasons[actual.reason or "none"] = reasons.get(actual.reason or "none", 0) + 1
    rng = random.Random(SEED)
    templates = tuple(source_adapter_cases())
    for sequence in range(128):
        expected_state = actual_state = CommandGuardState(ZERO)
        for cycle_index in range(64):
            candidate, inp, cfg, injected = rng.choice(templates)
            if cycle_index % 17 == 0: expected_state = actual_state = injected
            expected = apply_command_guard(candidate, inp, cfg, expected_state)
            raw = core.apply(candidate, inp, cfg, actual_state)
            actual = assert_result(expected, raw, f"stream{sequence}/{cycle_index}")
            expected_state, actual_state = expected.next_state, actual.next_state
            _digest_add(digest, {"stream": sequence, "cycle": cycle_index, "result": signature(actual)})
            counts["stateful_cycles"] += 1
    corners = {}
    for label, *values in corner_cases():
        corners[label] = signature(assert_result(apply_command_guard(*values), core.apply(*values), label))
    for label, cfg, samples in guarded_composition_scenarios():
        rows = replay_control_pipeline(samples, cfg)
        previous, clock_state, gate_state = CommandGuardState(ZERO), ClockState(), Snapshot(3, 0, 0)
        for sample, row in zip(samples, rows):
            if sample.restart_requested: previous = CommandGuardState(ZERO, previous.pedal_overlap_latched)
            candidate = allocate_propulsive_torque(sample.allocation, cfg.allocator)
            raw = core.apply(candidate, sample.guard, cfg.guard, previous)
            base = assert_result(apply_command_guard(candidate, sample.guard, cfg.guard, previous), raw,
                                 f"composed/{label}/{row['sequence']}")
            clock = core.step(clock_state, clock_input(sample.allocation.now_ms, sample.guard.dt_s), clock_policy(cfg.period_ms))
            reconciled = core.reconcile(facts(candidate, sample.guard, cfg.guard, previous, base, bool(clock.fault.kind)))
            effective = adapted(base, reconciled)
            decision = core.decide_raw(gate_state, Cycle(allocation(candidate), guard(effective), clock.fault,
                sample.restart_requested), Policy(cfg.fault.valid_samples_to_recover))
            actual = {"command_allowed": bool(decision.command_allowed),
                "command_hex": [float(v).hex() for v in decision.command], "latch": bool(reconciled.next_latched),
                "state": STATE_NAMES[decision.next.state], "streak": decision.next.recovery_streak,
                "generation": decision.next.generation, "reason": bytes(decision.reason).decode("ascii")}
            wanted = {"command_allowed": row["command_allowed"],
                "command_hex": [float(v).hex() for v in row["command_nm"]], "latch": row["guard"]["pedal_overlap_latched"],
                "state": row["fault"]["next_state"], "streak": row["fault"]["recovery_streak"],
                "generation": row["fault"]["generation"], "reason": row["fault"]["reason"]}
            if actual != wanted or unpack(clock)["fault"] != row["clock_fault"]:
                raise AssertionError(f"native guard/pedal/clock/gate disagreement {label}/{row['sequence']}")
            if not decision.command_allowed and bytes(decision.command) != b"\0" * 32:
                raise AssertionError("held proposed command is not exact positive zero")
            _digest_add(composed_digest, {"label": label, "cycle": row["sequence"], "base": signature(base), "result": actual})
            previous = CommandGuardState(tuple(decision.command), bool(reconciled.next_latched))
            clock_state, gate_state = clock.next, decision.next
            counts["composed_cycles"] += 1
            counts["allowed_cycles"] += bool(decision.command_allowed)
            counts["held_cycles"] += not decision.command_allowed
            counts["clock_fault_cycles"] += bool(clock.fault.kind)
    return {**counts, "reasons": reasons, "corners": corners, "base_results_sha256": digest.hexdigest(),
            "composed_results_sha256": composed_digest.hexdigest()}


def check_boundaries(core):
    checks, digest = 0, hashlib.sha256()
    baseline = tuple((allocation, guard_input, config, state)[i](v) for i, v in enumerate(ordinary()))
    def require(condition, label):
        nonlocal checks
        if not condition: raise AssertionError("guard C boundary: " + label)
        checks += 1; _digest_add(digest, label)
    def zero(raw):
        return raw.guard.status == 3 and all(s.value == 0. and math.copysign(1., s.value) == 1.
            for s in (*raw.guard.output, *raw.next.previous))
    mutations = [(1, name, None) for name in ("type_valid", "brake", "comms", "sensors", "interlock")]
    mutations += [(0, "type_valid", None), (0, "wheel_vector_valid", None),
                  (2, "type_valid", None), (3, "type_valid", None), (3, "previous_vector_valid", None)]
    mutations += [(owner, name, "numeric") for owner, names in ((1, ("dt_s", "accelerator")),
                  (2, ("max_rise", "trip", "clear"))) for name in names]
    for owner, name, subfield in mutations:
        for tag in range(256):
            values = tuple(type(v).from_buffer_copy(v) for v in baseline)
            if subfield: setattr(getattr(values[owner], name), subfield, tag)
            else: setattr(values[owner], name, tag)
            raw = core.apply_raw(*values)
            malformed = tag > 1 if owner == 1 and name in ("brake", "comms", "sensors", "interlock") else tag != 1
            require(not malformed or zero(raw), f"{owner}/{name}/{tag}")
    for slot, owner, member in itertools.product(range(4), (0, 3), ("numeric",)):
        for tag in range(256):
            values = tuple(type(v).from_buffer_copy(v) for v in baseline)
            target = values[owner].wheels if owner == 0 else values[owner].previous
            setattr(target[slot], member, tag)
            require(tag == 1 or zero(core.apply_raw(*values)), f"vector/{owner}/{slot}/{tag}")
    for tag in range(2, 256):
        values = tuple(type(v).from_buffer_copy(v) for v in baseline)
        values[3].previous_latched = tag
        raw = core.apply_raw(*values)
        require(zero(raw) and raw.next.previous_latched == 1, f"latch/{tag}")
    for tag in range(256):
        values = tuple(type(v).from_buffer_copy(v) for v in baseline)
        values[0].status = tag
        require(tag == 1 or zero(core.apply_raw(*values)), f"candidate_status/{tag}")
        values = tuple(type(v).from_buffer_copy(v) for v in baseline)
        values[0].fault.kind = tag
        require(tag == 0 or zero(core.apply_raw(*values)), f"candidate_fault_kind/{tag}")
    values = tuple(type(v).from_buffer_copy(v) for v in baseline)
    values[0].fault.kind = 1
    ct.memset(ct.addressof(values[0].fault) + type(values[0].fault).value.offset, 65, 64)
    require(zero(core.apply_raw(*values)), "unterminated_candidate_fault")
    for owner, reason, latch in ((1, "invalid_guard_input_type", False),
            (2, "invalid_guard_config_type", False), (3, "invalid_guard_state_type", True)):
        values = tuple(type(v).from_buffer_copy(v) for v in baseline)
        values[owner].type_valid = 0
        actual = decoded(core.apply_raw(*values))
        require(actual.reason == reason and actual.next_state.pedal_overlap_latched == latch,
                f"C_only_outer_schema/{owner}")
    for index in range(5):
        result = GuardResult(); ct.memset(ct.addressof(result), 255, ct.sizeof(result))
        arguments = [ct.byref(v) for v in baseline] + [ct.byref(result)]
        arguments[index] = None
        code = core.library.tc_apply_command_guard(*arguments)
        require(code == 1 and (index == 4 or (zero(result) and result.next.previous_latched == 1)), f"null/{index}")
    initialized = GuardState(); ct.memset(ct.addressof(initialized), 255, ct.sizeof(initialized))
    core.library.tc_init_command_guard_state(ct.byref(initialized))
    require(initialized.type_valid == initialized.previous_vector_valid == 1 and initialized.previous_latched == 0
            and all(s.numeric == 1 and s.value == 0. and math.copysign(1., s.value) == 1. for s in initialized.previous), "initialized")
    core.library.tc_init_command_guard_state(None)
    require(core.library.tc_command_guard_abi_sizeof(999) == 0, "unknown_size")
    return {"checks": checks, "sha256": digest.hexdigest()}


def _worker(library, sender):
    try:
        core = GuardCore(Path(library))
        boundaries = check_boundaries(core)
        first, second = run_guard_parity(core), run_guard_parity(core)
        if first != second: raise AssertionError("guard behavior did not repeat")
        sender.send({"results": first, "guard_abi_sizes": core.guard_sizes, "boundaries": boundaries})
    except BaseException: sender.send({"error": traceback.format_exc()})
    finally: sender.close()


def verify_in_child(library):
    context = mp.get_context("spawn"); receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(str(library), sender)); process.start(); sender.close()
    try:
        if not receiver.poll(180): raise RuntimeError("guard child timed out")
        result = receiver.recv(); process.join(10)
        if process.is_alive() or process.exitcode != 0 or "error" in result:
            raise RuntimeError(result.get("error", f"guard child exit {process.exitcode}"))
        return result
    finally:
        receiver.close()
        if process.is_alive(): process.terminate()
        process.join(10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc"); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink(): parser.error("receipt output must be new")
    frozen_protocol()
    with tempfile.TemporaryDirectory(prefix="enme408-guard-") as directory:
        library, build = build_guard_library(Path(directory), args.cc)
        result = verify_in_child(library)
        receipt = {"schema": "enme408-portable-base-command-guard-parity/v1", "guard_version": VERSION,
            "numeric_contract_version": 2, "protocol_sha256": PROTOCOL_SHA256, "seed": SEED,
            "repeat_agreement": True, "build": build, **result,
            "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES},
            "limits": ["Ordinary IEEE binary64 round-to-nearest and retained subnormals assumed",
                       "Offline synthetic four-slot base guard; allocator and orchestration remain external",
                       "C-only outer schema/null checks are distinct from Python result parity",
                       "No physical mapping, target parity, firmware, CAN, hardware, timing, WCET or safety approval"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result["results"], sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
