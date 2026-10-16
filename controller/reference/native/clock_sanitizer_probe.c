/* Standalone host probe for ASAN/UBSan; no timer, transport or motor IO. */
#include "torque_clock.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    unsigned int tag;
    tc_clock_state previous = {1u, 0u};
    tc_clock_input input = {50u, 1u, {0.05, 1u}};
    tc_clock_policy policy = {50u};
    tc_clock_result output;
    tc_snapshot gate_previous = {TC_READY, 0u, 0u};
    tc_cycle cycle = {0};
    tc_policy gate_policy = {2u};
    tc_decision decision;
    size_t index;
    cycle.allocation.type_valid = cycle.allocation.wheel_vector_valid = 1u;
    cycle.allocation.status = TC_ALLOCATION_OK;
    cycle.allocation.requested = cycle.allocation.delivered = (tc_scalar){40.0, 1u};
    cycle.guard.status = TC_GUARD_OK; cycle.guard.output_valid = 1u;
    for (index = 0u; index < TC_WHEELS; ++index)
        cycle.allocation.wheels[index] = cycle.guard.output[index] = (tc_scalar){10.0, 1u};
    for (tag = 0u; tag <= UINT8_MAX; ++tag) {
        input.timestamp_valid = (uint8_t)tag;
        assert(tc_clocked_decide(&previous, &input, &policy, &gate_previous, &cycle,
                                &gate_policy, &output, &decision) == 0u);
        assert(decision.command_allowed == (tag == 1u));
        if (tag != 1u) for (index = 0u; index < TC_WHEELS; ++index) assert(decision.command[index] == 0.0);
        input.timestamp_valid = 1u; input.dt_s.numeric = (uint8_t)tag;
        assert(tc_clock_step(&previous, &input, &policy, &output) == 0u);
        assert((output.fault.kind == TC_TEXT_NONE) == (tag == 1u));
        input.dt_s.numeric = 1u; previous.previous_present = (uint8_t)tag;
        assert(tc_clock_step(&previous, &input, &policy, &output) == 0u);
        assert((output.fault.kind == TC_TEXT_NONE) == (tag <= 1u));
        previous.previous_present = 1u;
    }
    previous.previous_tick = UINT64_MAX-50u; input.now_ms = UINT64_MAX;
    assert(tc_clock_step(&previous, &input, &policy, &output) == 0u && output.fault.kind == TC_TEXT_NONE);
    previous = output.next; input.now_ms = 0u;
    assert(tc_clock_step(&previous, &input, &policy, &output) == 0u);
    assert(strcmp(output.fault.value, "nonmonotonic_cycle_timestamp") == 0);
    assert(output.next.previous_tick == UINT64_MAX);
    policy.period_ms = 0u;
    assert(tc_clock_step(&previous, &input, &policy, &output) == 0u);
    assert(strcmp(output.fault.value, "invalid_clock_policy") == 0);
    assert(!output.next.previous_present && !output.next.previous_tick && !output.now_valid && !output.now_ms);
    policy.period_ms = 50u;
    input.dt_s.value = NAN;
    assert(tc_clocked_decide(&previous, &input, &policy, &gate_previous, &cycle,
                            &gate_policy, &output, &decision) == 0u && !decision.command_allowed);
    memset(&output, 255, sizeof(output)); memset(&decision, 255, sizeof(decision));
    assert(tc_clocked_decide(NULL, &input, &policy, &gate_previous, &cycle,
                            &gate_policy, &output, &decision) == 1u);
    assert(!output.now_valid && output.fault.kind == TC_TEXT_STRING && !decision.command_allowed);
    for (index = 0u; index < TC_WHEELS; ++index) assert(decision.command[index] == 0.0);
    assert(tc_clock_step(NULL, NULL, NULL, NULL) == 1u);
    tc_init_clock(NULL);
    puts("C normalized-clock probe passed (including 768 tagged-field substitutions)");
    return 0;
}
