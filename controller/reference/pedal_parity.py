"""Compiled trust predicates and pedal-adapter metadata, with native clock/gate."""
from __future__ import annotations

import argparse
import ctypes as ct
from dataclasses import replace
import hashlib
import itertools
import json
import math
import multiprocessing as mp
from pathlib import Path
import random
import tempfile
import traceback

from allocator import AllocationResult, allocate_propulsive_torque
from command_guard import (CommandGuardConfig, CommandGuardInput, CommandGuardResult,
                           CommandGuardState, apply_command_guard)
from guard_overlap_observation import trusted_overlap_trip
from guard_trusted_clear import trusted_clear_cycle, apply_trusted_clear_guard
from control_pipeline import replay_control_pipeline
from c_parity import (ROOT, Cycle, Policy, Scalar, Snapshot, Text, STATE_NAMES, allocation,
                      build_library, guard, scalar, text, _digest_add, _packed_signature)
from clock_parity import (ClockCore, ClockState, clock_input, clock_policy, unpack,
                          composition_scenarios, SOURCE_FILES as CLOCK_SOURCE_FILES)

PEDAL_ADAPTER_VERSION = 1
SOURCE_FILES = (*CLOCK_SOURCE_FILES, "pedal_parity.py", "native/pedal_sanitizer_probe.c",
                "../research/TC-03D-pedal-protocol.json")
ZERO = (0.,)*4


class PedalFacts(ct.Structure):
    _fields_ = [("input_type_valid", ct.c_uint8), ("config_type_valid", ct.c_uint8),
        ("state_type_valid", ct.c_uint8), ("previous_latched", ct.c_uint8), ("base_next_latched", ct.c_uint8),
        ("accelerator", Scalar), ("rise", Scalar), ("trip", Scalar), ("clear", Scalar),
        ("brake", ct.c_uint8), ("comms", ct.c_uint8), ("sensors", ct.c_uint8), ("interlock", ct.c_uint8),
        ("candidate_type_valid", ct.c_uint8), ("candidate_status", ct.c_uint8),
        ("result_type_valid", ct.c_uint8), ("guard_status", ct.c_uint8), ("clock_fault_present", ct.c_uint8),
        ("base_reason", Text)]


class PedalResult(ct.Structure):
    _fields_ = [("trip_observed", ct.c_uint8), ("clear_cycle_trusted", ct.c_uint8),
                ("adapter_veto", ct.c_uint8), ("next_latched", ct.c_uint8), ("reason", Text)]


def boolean(value):
    return int(value) if type(value) is bool else 2


def facts(candidate, inp, cfg, state, result, clock_fault=False):
    value = PedalFacts()
    value.input_type_valid = type(inp) is CommandGuardInput
    value.config_type_valid = type(cfg) is CommandGuardConfig
    value.state_type_valid = type(state) is CommandGuardState
    value.candidate_type_valid = type(candidate) is AllocationResult
    value.result_type_valid = type(result) is CommandGuardResult
    if value.input_type_valid:
        value.accelerator = scalar(inp.accelerator_fraction)
        for field, source in (("brake", inp.brake_active), ("comms", inp.critical_comms_ok),
                              ("sensors", inp.sensor_agreement_ok), ("interlock", inp.external_interlock)):
            setattr(value, field, boolean(source))
    if value.config_type_valid:
        value.rise, value.trip, value.clear = map(scalar, (cfg.max_rise_nm_per_s,
            cfg.pedal_overlap_trip_fraction, cfg.pedal_clear_fraction))
    value.previous_latched = boolean(state.pedal_overlap_latched) if value.state_type_valid else 2
    if value.candidate_type_valid and type(candidate.status) is str:
        value.candidate_status = {"ok": 1, "saturated": 2, "fault": 3}.get(candidate.status, 0)
    if value.result_type_valid:
        value.base_next_latched = boolean(result.next_state.pedal_overlap_latched)
        if type(result.status) is str:
            value.guard_status = {"ok": 1, "limited": 2, "inhibited": 3}.get(result.status, 0)
        value.base_reason = text(result.reason)
    value.clock_fault_present = boolean(clock_fault)
    return value


