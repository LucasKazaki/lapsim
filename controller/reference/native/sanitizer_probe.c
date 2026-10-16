/* Host-only memory/UB boundary probe. No transport or target startup code. */
#include "torque_contract.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static tc_allocation ordinary(void) {
    tc_allocation value = {0};
    size_t index;
    value.type_valid = 1u;
    value.status = TC_ALLOCATION_OK;
    value.wheel_vector_valid = 1u;
    value.requested.numeric = value.delivered.numeric = 1u;
    value.requested.value = value.delivered.value = 40.0;
    for (index = 0u; index < TC_WHEELS; ++index) {
        value.wheels[index].numeric = 1u;
        value.wheels[index].value = 10.0;
    }
    return value;
}

int main(void) {
    unsigned int tag;
    tc_allocation value;
    tc_cycle cycle = {0};
    tc_snapshot previous = {TC_READY, 0u, 0u};
    tc_policy policy = {2u};
    tc_decision output;
    size_t index;
    assert(tc_validate_allocation(NULL) == TC_INVALID_CANDIDATE_TYPE);
    for (tag = 0u; tag <= UINT8_MAX; ++tag) {
        value = ordinary(); value.type_valid = (uint8_t)tag;
        assert(tc_validate_allocation(&value) == (tag == 1u ? TC_CONTRACT_OK : TC_INVALID_CANDIDATE_TYPE));
        value = ordinary(); value.wheel_vector_valid = (uint8_t)tag;
        assert(tc_validate_allocation(&value) == (tag == 1u ? TC_CONTRACT_OK : TC_INVALID_CANDIDATE_OUTPUT));
        value = ordinary(); value.requested.numeric = (uint8_t)tag;
        assert(tc_validate_allocation(&value) == (tag == 1u ? TC_CONTRACT_OK : TC_INVALID_CANDIDATE_REQUESTED));
    }
    value = ordinary(); value.fault.kind = TC_TEXT_STRING;
    memset(value.fault.value, 'A', TC_TEXT_CAPACITY);
    assert(tc_validate_allocation(&value) == TC_INVALID_CANDIDATE_FAULT);
    value.fault.kind = TC_TEXT_NONE;
    assert(tc_validate_allocation(&value) == TC_CONTRACT_OK);
    value = ordinary(); value.wheels[0].value = NAN;
    assert(tc_validate_allocation(&value) == TC_INVALID_CANDIDATE_OUTPUT);
    value = ordinary(); value.wheels[0].value = INFINITY;
    assert(tc_validate_allocation(&value) == TC_INVALID_CANDIDATE_OUTPUT);
    value = ordinary();
    for (index = 0u; index < TC_WHEELS; ++index) value.wheels[index].value = 0.0;
    value.wheels[0].value = DBL_MIN;
    value.requested.value = value.delivered.value = 2.0 * DBL_MIN;
    assert(tc_validate_allocation(&value) == TC_CANDIDATE_SUM_MISMATCH);
    cycle.allocation = ordinary(); cycle.guard.status = TC_GUARD_OK; cycle.guard.output_valid = 1u;
    for (index = 0u; index < TC_WHEELS; ++index) cycle.guard.output[index] = cycle.allocation.wheels[index];
    assert(tc_decide(&previous, &cycle, &policy, &output) == 0u);
    assert(output.command_allowed == 1u);
    previous.state = TC_RECOVERY_PENDING; previous.recovery_streak = UINT32_MAX;
    assert(tc_decide(&previous, &cycle, &policy, &output) == 0u);
    assert(output.next.state == TC_INHIBITED && output.command_allowed == 0u);
    for (index = 0u; index < TC_WHEELS; ++index) assert(output.command[index] == 0.0);
    memset(&output, 255, sizeof(output));
    assert(tc_decide(NULL, &cycle, &policy, &output) == 1u);
    assert(output.next.state == TC_INHIBITED && output.command_allowed == 0u);
    for (index = 0u; index < TC_WHEELS; ++index) assert(output.command[index] == 0.0);
    puts("C host boundary probe passed (including 768 tagged-field substitutions)");
    return 0;
}
