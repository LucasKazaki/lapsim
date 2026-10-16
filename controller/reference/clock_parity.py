"""Finite compiled normalized-clock parity and clock-to-final-gate composition."""
from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import itertools
import json
import math
import multiprocessing as mp
from pathlib import Path
import random
import tempfile
import traceback

from allocator import AllocationInput, AllocationResult, AllocatorConfig
from command_guard import CommandGuardConfig, CommandGuardInput, CommandGuardResult, CommandGuardState
from control_pipeline import ControlSample, PipelineConfig, replay_control_pipeline
from cycle_clock import CLOCK_CONTRACT_VERSION, CycleClockState, observe_cycle_clock
from fault_state import FaultPolicy
from torque_numeric import NUMERIC_CONTRACT_VERSION
from c_parity import (ROOT, SOURCE_FILES as CORE_SOURCE_FILES, Core, Cycle, Decision, Policy,
                      Scalar, Snapshot, STATE_NAMES, Text, allocation, build_library,
                      guard, scalar, text, _digest_add, _packed_signature, pipeline_scenarios)

UINT64_MAX = 2**64-1
PERIODS = (1, 7, 50, 999, 1000, 60000)
SOURCE_FILES = (*CORE_SOURCE_FILES, "clock_parity.py", "native/clock_sanitizer_probe.c",
                "../research/TC-03C-clock-protocol.json")


class ClockState(ct.Structure):
    _fields_ = [("previous_present", ct.c_uint8), ("previous_tick", ct.c_uint64)]


class ClockInput(ct.Structure):
    _fields_ = [("now_ms", ct.c_uint64), ("timestamp_valid", ct.c_uint8), ("dt_s", Scalar)]


class ClockPolicy(ct.Structure):
    _fields_ = [("period_ms", ct.c_uint32)]


class ClockResult(ct.Structure):
    _fields_ = [("next", ClockState), ("now_valid", ct.c_uint8), ("now_ms", ct.c_uint64), ("fault", Text)]


def clock_state(previous: CycleClockState) -> ClockState:
    if type(previous) is not CycleClockState:
        raise ValueError("expected CycleClockState")
    if previous.previous_tick is None:
        return ClockState()
    if type(previous.previous_tick) is not int or not 0 <= previous.previous_tick <= UINT64_MAX:
        raise ValueError("previous timestamp is outside the C uint64 domain")
    return ClockState(1, previous.previous_tick)


def clock_input(tick: object, dt: object) -> ClockInput:
    if type(tick) is int and tick > UINT64_MAX:
        raise ValueError("timestamp is outside the C uint64 domain")
    valid = type(tick) is int and tick >= 0
    return ClockInput(tick if valid else 0, int(valid), scalar(dt))


def clock_policy(period: object) -> ClockPolicy:
    if type(period) is not int or not 1 <= period <= 60000:
        raise ValueError("period_ms must be an integer in [1, 60000]")
    return ClockPolicy(period)


def unpack(result: ClockResult):
    return {"previous_tick": result.next.previous_tick if result.next.previous_present else None,
            "now_ms": result.now_ms if result.now_valid else None,
            "fault": bytes(result.fault.value).decode("ascii") if result.fault.kind else None}


