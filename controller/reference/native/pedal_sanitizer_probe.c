#include "torque_pedal.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    tc_pedal_facts facts = {0};
    tc_pedal_result result;
    unsigned int tag;
    facts.input_type_valid = facts.config_type_valid = facts.state_type_valid = 1u;
    facts.candidate_type_valid = facts.result_type_valid = 1u;
    facts.candidate_status = TC_ALLOCATION_OK; facts.guard_status = TC_GUARD_OK;
    facts.brake = facts.comms = facts.sensors = facts.interlock = 1u;
    facts.accelerator = (tc_scalar){0.8, 1u}; facts.rise = (tc_scalar){100.0, 1u};
    facts.trip = (tc_scalar){0.6, 1u}; facts.clear = (tc_scalar){0.2, 1u};
    assert(tc_trusted_overlap_trip(&facts) == 1u && tc_trusted_clear_cycle(&facts) == 1u);
    assert(tc_reconcile_pedal_latch(&facts, &result) == 0u);
    assert(result.next_latched == 1u && result.adapter_veto == 1u);
    assert(strcmp(result.reason.value, "brake_accelerator_overlap") == 0);
    for (tag = 0u; tag <= UINT8_MAX; ++tag) {
        facts.comms = (uint8_t)tag;
        assert(tc_trusted_overlap_trip(&facts) == (tag == 1u));
        assert(tc_trusted_clear_cycle(&facts) == (tag == 1u));
        facts.comms = 1u; facts.previous_latched = (uint8_t)tag;
        assert(tc_reconcile_pedal_latch(&facts, &result) == 0u);
        if (tag > 1u) assert(result.next_latched == 1u && result.adapter_veto == 1u);
    }
    facts.previous_latched = 1u; facts.brake = 0u; facts.accelerator.value = 0.1;
    facts.clock_fault_present = 1u;
    assert(tc_reconcile_pedal_latch(&facts, &result) == 0u);
    assert(!result.adapter_veto && result.next_latched);
    facts.accelerator.value = NAN;
    assert(tc_trusted_overlap_trip(&facts) == 0u);
    facts.base_reason.kind = TC_TEXT_STRING;
    memset(facts.base_reason.value, 'A', TC_TEXT_CAPACITY);
    assert(tc_reconcile_pedal_latch(&facts, &result) == 0u && result.adapter_veto && result.next_latched);
    memset(&result, 255, sizeof(result));
    assert(tc_reconcile_pedal_latch(NULL, &result) == 1u && result.adapter_veto && result.next_latched);
    assert(tc_reconcile_pedal_latch(&facts, NULL) == 1u);
    assert(!tc_trusted_overlap_trip(NULL) && !tc_trusted_clear_cycle(NULL));
    puts("C pedal metadata probe passed (including 512 tagged-field substitutions)");
    return 0;
}