class PedalCore(ClockCore):
    def __init__(self, library):
        super().__init__(library)
        lib = self.library
        lib.tc_pedal_adapter_version.argtypes, lib.tc_pedal_adapter_version.restype = [], ct.c_uint32
        lib.tc_pedal_abi_sizeof.argtypes, lib.tc_pedal_abi_sizeof.restype = [ct.c_uint32], ct.c_size_t
        for name in ("tc_trusted_overlap_trip", "tc_trusted_clear_cycle"):
            method = getattr(lib, name)
            method.argtypes, method.restype = [ct.POINTER(PedalFacts)], ct.c_uint8
        lib.tc_reconcile_pedal_latch.argtypes = [ct.POINTER(PedalFacts), ct.POINTER(PedalResult)]
        lib.tc_reconcile_pedal_latch.restype = ct.c_uint32
        if lib.tc_pedal_adapter_version() != PEDAL_ADAPTER_VERSION:
            raise ValueError("pedal adapter contract mismatch")
        self.pedal_sizes = {kind.__name__: ct.sizeof(kind) for kind in (PedalFacts, PedalResult)}
        for number, kind in enumerate((PedalFacts, PedalResult), 1):
            if lib.tc_pedal_abi_sizeof(number) != ct.sizeof(kind):
                raise ValueError("pedal ABI size mismatch")

    def reconcile(self, packed):
        result = PedalResult()
        if self.library.tc_reconcile_pedal_latch(ct.byref(packed), ct.byref(result)):
            raise ValueError("pedal call rejected required input")
        return result


def ordinary():
    return (AllocationResult((10.,)*4, 40., 40., "ok", None),
            CommandGuardInput(.05, .8, True, True, True, True), CommandGuardConfig(100., .6, .2),
            CommandGuardState(ZERO), CommandGuardResult(ZERO, CommandGuardState(ZERO), "ok", None))


def predicate_cases():
    good, inp, cfg, state, result = ordinary()
    accels = (0., .2, math.nextafter(.2, math.inf), math.nextafter(.6, -math.inf), .6, .8, 1.)
    for accel, flags, prior, status, guard_status in itertools.product(
            accels, itertools.product((False, True), repeat=4), (False, True),
            ("ok", "saturated", "fault", "unknown"), ("ok", "limited", "inhibited")):
        yield replace(good, status=status), replace(inp, accelerator_fraction=accel,
            brake_active=flags[0], critical_comms_ok=flags[1], sensor_agreement_ok=flags[2],
            external_interlock=flags[3]), cfg, replace(state, pedal_overlap_latched=prior), replace(result, status=guard_status)
    for malformed in (None, True, "0.8", math.nan, math.inf, -math.inf, -1., 1.01, 10**400):
        yield good, replace(inp, accelerator_fraction=malformed), cfg, state, result
        for field in ("max_rise_nm_per_s", "pedal_overlap_trip_fraction", "pedal_clear_fraction"):
            yield good, inp, replace(cfg, **{field: malformed}), state, result
        for field in ("brake_active", "critical_comms_ok", "sensor_agreement_ok", "external_interlock"):
            yield good, replace(inp, **{field: malformed}), cfg, state, result
        yield good, inp, cfg, replace(state, pedal_overlap_latched=malformed), result
    for index in range(5):
        values = [good, inp, cfg, state, result]
        values[index] = None
        yield tuple(values)


