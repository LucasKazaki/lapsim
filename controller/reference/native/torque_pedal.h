#ifndef ENME408_TORQUE_PEDAL_H
#define ENME408_TORQUE_PEDAL_H

#include "torque_contract.h"

#define TC_PEDAL_ADAPTER_VERSION 1u
/* Metadata for the two narrow trust predicates and their adapter decisions.
 * An external base guard MUST own the original latch/slew/result generation.
 * These predicates do not validate candidate vectors or attest pedal sources.
 * Type tags exactly 1 mean the expected ordinary source type; Boolean fields
 * encode false=0/true=1, every other byte denotes malformed source metadata. */
typedef struct {
    uint8_t input_type_valid, config_type_valid, state_type_valid;
    uint8_t previous_latched, base_next_latched;
    tc_scalar accelerator, rise, trip, clear;
    uint8_t brake, comms, sensors, interlock;
    uint8_t candidate_type_valid, candidate_status;
    uint8_t result_type_valid, guard_status;
    uint8_t clock_fault_present;
    tc_text base_reason;
} tc_pedal_facts;

typedef struct {
    uint8_t trip_observed, clear_cycle_trusted;
    uint8_t adapter_veto, next_latched;
    tc_text reason;
} tc_pedal_result;

TC_API uint32_t tc_pedal_adapter_version(void);
/* kind1=facts, kind2=result; other values return 0. Additive host ABI only. */
TC_API size_t tc_pedal_abi_sizeof(uint32_t kind);
TC_API uint8_t tc_trusted_overlap_trip(const tc_pedal_facts *facts);
TC_API uint8_t tc_trusted_clear_cycle(const tc_pedal_facts *facts);
/* No torque vector is generated or authorized by this component. A veto means
 * the caller MUST use an inhibited, exact-zero guard before the final gate.
 * A non-veto retains the externally computed base guard; it is not permission
 * for torque. Clock faults independently inhibit through the clock/final gate.
 * A successful call can veto; inspect adapter_veto and next_latched.
 * Null required pointer returns1; available output defaults veto/true-latch.
 * Complete aligned input/output objects must not overlap. */
TC_API uint32_t tc_reconcile_pedal_latch(const tc_pedal_facts *facts, tc_pedal_result *result);

#endif