class ClockCore(Core):
    def __init__(self, library):
        super().__init__(library)
        lib = self.library
        lib.tc_clock_contract_version.argtypes, lib.tc_clock_contract_version.restype = [], ct.c_uint32
        lib.tc_clock_abi_sizeof.argtypes, lib.tc_clock_abi_sizeof.restype = [ct.c_uint32], ct.c_size_t
        lib.tc_init_clock.argtypes, lib.tc_init_clock.restype = [ct.POINTER(ClockState)], None
        lib.tc_clock_step.argtypes = [ct.POINTER(ClockState), ct.POINTER(ClockInput),
                                     ct.POINTER(ClockPolicy), ct.POINTER(ClockResult)]
        lib.tc_clock_step.restype = ct.c_uint32
        lib.tc_clocked_decide.argtypes = [ct.POINTER(ClockState), ct.POINTER(ClockInput),
            ct.POINTER(ClockPolicy), ct.POINTER(Snapshot), ct.POINTER(Cycle), ct.POINTER(Policy),
            ct.POINTER(ClockResult), ct.POINTER(Decision)]
        lib.tc_clocked_decide.restype = ct.c_uint32
        if lib.tc_clock_contract_version() != CLOCK_CONTRACT_VERSION:
            raise ValueError("C clock contract version mismatch")
        kinds = (ClockState, ClockInput, ClockPolicy, ClockResult)
        self.clock_sizes = {kind.__name__: ct.sizeof(kind) for kind in kinds}
        for number, kind in enumerate(kinds, 1):
            if lib.tc_clock_abi_sizeof(number) != ct.sizeof(kind):
                raise ValueError("C clock ABI size mismatch: " + kind.__name__)

    def step(self, previous, inp, policy):
        result = ClockResult()
        if self.library.tc_clock_step(ct.byref(previous), ct.byref(inp), ct.byref(policy), ct.byref(result)):
            raise ValueError("clock call rejected a required argument")
        return result

    def decide(self, previous, inp, policy, previous_gate, cycle, gate_policy):
        result, decision = ClockResult(), Decision()
        code = self.library.tc_clocked_decide(ct.byref(previous), ct.byref(inp), ct.byref(policy),
            ct.byref(previous_gate), ct.byref(cycle), ct.byref(gate_policy), ct.byref(result), ct.byref(decision))
        if code:
            raise ValueError("clock/gate call rejected a required argument")
        return result, decision


def dt_edges(period):
    expected = period / 1000
    values = [None, True, "0.05", -1., -0., 0., math.nan, math.inf, -math.inf,
              10**400, expected, math.nextafter(expected, -math.inf),
              math.nextafter(expected, math.inf), 1, 100., 5e-324]
    for boundary in (expected-1e-12, expected+1e-12):
        values.extend((math.nextafter(boundary, -math.inf), boundary,
                       math.nextafter(boundary, math.inf)))
    return values


def direct_cases():
    previous = (None, 0, 1, 50, 2**53+7, UINT64_MAX-60000, UINT64_MAX)
    ticks = (None, True, "50", 50., -1, 0, 1, 49, 50, 51, 100,
             2**53+7, 2**53+57, UINT64_MAX-60000, UINT64_MAX-1, UINT64_MAX)
    for period in PERIODS:
        yield from ((prior, tick, dt, period) for prior, tick, dt in
                    itertools.product(previous, ticks, dt_edges(period)))
        # Healthy and adjacent cadence at exact integers larger than 2**53.
        for prior in (0, 2**53+7, UINT64_MAX-60000):
            for delta in (period-1, period, period+1):
                if prior+delta <= UINT64_MAX:
                    yield prior, prior+delta, period/1000, period


def stateful_cases(seed=409):
    rng = random.Random(seed)
    for sequence in range(64):
        period = PERIODS[sequence % len(PERIODS)]
        tick = rng.choice((0, 2**53+7, UINT64_MAX-10_000_000))
        values = []
        for index in range(64):
            tick += period
            event = rng.randrange(12)
            now = (None if event == 0 else True if event == 1 else
                   tick-period if event == 2 else tick-2*period if event == 3 else
                   tick+period if event == 4 else tick)
            dt = rng.choice(dt_edges(period)) if event < 6 else period/1000
            values.append((now, dt))
        yield sequence, period, values


def composition_scenarios():
    yield from pipeline_scenarios(seed=409)
    cfg = PipelineConfig(AllocatorConfig(50), CommandGuardConfig(100., .6, .2), FaultPolicy(2), 50)
    def sample(tick, *, accel=.3, brake=False, dt=.05, restart=False):
        return ControlSample(AllocationInput(tick, tick, 40., (100.,)*4, (True,)*4, True),
                             CommandGuardInput(dt, accel, brake, True, True, True), restart)
    for tick, dt in ((150, .05), (50, .05), (100, 100.)):
        next_tick = max(50, tick)+50
        yield f"original_clock_latch_{tick}_{dt}", cfg, (
            sample(0, accel=.8, brake=True), sample(50, accel=.8),
            sample(tick, accel=.1, dt=dt), sample(next_tick, accel=.8),
            sample(next_tick+50, accel=.8), sample(next_tick+100, accel=.1),
            sample(next_tick+150, accel=.8))
    for base in (2**53+1, UINT64_MAX-100):
        yield f"exact_uint64_{base}", cfg, (
            sample(base), sample(base+50), sample(base+100), sample(base+50, restart=True), sample(base+100))
    yield "malformed_timestamp_no_coercion", cfg, tuple(sample(tick) for tick in (0, True, 50., None, -1, 50, 100))