def source_adapter_cases():
    candidate, inp, cfg, state, _ = ordinary()
    candidates = (candidate, None, replace(candidate, status="unknown"),
        replace(candidate, requested_nm=0.), replace(candidate, wheel_torque_nm=(10.,)*3),
        replace(candidate, fault="external_interlock_open"),
        AllocationResult(ZERO, 40., 0., "fault", "stale_input"))
    for prior, accel, flags, cand, bad_dt in itertools.product((False, True),
            (.1, .2, .3, .6, .8), itertools.product((False, True), repeat=4), candidates, (False, True)):
        yield (cand, replace(inp, accelerator_fraction=accel, brake_active=flags[0], critical_comms_ok=flags[1],
            sensor_agreement_ok=flags[2], external_interlock=flags[3], dt_s=100. if bad_dt else .05),
            cfg, replace(state, pedal_overlap_latched=prior))
    for bad in (None, True, "0", math.nan, math.inf, -1., 10**400):
        for field in ("max_rise_nm_per_s", "pedal_overlap_trip_fraction", "pedal_clear_fraction"):
            yield candidate, inp, replace(cfg, **{field: bad}), state
        yield candidate, replace(inp, accelerator_fraction=bad), cfg, state
        for field in ("brake_active", "critical_comms_ok", "sensor_agreement_ok", "external_interlock"):
            yield candidate, replace(inp, **{field: bad}), cfg, state
        yield candidate, inp, cfg, replace(state, pedal_overlap_latched=bad)
    rng = random.Random(410)
    for _ in range(256):
        clear = rng.uniform(0., .4)
        config = CommandGuardConfig(rng.choice((0., 100., 1e308)), rng.uniform(.5, 1.), clear)
        random_input = CommandGuardInput(rng.choice((.05, 100., math.nan, True)), rng.random(),
            *(bool(rng.getrandbits(1)) for _ in range(4)))
        previous = CommandGuardState(tuple(rng.uniform(0., 20.) for _ in range(4)), bool(rng.getrandbits(1)))
        yield rng.choice(candidates), random_input, config, previous


def adapted(base, native):
    reason = bytes(native.reason.value).decode("utf-8") if native.reason.kind else None
    if native.adapter_veto:
        return CommandGuardResult(ZERO, CommandGuardState(ZERO, bool(native.next_latched)), "inhibited", reason)
    return replace(base, reason=reason,
                   next_state=replace(base.next_state, pedal_overlap_latched=bool(native.next_latched)))


