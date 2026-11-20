"""Source-bound synthetic lap mission and accepted-feedback monitor; no scientific imports.

Derived from the retained FSI finite physical-gate rule and r07 coherent start
heading. Monitor checkpoints do NOT restore a driver/controller/Light session.
No constructor, stepping, runtime admission, resource or process operation exists.
"""
from hashlib import sha256
import json
from math import atan2, cos, sin, isfinite, hypot

COURSE_ID = 'public_synthetic_stadium_150m'
REVISION = 'synthetic-arc-fixture-v1'
COURSE_RAW_SHA256 = 'a4ed7fbcc850ab5ba9e03407990fee9b1daca720f26c1780f2b5cb78f5f4f3c8'
GEOMETRY_SHA256 = 'b68a3bb354ab459af5cd8a783013818d22440e56a5b09acff328134384b131ba'
SCOPE = 'public independently generated synthetic stadium; no real course or calibration claim'


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def clone(value):
    return json.loads(canonical(value))


def finite(value):
    return type(value) in (int, float) and isfinite(value)


def pin(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class MichiganGate:
    """A data binding constructed only from the exact staged course bytes."""
    def __init__(self, course_raw):
        require(type(course_raw) is bytes and sha256(course_raw).hexdigest() == COURSE_RAW_SHA256,
                "Exact pinned synthetic course bytes required")
        course = json.loads(course_raw)
        require(course["course_id"] == COURSE_ID and course["revision"] == REVISION,
                "Synthetic course identity differs")
        geometry = course["geometry"]
        view = {k: geometry[k] for k in ("closed", "distance_m", "x_m", "y_m", "curvature_per_m")}
        require(geometry["closed"] is True and digest(view) == course["geometry_sha256"] == GEOMETRY_SHA256,
                "Pinned closed synthetic geometry required")
        distance, x, y, curvature = (geometry[k] for k in ("distance_m", "x_m", "y_m", "curvature_per_m"))
        require(len(x) == len(y) == len(distance) == len(curvature) + 1 and distance[0] == 0
                and x[0] == x[-1] and y[0] == y[-1], "Closed source seam required")
        heading = atan2(y[1] - y[0], x[1] - x[0]) - curvature[0] * (distance[1] - distance[0]) / 2
        self._course_json = canonical(course)
        self._json = canonical({"course_id": COURSE_ID, "revision": REVISION,
            "course_raw_sha256": COURSE_RAW_SHA256, "geometry_sha256": GEOMETRY_SHA256,
            "origin_xy_m": [x[0], y[0]], "forward_unit": [cos(heading), sin(heading)],
            "source_length_m": distance[-1], "finite_half_width_m": course["ai_defaults"]["half_width_m"],
            "heading_rule": "r07 coherent chord heading minus first curvature*cell_length/2",
            "scope": SCOPE})

    @property
    def value(self): return json.loads(self._json)

    @property
    def identity(self): return sha256(self._json.encode()).hexdigest()


def prepare_one_lap_case(gate, original_case, *, maximum_duration_ms):
    """Change only the explicit finite mission horizon, before initialization."""
    require(type(gate) is MichiganGate, "Pinned Michigan gate binding required")
    require(type(maximum_duration_ms) is int and 500 < maximum_duration_ms <= 300000,
            "Explicit longer finite horizon within existing SharedLightSession domain required")
    require(original_case["course_bundle"] == json.loads(gate._course_json)
            and original_case["laps"] == 1 and original_case["duration_s"] == 0.5,
            "Exact staged one-lap diagnostic Case required")
    result = clone(original_case)
    result["duration_s"] = maximum_duration_ms / 1000
    return {"case": result, "mission": "one_lap", "gate_sha256": gate.identity, "scope": SCOPE,
            "scientific_session_initialized": False}


def _state(value, capacity):
    require(type(value) is dict and pin(value.get("model_sha256")), "Complete source state/model identity required")
    light = value["thermal"]["light"]
    tick, power = light["feedback_ticks"], light["powered"]
    require(type(tick) is int and tick >= 0, "Accepted integer feedback clock required")
    x, y, energy = power["plant"]["x_m"], power["plant"]["y_m"], power["pack_energy_j"]
    require(all(finite(v) for v in (x, y, energy)) and 0 <= energy <= capacity,
            "Finite accepted pose and in-domain pack energy required")
    return tick, [x, y], energy


def new_monitor(gate, initial_state, *, pack_capacity_j, context_sha256):
    require(type(gate) is MichiganGate and finite(pack_capacity_j) and pack_capacity_j > 0 and pin(context_sha256),
            "Explicit pinned gate/context and source pack capacity required")
    tick, pose, energy = _state(initial_state, pack_capacity_j)
    require(tick == 0 and pose == gate.value["origin_xy_m"], "Exact r07 source seam initialization required")
    return {"schema": "lapsim.mi26-feedback-lap-monitor.v2", "gate_sha256": gate.identity,
            "context_sha256": context_sha256, "pack_capacity_j": pack_capacity_j,
            "initial_pack_energy_j": energy, "initial_state": clone(initial_state),
            "initial_state_sha256": digest(initial_state), "accepted_state": clone(initial_state),
            "accepted_state_sha256": digest(initial_state), "last_source_progress_m": 0.0,
            "crossing": None, "scope": SCOPE, "checkpoint_role": "monitor_only_not_scientific_session_restore"}


def _crossing(gate, before, after, source_before, source_after, initial_energy, capacity):
    tick0, p0, e0 = _state(before, capacity)
    tick1, p1, e1 = _state(after, capacity)
    require(tick1 == tick0 + 1, "One accepted 1ms feedback interval required")
    g = gate.value
    origin, forward = g["origin_xy_m"], g["forward_unit"]
    normal = [-forward[1], forward[0]]
    local = lambda point, axis: sum((point[i] - origin[i]) * axis[i] for i in (0, 1))
    d0, d1 = local(p0, forward), local(p1, forward)
    if not (d0 < 0 <= d1) or source_after < 0.75 * g["source_length_m"]:
        return None
    fraction = -d0 / (d1 - d0)
    lateral = local(p0, normal) + fraction * (local(p1, normal) - local(p0, normal))
    if abs(lateral) > g["finite_half_width_m"]:
        return None
    # Preserve the existing FSI winding/1ms consistency bounds, not car calibration.
    require(abs(source_after - g["source_length_m"]) <= 2 and 0 < d1 - d0 <= 0.5
            and abs(source_after - source_before) <= 12.
            and hypot(p1[0]-p0[0],p1[1]-p0[1]) <= .5, "Physical seam/source winding inconsistent")
    energy = e0 + fraction * (e1 - e0)
    return {"lap": 1, "boundary_tick_ms": tick1, "gate_sha256": gate.identity,
            "fraction": fraction, "time_s": (tick0 + fraction) / 1000,
            "pack_energy_j": energy, "lap_net_battery_wh": (initial_energy - energy) / 3600,
            "source_progress_endpoints_m": [source_before, source_after],
            "gate_signed_distances_m": [d0, d1], "lateral_crossing_m": lateral,
            "before_state": clone(before), "accepted_state_sha256": digest(after),
            "scope": SCOPE + "; interpolate time/energy only; retain full accepted endpoint state"}


def _validate(gate, monitor):
    require(type(gate) is MichiganGate and monitor["schema"] == "lapsim.mi26-feedback-lap-monitor.v2"
            and monitor["gate_sha256"] == gate.identity and monitor["scope"] == SCOPE
            and monitor["checkpoint_role"] == "monitor_only_not_scientific_session_restore"
            and pin(monitor["context_sha256"]), "Monitor source/role differs")
    require(finite(monitor["pack_capacity_j"]) and monitor["pack_capacity_j"] > 0
            and digest(monitor["initial_state"]) == monitor["initial_state_sha256"], "Initial state/capacity differs")
    initial_tick, initial_pose, initial_energy = _state(monitor["initial_state"], monitor["pack_capacity_j"])
    require(initial_tick == 0 and initial_pose == gate.value["origin_xy_m"]
            and initial_energy == monitor["initial_pack_energy_j"], "Initial seam/energy differs")
    require(digest(monitor["accepted_state"]) == monitor["accepted_state_sha256"], "Accepted state hash differs")
    _state(monitor["accepted_state"], monitor["pack_capacity_j"])
    require(monitor["accepted_state"]["model_sha256"] == monitor["initial_state"]["model_sha256"]
            and finite(monitor["last_source_progress_m"])
            and -0.5 <= monitor["last_source_progress_m"] <= gate.value["source_length_m"] + 1,
            "Current model/progress differs")
    require(finite(monitor["initial_pack_energy_j"]) and 0 <= monitor["initial_pack_energy_j"] <= monitor["pack_capacity_j"],
            "Explicit initial pack energy required")
    if monitor["crossing"] is not None:
        event = monitor["crossing"]
        expected = _crossing(gate, event["before_state"], monitor["accepted_state"],
            *event["source_progress_endpoints_m"], monitor["initial_pack_energy_j"], monitor["pack_capacity_j"])
        require(expected is not None and canonical(expected) == canonical(event)
                and event["source_progress_endpoints_m"][1] == monitor["last_source_progress_m"],
                "Monitor finish receipt differs from accepted physical endpoints")


def accept_segment(gate, monitor, feedback, *, source_terminal):
    """Validate supplied accepted data; never project, step, restore or mutate physics.

    Requires added per-feedback source projection from the existing source-pinned
    pose_driver._project_local port. The r13 thin trace alone lacks these inputs.
    """
    _validate(gate, monitor)
    require(source_terminal is None, "A source refusal/duration stop cannot be relabeled a lap")
    require(type(feedback) is list and 1 <= len(feedback) <= 4000, "Existing finite chunk domain required")
    result = clone(monitor)
    length = gate.value["source_length_m"]
    for row in feedback:
        require(type(row) is dict and set(row) >= {"from_ms", "until_ms", "context_sha256",
                "input_state_sha256", "accepted_state_sha256", "complete_accepted_state", "source_projection"},
                "Accepted feedback needs complete source/context and per-feedback projection")
        require(result["crossing"] is None, "No feedback after the first accepted lap crossing")
        before, after = result["accepted_state"], row["complete_accepted_state"]
        t0, pose0, _ = _state(before, result["pack_capacity_j"])
        t1, pose1, _ = _state(after, result["pack_capacity_j"])
        require(hypot(pose1[0]-pose0[0],pose1[1]-pose0[1]) <= .5, "Physical1ms translation exceeds supported bound")
        require(type(row["from_ms"]) is int and type(row["until_ms"]) is int
                and row["from_ms"] == t0 and row["until_ms"] == t1 == t0 + 1,
                "Skipped/duplicate feedback or segment clock reset")
        require(row["context_sha256"] == result["context_sha256"]
                and row["input_state_sha256"] == result["accepted_state_sha256"]
                and row["accepted_state_sha256"] == digest(after)
                and after["model_sha256"] == before["model_sha256"], "Feedback state/context/model lineage differs")
        projection = row["source_projection"]
        require(type(projection) is dict and set(projection) == {"before_m", "after_m", "geometry_sha256"},
                "Exact per-feedback source projection required")
        s0, s1 = projection["before_m"], projection["after_m"]
        require(projection["geometry_sha256"] == GEOMETRY_SHA256 and all(finite(v) for v in (s0, s1))
                and s0 == result["last_source_progress_m"] and abs(s1 - s0) <= 12.
                and -0.5 <= s0 <= length + 1 and -0.5 <= s1 <= length + 1,
                "Missing, wrapped, outside original local window or differently sourced projection")
        result["crossing"] = _crossing(gate, before, after, s0, s1,
            result["initial_pack_energy_j"], result["pack_capacity_j"])
        result["accepted_state"] = clone(after)
        result["accepted_state_sha256"] = row["accepted_state_sha256"]
        result["last_source_progress_m"] = s1
    _validate(gate, result)
    return result


def checkpoint_monitor(gate, monitor):
    _validate(gate, monitor)
    return {"monitor": clone(monitor), "monitor_sha256": digest(monitor)}


def resume_monitor(gate, checkpoint, *, expected_context_sha256, expected_initial_state_sha256):
    require(set(checkpoint) == {"monitor", "monitor_sha256"}
            and digest(checkpoint["monitor"]) == checkpoint["monitor_sha256"], "Monitor checkpoint hash differs")
    _validate(gate, checkpoint["monitor"])
    require(checkpoint["monitor"]["context_sha256"] == expected_context_sha256
            and checkpoint["monitor"]["initial_state_sha256"] == expected_initial_state_sha256,
            "Monitor must match the actual source constructor context/initial state")
    return clone(checkpoint["monitor"])