def run_clock_parity(core):
    clock_digest, composed_digest = hashlib.sha256(), hashlib.sha256()
    stats = {"direct_cases": 0, "stateful_cycles": 0, "composed_cycles": 0,
             "allowed_cycles": 0, "held_cycles": 0, "clock_fault_cycles": 0, "restarts": 0}
    reasons = {}
    def compare(state, native, tick, dt, period, label):
        expected = observe_cycle_clock(state, tick, dt, period)
        inp = clock_input(tick, dt)
        result = core.step(native, inp, clock_policy(period))
        wanted = {"previous_tick": expected.next_state.previous_tick, "now_ms": expected.now_ms, "fault": expected.fault}
        actual = unpack(result)
        if actual != wanted:
            raise AssertionError(f"clock parity mismatch {label}: {wanted!r} vs {actual!r}")
        reasons[actual["fault"] or "accepted"] = reasons.get(actual["fault"] or "accepted", 0)+1
        _digest_add(clock_digest, {"label": label, "previous": _packed_signature(native),
            "input": _packed_signature(inp), "period_ms": period, "output": actual})
        return expected.next_state, result.next
    for index, (prior, tick, dt, period) in enumerate(direct_cases()):
        previous = CycleClockState(prior)
        compare(previous, clock_state(previous), tick, dt, period, f"direct_{index}")
        stats["direct_cases"] += 1
    for sequence, period, values in stateful_cases():
        state, native = CycleClockState(), ClockState()
        for index, (tick, dt) in enumerate(values):
            state, native = compare(state, native, tick, dt, period, f"sequence_{sequence}_{index}")
            stats["stateful_cycles"] += 1
    for label, config, samples in composition_scenarios():
        rows = replay_control_pipeline(samples, config)
        native, previous_gate = ClockState(), Snapshot(3, 0, 0)
        for sample, row in zip(samples, rows):
            result = AllocationResult(**row["allocator"])
            g = row["guard"]
            guarded = CommandGuardResult(tuple(g["output_nm"]), CommandGuardState(tuple(g["output_nm"]),
                g["pedal_overlap_latched"]), g["status"], g["reason"])
            # A deliberately forged supplied clock fault proves composition
            # uses the new owner, rather than trusting this old cycle field.
            cycle = Cycle(allocation(result), guard(guarded), text("forged_supplied_fault"), sample.restart_requested)
            inp = clock_input(sample.allocation.now_ms, sample.guard.dt_s)
            clock, decision = core.decide(native, inp, clock_policy(config.period_ms), previous_gate,
                                          cycle, Policy(config.fault.valid_samples_to_recover))
            actual = {"next_state": STATE_NAMES[decision.next.state], "recovery_streak": decision.next.recovery_streak,
                "generation": decision.next.generation, "command_allowed": bool(decision.command_allowed),
                "command_nm": list(decision.command), "reason": bytes(decision.reason).decode("utf-8")}
            wanted = {"next_state": row["fault"]["next_state"], "recovery_streak": row["fault"]["recovery_streak"],
                "generation": row["fault"]["generation"], "command_allowed": row["command_allowed"],
                "command_nm": row["command_nm"], "reason": row["fault"]["reason"]}
            if actual != wanted or unpack(clock)["fault"] != row["clock_fault"] or unpack(clock)["now_ms"] != row["now_ms"]:
                raise AssertionError(f"clock/gate mismatch {label} cycle {row['sequence']}: {wanted!r} vs {actual!r}")
            if (not decision.command_allowed or clock.fault.kind) and bytes(decision.command) != b"\0"*32:
                raise AssertionError("held clock/gate output was not exact positive zero")
            _digest_add(composed_digest, {"scenario": label, "sequence": row["sequence"],
                "input": _packed_signature(inp), "clock": unpack(clock), "gate": actual})
            native, previous_gate = clock.next, decision.next
            stats["composed_cycles"] += 1
            stats["allowed_cycles"] += bool(decision.command_allowed)
            stats["held_cycles"] += not decision.command_allowed
            stats["clock_fault_cycles"] += clock.fault.kind == 1
            stats["restarts"] += sample.restart_requested
    return {**stats, "clock_reasons": reasons, "clock_results_sha256": clock_digest.hexdigest(),
            "composed_results_sha256": composed_digest.hexdigest()}