def run_pedal_parity(core):
    digest, composed_digest = hashlib.sha256(), hashlib.sha256()
    stats = {"predicate_cases": 0, "source_adapter_cases": 0, "adapter_vetoes": 0,
             "composed_cycles": 0, "allowed_cycles": 0, "held_cycles": 0, "clock_fault_cycles": 0}
    for index, (candidate, inp, cfg, state, result) in enumerate(predicate_cases()):
        packed = facts(candidate, inp, cfg, state, result)
        expected = (trusted_overlap_trip(inp, cfg, state), trusted_clear_cycle(candidate, inp, result))
        actual = (bool(core.library.tc_trusted_overlap_trip(ct.byref(packed))),
                  bool(core.library.tc_trusted_clear_cycle(ct.byref(packed))))
        if actual != expected:
            raise AssertionError(f"pedal predicate disagreement {index}: {expected!r} vs {actual!r}")
        _digest_add(digest, {"predicate": index, "input": _packed_signature(packed), "result": actual})
        stats["predicate_cases"] += 1
    for index, (candidate, inp, cfg, state) in enumerate(source_adapter_cases()):
        base = apply_command_guard(candidate, inp, cfg, state)
        expected = apply_trusted_clear_guard(candidate, inp, cfg, state)
        native = core.reconcile(facts(candidate, inp, cfg, state, base))
        actual = adapted(base, native)
        if actual != expected:
            raise AssertionError(f"pedal adapter disagreement {index}: {expected!r} vs {actual!r}")
        if native.adapter_veto and actual.output_nm != ZERO:
            raise AssertionError("adapter veto did not yield exact-zero guard")
        _digest_add(digest, {"adapter": index, "result": _packed_signature(native)})
        stats["source_adapter_cases"] += 1
        stats["adapter_vetoes"] += bool(native.adapter_veto)
    for label, cfg, samples in composition_scenarios():
        rows = replay_control_pipeline(samples, cfg)
        state, clock_state, gate_state = CommandGuardState(ZERO), ClockState(), Snapshot(3, 0, 0)
        for sample, row in zip(samples, rows):
            if sample.restart_requested:
                state = CommandGuardState(ZERO, state.pedal_overlap_latched)
            candidate = allocate_propulsive_torque(sample.allocation, cfg.allocator)
            base = apply_command_guard(candidate, sample.guard, cfg.guard, state)
            clock = core.step(clock_state, clock_input(sample.allocation.now_ms, sample.guard.dt_s), clock_policy(cfg.period_ms))
            native = core.reconcile(facts(candidate, sample.guard, cfg.guard, state, base, bool(clock.fault.kind)))
            guarded = adapted(base, native)
            cycle = Cycle(allocation(candidate), guard(guarded), clock.fault, sample.restart_requested)
            decision = core.decide_raw(gate_state, cycle, Policy(cfg.fault.valid_samples_to_recover))
            actual = {"command_allowed": bool(decision.command_allowed), "command_nm": list(decision.command),
                "latch": bool(native.next_latched), "state": STATE_NAMES[decision.next.state],
                "streak": decision.next.recovery_streak, "generation": decision.next.generation,
                "reason": bytes(decision.reason).decode("utf-8")}
            wanted = {"command_allowed": row["command_allowed"], "command_nm": row["command_nm"],
                "latch": row["guard"]["pedal_overlap_latched"], "state": row["fault"]["next_state"],
                "streak": row["fault"]["recovery_streak"], "generation": row["fault"]["generation"],
                "reason": row["fault"]["reason"]}
            if actual != wanted or unpack(clock)["fault"] != row["clock_fault"]:
                raise AssertionError(f"pedal/clock/gate disagreement {label}/{row['sequence']}: {wanted!r} vs {actual!r}")
            if not decision.command_allowed and bytes(decision.command) != b"\0"*32:
                raise AssertionError("held composed command is not exact positive zero")
            _digest_add(composed_digest, {"label": label, "sequence": row["sequence"], "pedal": _packed_signature(native), "result": actual})
            state = CommandGuardState(tuple(decision.command), bool(native.next_latched))
            clock_state, gate_state = clock.next, decision.next
            stats["composed_cycles"] += 1
            stats["allowed_cycles"] += bool(decision.command_allowed)
            stats["held_cycles"] += not decision.command_allowed
            stats["clock_fault_cycles"] += bool(clock.fault.kind)
    return {**stats, "pedal_results_sha256": digest.hexdigest(), "composed_results_sha256": composed_digest.hexdigest()}


