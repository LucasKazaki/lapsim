#ifndef ENME408_TORQUE_ALLOCATOR_H
#define ENME408_TORQUE_ALLOCATOR_H

#include "torque_contract.h"

/* Normalized offline candidate producer; four abstract slots, not motors.
 * Positive candidates must pass the existing guard/pedal/clock/final gate.
 * Binary64 nearest rounding with retained subnormals is assumed. */
#define TC_ALLOCATOR_VERSION 1u

typedef struct {
    uint8_t type_valid, max_input_age_valid;
    uint64_t max_input_age_ms;
} tc_allocator_config;

typedef struct {
    uint8_t type_valid, now_valid, timestamp_valid;
    uint64_t now_ms, input_timestamp_ms;
    tc_scalar request;
    uint8_t limits_vector_valid, enabled_vector_valid;
    tc_scalar limits[TC_WHEELS];
    uint8_t enabled[TC_WHEELS], external_interlock;
    tc_text torque_unit;
} tc_allocator_input;

TC_API uint32_t tc_allocator_version(void);
/* kind 1=config, 2=input; otherwise 0. Existing ABI/numeric versions unchanged. */
TC_API size_t tc_allocator_abi_sizeof(uint32_t kind);
/* Exactly 1 denotes ordinary decoded record/numeric/vector/time metadata.
 * Boolean bytes must be 0/1. Numeric-tagged NaN/Inf request is distinguished
 * from malformed numeric source. No-wrap uint64 ticks only; no wire format.
 * tc_text's first bounded NUL defines its raw C string. Source decoders MUST
 * reject embedded-NUL Python strings, never truncate them to a valid unit.
 * Required NULL returns 1; an available output is faulted/positive-zero first.
 * Semantic results return 0. C-only outer schema errors have separate reasons.
 * Complete aligned input/output objects must not overlap. No heap/state/IO,
 * scheduling, target, physical mapping or independent shutdown authority. */
TC_API uint32_t tc_allocate_propulsive_torque(const tc_allocator_input *input,
    const tc_allocator_config *config, tc_allocation *result);

#endif
