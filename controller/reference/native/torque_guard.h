#ifndef ENME408_TORQUE_GUARD_H
#define ENME408_TORQUE_GUARD_H

#include "torque_contract.h"

/* Offline base-guard owner, not a motor interface. Four synthetic slots have
 * no confirmed physical mapping. Proposed vectors must pass the existing
 * pedal/clock/recovery/final gate before an offline command is reported.
 * Ordinary binary64 round-to-nearest with retained subnormals is assumed. */
#define TC_COMMAND_GUARD_VERSION 1u

typedef struct {
    uint8_t type_valid;
    tc_scalar max_rise, trip, clear;
} tc_command_guard_config;

typedef struct {
    uint8_t type_valid;
    tc_scalar dt_s, accelerator;
    uint8_t brake, comms, sensors, interlock;
} tc_command_guard_input;

typedef struct {
    uint8_t type_valid, previous_vector_valid, previous_latched;
    tc_scalar previous[TC_WHEELS];
} tc_command_guard_state;

typedef struct {
    tc_guard guard;
    tc_command_guard_state next;
    uint32_t contract_code;
} tc_command_guard_result;

TC_API uint32_t tc_command_guard_version(void);
/* kind1=config, 2=input, 3=state, 4=result; otherwise0. */
TC_API size_t tc_command_guard_abi_sizeof(uint32_t kind);
TC_API void tc_init_command_guard_state(tc_command_guard_state *state);
/* Exactly1 means an ordinary decoded record/numeric/vector type. Boolean
 * bytes must be0/1. Required NULL returns1; available output is initialized
 * inhibited/positive-zero with a conservative true latch. Other calls return0
 * even when inhibited. C-only outer schema failures have explicit diagnostics;
 * they do not claim Python result parity for objects Python cannot inspect.
 * Complete aligned input/output objects must be mutually non-overlapping.
 * No heap, transport, scheduler, allocator, target or shutdown authority. */
TC_API uint32_t tc_apply_command_guard(const tc_allocation *candidate,
    const tc_command_guard_input *input, const tc_command_guard_config *config,
    const tc_command_guard_state *previous, tc_command_guard_result *result);

#endif
