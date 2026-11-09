"""UNTESTED one-tick adapter extracted from the archived bridge.

No guidance/allocator scheduling, line validation, resource guard or dispatch.
The owning future bridge must authenticate inputs and validate output/state.
"""
from dataclasses import replace

from lapsim_light_core.torque_light_combined import advance_combined_light
from lapsim_light_policies.awd_contracts import AVAILABLE
from lapsim_light_policies.core_adapter import ensure_topology

from .input_contracts import require

MAX_CHUNK_WORK = 50000

def advance_tick(settings, heat, policy, act, state, held, steer, friction, env, *, braking_requested, maximum_work):
    """Local WORK-counter view for the unchanged integrator's absolute cap.

    Only three diagnostic counters are rebased; no integrated state, energy,
    clock, event dissipation or controller input is reset. A rejected interval
    returns nothing and cannot commit its provisional counters. This is an
    isolated new adapter requiring parity and high-counter regressions.
    """
    ensure_topology(act, AVAILABLE)
    require(type(maximum_work) is int and 1 <= maximum_work <= MAX_CHUNK_WORK, "Per-call work remainder exceeded")
    previous = state.thermal.light.powered
    local_power = replace(previous, integration_trials=0, integration_substeps=0, wheel_stop_events=0)
    local_state = replace(state, thermal=replace(state.thermal, light=replace(state.thermal.light, powered=local_power)))
    updated = advance_combined_light(settings, heat, policy, act, local_state, held, steer, friction,
        AVAILABLE, env, braking_requested=braking_requested, maximum_work=maximum_work)
    power = updated.thermal.light.powered
    restored = replace(power, integration_trials=previous.integration_trials + power.integration_trials,
                       integration_substeps=previous.integration_substeps + power.integration_substeps,
                       wheel_stop_events=previous.wheel_stop_events + power.wheel_stop_events)
    return replace(updated, thermal=replace(updated.thermal, light=replace(updated.thermal.light, powered=restored)))