def check_clock_boundaries(core):
    checks = 0
    digest = hashlib.sha256()
    candidate = AllocationResult((10.,)*4, 40., 40., "ok", None)
    guarded = CommandGuardResult((10.,)*4, CommandGuardState((10.,)*4), "ok", None)
    def fresh():
        return [ClockState(1, 0), ClockInput(50, 1, Scalar(.05, 1)), ClockPolicy(50),
                Snapshot(1, 0, 0), Cycle(allocation(candidate), guard(guarded), text(None), 0), Policy(2)]
    def require(condition, label):
        nonlocal checks
        if not condition:
            raise AssertionError("C clock boundary failed: " + label)
        checks += 1
        _digest_add(digest, label)
    for tag in range(256):
        for field in ("state", "timestamp", "dt"):
            args = fresh()
            if field == "state": args[0].previous_present = tag
            elif field == "timestamp": args[1].timestamp_valid = tag
            else: args[1].dt_s.numeric = tag
            clock, decision = core.decide(*args)
            valid = tag in (0, 1) if field == "state" else tag == 1
            require(bool(decision.command_allowed) == valid and
                    (valid or bytes(decision.command) == b"\0"*32), f"{field}_tag_{tag}")
    for period in (0, 60001, 2**32-1):
        args = fresh(); args[2].period_ms = period
        clock, decision = core.decide(*args)
        require(unpack(clock)["fault"] == "invalid_clock_policy" and not decision.command_allowed and
                bytes(decision.command) == b"\0"*32 and not clock.next.previous_present and
                clock.next.previous_tick == 0 and not clock.now_valid and clock.now_ms == 0,
                f"invalid_period_{period}_initializes_absent_state")
    args = fresh(); args[0] = ClockState(0, UINT64_MAX)
    clock, decision = core.decide(*args)
    require(decision.command_allowed and unpack(clock)["previous_tick"] == 50, "absent_anchor_ignores_stored_tick")
    args = fresh(); args[0] = ClockState(1, UINT64_MAX-50); args[1].now_ms = UINT64_MAX
    clock, decision = core.decide(*args)
    require(decision.command_allowed and clock.next.previous_tick == UINT64_MAX, "max_forward_subtraction_no_wrap")
    args[0] = clock.next; args[1].now_ms = 0
    clock, decision = core.decide(*args)
    require(unpack(clock)["fault"] == "nonmonotonic_cycle_timestamp" and not decision.command_allowed and
            clock.next.previous_tick == UINT64_MAX, "wrap_is_rejected_not_normalized")
    for index in range(4):
        args = fresh()[:3]
        result = ClockResult(); ct.memset(ct.addressof(result), 255, ct.sizeof(result))
        pointers = [ct.byref(value) for value in args]+[ct.byref(result)]
        pointers[index] = None
        require(core.library.tc_clock_step(*pointers) == 1 and (index == 3 or
                (unpack(result)["fault"] == "invalid_argument" and not result.now_valid and
                 not result.next.previous_present)), f"clock_null_{index}")
    for index in range(8):
        args = fresh()
        clock, decision = ClockResult(), Decision()
        ct.memset(ct.addressof(clock), 255, ct.sizeof(clock))
        ct.memset(ct.addressof(decision), 255, ct.sizeof(decision))
        pointers = [ct.byref(value) for value in args]+[ct.byref(clock), ct.byref(decision)]
        pointers[index] = None
        require(core.library.tc_clocked_decide(*pointers) == 1 and
                (index == 6 or unpack(clock)["fault"] == "invalid_argument") and
                (index == 7 or (not decision.command_allowed and bytes(decision.command) == b"\0"*32)),
                f"composed_null_{index}")
    native = ClockState(255, UINT64_MAX)
    core.library.tc_init_clock(ct.byref(native))
    require(not native.previous_present and not native.previous_tick, "init_clock_zero")
    core.library.tc_init_clock(None)
    require(core.library.tc_clock_abi_sizeof(999) == 0, "unknown_clock_abi_kind")
    # Make the local model's underspecified scenarios concrete, and test its
    # claimed precedence ambiguity rather than adopting it as a finding.
    hypotheses = []
    for label, tick, dt, wanted, anchor in (
        ("model_forward_gap", 100, .05, "cycle_period_mismatch", 100),
        ("model_invalid_dt", 50, 100., "guard_period_mismatch", 50),
        ("precedence_gap_and_invalid_dt", 100, 100., "cycle_period_mismatch", 100),
        ("precedence_invalid_tick_and_dt", None, 100., "invalid_cycle_timestamp", 0),
        ("precedence_duplicate_and_invalid_dt", 0, 100., "nonmonotonic_cycle_timestamp", 0),
    ):
        args = fresh(); args[1] = clock_input(tick, dt)
        clock, decision = core.decide(*args)
        actual = unpack(clock)
        require(actual["fault"] == wanted and actual["previous_tick"] == anchor and
                not decision.command_allowed and bytes(decision.command) == b"\0"*32, label)
        hypotheses.append({"label": label, "previous_tick": 0, "tick": tick, "dt_s": dt,
                           "period_ms": 50, "actual": actual, "final_command": list(decision.command)})
    return {"checks": checks, "byte_tag_substitutions": 768, "sha256": digest.hexdigest(),
            "local_model_hypothesis_checks": hypotheses}


