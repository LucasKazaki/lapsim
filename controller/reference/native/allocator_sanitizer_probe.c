#include "torque_allocator.h"
#include "torque_guard.h"

#include <assert.h>
#include <float.h>
#include <math.h>
#include <string.h>

static void zero_fault(const tc_allocation *result) {
    size_t i;
    assert(result->status == TC_ALLOCATION_FAULT);
    assert(result->delivered.value == 0.0 && !signbit(result->delivered.value));
    assert(result->type_valid == 1u && result->wheel_vector_valid == 1u);
    for (i = 0u; i < TC_WHEELS; ++i) {
        assert(result->wheels[i].numeric == 1u);
        assert(result->wheels[i].value == 0.0 && !signbit(result->wheels[i].value));
    }
}

int main(void) {
    tc_allocator_input input;
    tc_allocator_config config = {1u, 1u, 50u};
    tc_allocation result;
    size_t i;
    unsigned tag, mask;
    memset(&input, 0, sizeof(input));
    input.type_valid = input.now_valid = input.timestamp_valid = 1u;
    input.now_ms = input.input_timestamp_ms = UINT64_MAX;
    input.request.numeric = 1u; input.request.value = 40.0;
    input.limits_vector_valid = input.enabled_vector_valid = input.external_interlock = 1u;
    input.torque_unit.kind = TC_TEXT_STRING;
    memcpy(input.torque_unit.value, "N*m", 4u);
    for (i = 0u; i < TC_WHEELS; ++i) {
        input.limits[i].numeric = input.enabled[i] = 1u;
        input.limits[i].value = 20.0;
    }
    assert(tc_allocate_propulsive_torque(&input, &config, &result) == 0u);
    assert(result.status == TC_ALLOCATION_OK && result.delivered.value == 40.0);
    for (tag = 0u; tag < 256u; ++tag) {
        tc_allocator_input changed = input;
        changed.request.numeric = (uint8_t)tag;
        assert(tc_allocate_propulsive_torque(&changed, &config, &result) == 0u);
        if (tag != 1u) zero_fault(&result);
        changed = input; changed.enabled[3] = (uint8_t)tag;
        assert(tc_allocate_propulsive_torque(&changed, &config, &result) == 0u);
        if (tag > 1u) zero_fault(&result);
        changed = input; changed.torque_unit.kind = (uint8_t)tag;
        assert(tc_allocate_propulsive_torque(&changed, &config, &result) == 0u);
        if (tag != TC_TEXT_STRING) zero_fault(&result);
    }
    for (mask = 0u; mask < 16u; ++mask) {
        tc_allocator_input changed = input;
        changed.request.value = DBL_MAX;
        for (i = 0u; i < TC_WHEELS; ++i) {
            changed.enabled[i] = (uint8_t)((mask >> i) & 1u);
            changed.limits[i].value = DBL_MAX;
        }
        assert(tc_allocate_propulsive_torque(&changed, &config, &result) == 0u);
        if (mask == 0u) zero_fault(&result);
    }
    input.request.value = NAN;
    assert(tc_allocate_propulsive_torque(&input, &config, &result) == 0u); zero_fault(&result);
    input.request.value = -INFINITY;
    assert(tc_allocate_propulsive_torque(&input, &config, &result) == 0u); zero_fault(&result);
    input.request.value = 1.0;
    memset(input.torque_unit.value, 'A', TC_TEXT_CAPACITY);
    assert(tc_allocate_propulsive_torque(&input, &config, &result) == 0u); zero_fault(&result);
    memset(input.torque_unit.value, 0, TC_TEXT_CAPACITY);
    memcpy(input.torque_unit.value, "N*m\0ignored", sizeof("N*m\0ignored"));
    input.limits[0].value = 1.0 + 1e-12;
    for (i = 1u; i < TC_WHEELS; ++i) input.enabled[i] = 0u;
    assert(tc_allocate_propulsive_torque(&input, &config, &result) == 0u);
    assert(result.status == TC_ALLOCATION_OK);
    assert(tc_validate_allocation(&result) == TC_CANDIDATE_EXCEEDS_REQUEST);
    {
        tc_command_guard_input gi;
        tc_command_guard_config gc;
        tc_command_guard_state previous;
        tc_command_guard_result guarded;
        tc_cycle cycle;
        tc_snapshot snapshot = {TC_READY, 0u, 0u};
        tc_policy policy = {2u};
        tc_decision decision;
        memset(&gi, 0, sizeof(gi)); memset(&gc, 0, sizeof(gc));
        gi.type_valid = gi.dt_s.numeric = gi.accelerator.numeric = 1u;
        gi.dt_s.value = 0.05; gi.accelerator.value = 0.4;
        gi.comms = gi.sensors = gi.interlock = 1u;
        gc.type_valid = gc.max_rise.numeric = gc.trip.numeric = gc.clear.numeric = 1u;
        gc.max_rise.value = 100.0; gc.trip.value = 0.6; gc.clear.value = 0.2;
        tc_init_command_guard_state(&previous);
        assert(tc_apply_command_guard(&result, &gi, &gc, &previous, &guarded) == 0u);
        assert(guarded.guard.status == TC_GUARD_INHIBITED);
        memset(&cycle, 0, sizeof(cycle)); cycle.allocation = result; cycle.guard = guarded.guard;
        assert(tc_decide(&snapshot, &cycle, &policy, &decision) == 0u);
        assert(decision.command_allowed == 0u);
        for (i = 0u; i < TC_WHEELS; ++i)
            assert(decision.command[i] == 0.0 && !signbit(decision.command[i]));
    }
    memset(&result, 255, sizeof(result));
    assert(tc_allocate_propulsive_torque(NULL, &config, &result) == 1u); zero_fault(&result);
    memset(&result, 255, sizeof(result));
    assert(tc_allocate_propulsive_torque(&input, NULL, &result) == 1u); zero_fault(&result);
    assert(tc_allocate_propulsive_torque(&input, &config, NULL) == 1u);
    assert(tc_allocator_version() == 1u && tc_allocator_abi_sizeof(999u) == 0u);
    return 0;
}
