"""UNTESTED integer-clock/chunk planning. No numerical step or admission.

These are the archived global phases, not clocks reset at chunk boundaries.
Full physical/checkpoint/line validation and original runtime guards remain
separate requirements before a future owner may execute any planned interval.
"""
from .input_contracts import decode, digest, encode, is_sha256, require
from . import raw_journal as journal


SCHEMA = "lapsim.light-global-clock-chunk-plan.v1"
MAX_PLAN_BYTES = 64 * 1024
MAX_MISSION_TICKS = 1_030_000
MAX_MISSION_WORK = 8_240_000
MAX_CHUNK_TICKS = 10_000
MAX_CHUNK_WORK = 50_000
ALLOCATOR_INTERVENTION_FIELDS = (
    "slip_interventions", "yaw_interventions", "reserve_interventions", "regen_inhibited_updates",
    "load_interventions", "energy_interventions", "feedforward_interventions",
)
TICK_DIAGNOSTIC_FIELDS = ("electrical_limit_ticks", "generating_boundaries", "brake_redistribution_ticks")


def _integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, "Bounded integer " + name + " required")


def boundary_counts(tick):
    """Counts committed after `tick` complete 1 ms intervals, including origin."""
    _integer(tick, 0, MAX_MISSION_TICKS, "tick")
    return {"driver_updates": (tick + 49) // 50,
            "allocator_updates": (tick + 9) // 10, "blend_updates": tick}


def _transition_ticks(start_tick, end_tick):
    _integer(start_tick, 0, MAX_MISSION_TICKS, "transition start tick")
    _integer(end_tick, start_tick, min(start_tick + MAX_CHUNK_TICKS, MAX_MISSION_TICKS), "transition end tick")
    return end_tick - start_tick


def require_committed_work_transition(before, after, *, start_tick, end_tick, maximum_new_work):
    """Existing integrator counter invariants only; no numerical work or admission."""
    ticks = _transition_ticks(start_tick, end_tick)
    _integer(maximum_new_work, 1, MAX_CHUNK_WORK, "new-work ceiling")
    names = ("integration_trials", "integration_substeps", "wheel_stop_events")
    require(type(before) is dict and type(after) is dict and
            all(name in before and name in after for name in names), "Complete integration counters required")
    for state in (before, after):
        for name in names:
            _integer(state[name], 0, MAX_MISSION_WORK, name)
        require(state["integration_substeps"] <= state["integration_trials"],
                "Accepted integration substeps exceed trials")
    delta = {name: after[name] - before[name] for name in names}
    require(all(value >= 0 for value in delta.values()) and
            delta["integration_substeps"] >= ticks and
            delta["integration_trials"] >= delta["integration_substeps"],
            "New committed ticks/substeps/trials disagree; historical work cannot be reused")
    require(ticks > 0 or all(value == 0 for value in delta.values()),
            "A rejected zero-tick chunk cannot commit provisional integration work")
    work = delta["integration_trials"] + delta["wheel_stop_events"]
    require(work <= maximum_new_work, "New committed work exceeds reviewed allowance")
    return work


def require_clocked_counter_transition(before, after, *, start_tick, end_tick):
    """Bound existing diagnostic increments by newly committed global events."""
    ticks = _transition_ticks(start_tick, end_tick)
    old_counts, new_counts = boundary_counts(start_tick), boundary_counts(end_tick)
    names = (*old_counts, *ALLOCATOR_INTERVENTION_FIELDS, *TICK_DIAGNOSTIC_FIELDS)
    require(type(before) is dict and type(after) is dict and
            all(name in before and name in after for name in names), "Complete clocked counters required")
    for memory, counts, tick in ((before, old_counts, start_tick), (after, new_counts, end_tick)):
        for name, count in counts.items():
            require(type(memory[name]) is int and memory[name] == count, "Global committed controller clock differs")
        for name in ALLOCATOR_INTERVENTION_FIELDS:
            _integer(memory[name], 0, counts["allocator_updates"], name)
        for name in TICK_DIAGNOSTIC_FIELDS:
            _integer(memory[name], 0, tick, name)
    allocator_updates = new_counts["allocator_updates"] - old_counts["allocator_updates"]
    for names, maximum in ((ALLOCATOR_INTERVENTION_FIELDS, allocator_updates), (TICK_DIAGNOSTIC_FIELDS, ticks)):
        require(all(0 <= after[name] - before[name] <= maximum for name in names),
                "Diagnostic counter increase exceeds newly committed clock events")


def interval_actions(tick):
    """Actions at the start and scheduled output after one global interval.

    Initial, chunk-boundary and terminal rows are additional runner obligations;
    nominal output flags never authorize dropping those raw boundary samples.
    """
    _integer(tick, 0, MAX_MISSION_TICKS - 1, "interval-start tick")
    end = tick + 1
    return {"start_tick": tick, "end_tick": end, "plant_period_s": .001,
            "driver_due": tick % 50 == 0, "allocator_due": tick % 10 == 0,
            "blend_due": True, "scheduled_log_due_after": end % 20 == 0,
            "progress_due_after": end % 100 == 0}


def _plan(checkpoint_raw, expected_checkpoint_sha256, expected_identity, ticks):
    require(is_sha256(expected_checkpoint_sha256), "Independently pinned parent checkpoint required")
    journal._validate_identity(expected_identity)
    checkpoint = decode(checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)
    before = journal._bind_checkpoint(checkpoint, expected_identity)
    require(checkpoint["checkpoint_sha256"] == expected_checkpoint_sha256 and before["status"] == "running",
            "Parent identity differs or checkpoint is terminal")
    require(before["segment"] < journal.MAX_RECORDS, "No remaining chunk/checkpoint chain slots")
    context = before["context"]
    require(context["mode"] == "one_lap", "Only the archived one-lap mission is planned")
    driver = context["driver"]
    require(type(driver["initial_speed_mps"]) in (int, float) and driver["initial_speed_mps"] == 0.,
            "Explicit standing-start driver required; no historical moving-start reuse")
    limits = context["limits"]
    maximum_ticks, maximum_work = limits["maximum_ticks"], limits["maximum_work"]
    _integer(maximum_ticks, 1, MAX_MISSION_TICKS, "mission horizon")
    _integer(maximum_work, 1, MAX_MISSION_WORK, "mission work")
    require(type(limits["logging_ticks"]) is int and limits["logging_ticks"] == 20,
            "Archived global logging clock required")
    start = before["tick"]
    _integer(start, 0, maximum_ticks - 1, "running checkpoint tick")
    _integer(ticks, 1, MAX_CHUNK_TICKS, "requested chunk ticks")
    state, memory = before["state"], before["memory"]
    thermal = state["thermal"]
    light = thermal["light"]
    power = light["powered"]
    for value in (state["drs"]["ticks"], thermal["thermal"]["ticks"], light["feedback_ticks"]):
        require(type(value) is int and value == start, "Checkpoint component clocks disagree")
    counts = boundary_counts(start)
    for name, count in counts.items():
        require(type(memory[name]) is int and memory[name] == count,
                "Checkpoint global controller phase differs: " + name)
    for name in ("integration_trials", "integration_substeps", "wheel_stop_events"):
        _integer(power[name], 0, maximum_work, name)
    require(start <= power["integration_substeps"] <= power["integration_trials"],
            "Checkpoint integration counts contradict its global tick")
    used_work = power["integration_trials"] + power["wheel_stop_events"]
    require(used_work < maximum_work, "No remaining mission work")
    end = min(start + ticks, maximum_ticks)
    end_counts = boundary_counts(end)
    body = {
        "schema": SCHEMA,
        "identity": decode(encode(expected_identity), MAX_PLAN_BYTES),
        "parent_checkpoint_sha256": expected_checkpoint_sha256,
        "context_sha256": before["context_sha256"], "start_tick": start, "end_tick_ceiling": end,
        "requested_ticks": ticks, "maximum_new_ticks": end - start,
        "mission_maximum_ticks": maximum_ticks, "mission_maximum_work": maximum_work,
        "work_at_start": used_work, "maximum_new_work": min(MAX_CHUNK_WORK, maximum_work - used_work),
        "clocks": {"plant_period_s": .001, "driver_interval_ticks": 50,
                   "allocator_interval_ticks": 10, "logging_interval_ticks": 20,
                   "progress_interval_ticks": 100},
        "maximum_updates": {name: end_counts[name] - count for name, count in counts.items()},
        "scheduled_log_boundaries": end // 20 - start // 20,
        "scheduled_progress_boundaries": end // 100 - start // 100,
        "boundary_rows": "Initial chunk row and unsampled final/terminal row remain required",
        "evidence_status": "CONSISTENCY_PLAN_ONLY_PENDING_ORIGINAL_OWNER_ADMISSION",
        "qualification_or_execution_authority": False,
        "full_checkpoint_validation_performed": False, "numerical_step_performed": False,
    }
    value = {"plan": body, "plan_sha256": digest(body)}
    require(len(encode(value)) <= MAX_PLAN_BYTES, "Chunk plan exceeds bound")
    return value


def plan_chunk(checkpoint_raw, *, expected_checkpoint_sha256, expected_identity, ticks):
    """Stage global phases and finite ceilings; never resume or advance a plant."""
    try:
        return _plan(checkpoint_raw, expected_checkpoint_sha256, expected_identity, ticks)
    except (KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError("Malformed checkpoint/identity for chunk planning") from error