def check_boundaries(core):
    checks, digest = 0, hashlib.sha256()
    good = facts(*ordinary())
    def require(condition, label):
        nonlocal checks
        if not condition: raise AssertionError("pedal ABI boundary: " + label)
        checks += 1; _digest_add(digest, label)
    for field in ("previous_latched", "base_next_latched", "clock_fault_present"):
        for tag in range(2, 256):
            value = PedalFacts.from_buffer_copy(good); setattr(value, field, tag)
            result = core.reconcile(value)
            require(result.adapter_veto == 1 and result.next_latched == 1, f"{field}_{tag}")
    for field in ("input_type_valid", "config_type_valid", "state_type_valid", "result_type_valid"):
        for tag in range(256):
            value = PedalFacts.from_buffer_copy(good); setattr(value, field, tag)
            result = core.reconcile(value)
            require(tag == 1 or (result.adapter_veto == 1 and result.next_latched == 1), f"{field}_{tag}")
    for field in ("accelerator", "rise", "trip", "clear"):
        for tag in range(256):
            value = PedalFacts.from_buffer_copy(good); getattr(value, field).numeric = tag
            require(bool(core.library.tc_trusted_overlap_trip(ct.byref(value))) == (tag == 1), f"{field}_numeric_{tag}")
    for field in ("brake", "comms", "sensors"):
        for tag in range(256):
            value = PedalFacts.from_buffer_copy(good); setattr(value, field, tag)
            require(bool(core.library.tc_trusted_overlap_trip(ct.byref(value))) == (tag == 1), f"{field}_trip_{tag}")
    for field in ("input_type_valid", "candidate_type_valid", "result_type_valid", "candidate_status",
                  "guard_status", "comms", "sensors", "interlock"):
        for tag in range(256):
            value = PedalFacts.from_buffer_copy(good); setattr(value, field, tag)
            accepted = tag in (1, 2) if field in ("candidate_status", "guard_status") else tag == 1
            require(bool(core.library.tc_trusted_clear_cycle(ct.byref(value))) == accepted, f"{field}_clear_{tag}")
    value = PedalFacts.from_buffer_copy(good)
    result = core.reconcile(value)
    require(result.adapter_veto and result.next_latched and
            bytes(result.reason.value) == b"brake_accelerator_overlap", "missed_trip_fallback")
    value.previous_latched = 1; value.accelerator.value = .1; value.brake = 0; value.guard_status = 3
    result = core.reconcile(value)
    require(result.adapter_veto and result.next_latched and
            bytes(result.reason.value) == b"untrusted_overlap_latch_clear", "untrusted_clear_fallback")
    value.guard_status = 1; value.clock_fault_present = 1
    result = core.reconcile(value)
    require(not result.adapter_veto and result.clear_cycle_trusted and result.next_latched,
            "clock_retains_latch_without_reclassifying_base_guard")
    value = PedalFacts.from_buffer_copy(good); value.base_reason.kind = 1
    ct.memset(ct.addressof(value.base_reason)+Text.value.offset, 65, 64)
    result = core.reconcile(value)
    require(result.adapter_veto == 1 and result.next_latched == 1, "unterminated_reason")
    output = PedalResult(); ct.memset(ct.addressof(output), 255, ct.sizeof(output))
    require(core.library.tc_reconcile_pedal_latch(None, ct.byref(output)) == 1 and
            output.adapter_veto == 1 and output.next_latched == 1, "null_input_initialized")
    require(core.library.tc_reconcile_pedal_latch(ct.byref(good), None) == 1, "null_output")
    require(core.library.tc_trusted_overlap_trip(None) == 0 and core.library.tc_trusted_clear_cycle(None) == 0,
            "null_predicates")
    require(core.library.tc_pedal_abi_sizeof(999) == 0, "unknown_abi_kind")
    return {"checks": checks, "sha256": digest.hexdigest()}


def _worker(library, sender):
    try:
        core = PedalCore(Path(library)); boundaries = check_boundaries(core)
        first, second = run_pedal_parity(core), run_pedal_parity(core)
        if first != second: raise AssertionError("pedal experiment did not repeat")
        sender.send({"results": first, "pedal_abi_sizes": core.pedal_sizes, "boundaries": boundaries})
    except BaseException:
        sender.send({"error": traceback.format_exc()})
    finally:
        sender.close()


def verify_in_child(library):
    context = mp.get_context("spawn"); receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(str(library), sender)); process.start(); sender.close()
    try:
        if not receiver.poll(120): raise RuntimeError("pedal child timed out")
        result = receiver.recv(); process.join(10)
        if process.is_alive() or process.exitcode != 0 or "error" in result:
            raise RuntimeError(result.get("error", f"pedal child exit {process.exitcode}"))
        return result
    finally:
        receiver.close()
        if process.is_alive(): process.terminate()
        process.join(10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc"); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if any(args.output.resolve() == (ROOT/name).resolve() or (args.output.exists() and args.output.samefile(ROOT/name))
           for name in SOURCE_FILES): parser.error("output must not overwrite a contributing source or hardlink")
    with tempfile.TemporaryDirectory(prefix="enme408-pedal-") as directory:
        library, build = build_library(Path(directory), args.cc); result = verify_in_child(library)
        receipt = {"schema": "enme408-portable-pedal-adapter-parity/v1", "pedal_adapter_version": PEDAL_ADAPTER_VERSION,
            "repeat_agreement": True, "seed": 410, "build": build, **result,
            "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
            "limits": ["Metadata adapters only; base guard/latch/slew/allocator remain external",
                       "No predicate independently authorizes positive torque or attests signal provenance",
                       "Clock faults separately inhibit through native clock/final gate",
                       "No target, firmware, CAN, hardware, HIL, WCET or safety approval"]}
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result["results"], sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