def _worker(library, sender):
    try:
        core = ClockCore(Path(library))
        boundaries = check_clock_boundaries(core)
        first, second = run_clock_parity(core), run_clock_parity(core)
        if first != second:
            raise AssertionError("repeated clock experiment changed deterministic results")
        sender.send({"results": first, "clock_abi_sizes": core.clock_sizes, "boundaries": boundaries})
    except BaseException:
        sender.send({"error": traceback.format_exc()})
    finally:
        sender.close()


def verify_clock_in_child(library):
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(str(library), sender))
    process.start(); sender.close()
    try:
        if not receiver.poll(120):
            raise RuntimeError("clock parity child timed out")
        result = receiver.recv()
        process.join(10)
        if process.is_alive() or process.exitcode != 0 or "error" in result:
            raise RuntimeError(result.get("error", f"clock child exit {process.exitcode}"))
        return result
    finally:
        receiver.close()
        if process.is_alive(): process.terminate()
        process.join(10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if any(args.output.resolve() == (ROOT/name).resolve() or
           (args.output.exists() and args.output.samefile(ROOT/name)) for name in SOURCE_FILES):
        parser.error("output must not overwrite a contributing source or hardlink")
    with tempfile.TemporaryDirectory(prefix="enme408-clock-") as directory:
        library, build = build_library(Path(directory), args.cc)
        result = verify_clock_in_child(library)
        receipt = {"schema": "enme408-portable-clock-parity/v1", "clock_contract_version": CLOCK_CONTRACT_VERSION,
            "numeric_contract_version": NUMERIC_CONTRACT_VERSION, "torque_abi_version": 1, "repeat_agreement": True, "seed": 409,
            "build": build, **result,
            "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES},
            "limits": ["host-only binary64 and normalized uint64 milliseconds; no wrap normalization",
                       "Python keeps unbounded integer time; C decoder rejects unrepresentable values",
                       "external allocator, pedal/latch and slew owners; no full native controller",
                       "no target clock/MCU timing, raw counter provenance, transport, motor or HIL validation"]}
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result["results"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
