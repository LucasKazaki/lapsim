#ifndef ENME408_TORQUE_CLOCK_H
#define ENME408_TORQUE_CLOCK_H

#include "torque_contract.h"

/* Separate additive clock ABI/semantic version. Existing torque ABI stays 1.
 * Values are normalized uint64 milliseconds, never a raw wrapping MCU timer. */
#define TC_CLOCK_CONTRACT_VERSION 1u
enum tc_clock_size_kind { TC_CLOCK_SIZE_STATE = 1, TC_CLOCK_SIZE_INPUT = 2,
    TC_CLOCK_SIZE_POLICY = 3, TC_CLOCK_SIZE_RESULT = 4 };

typedef struct { uint8_t previous_present; uint64_t previous_tick; } tc_clock_state;
typedef struct { uint64_t now_ms; uint8_t timestamp_valid; tc_scalar dt_s; } tc_clock_input;
typedef struct { uint32_t period_ms; } tc_clock_policy;
typedef struct {
    tc_clock_state next;
    uint8_t now_valid;
    uint64_t now_ms;
    tc_text fault;
} tc_clock_result;

TC_API uint32_t tc_clock_contract_version(void);
TC_API size_t tc_clock_abi_sizeof(uint32_t kind);
TC_API void tc_init_clock(tc_clock_state *state);
/* Aligned, complete, non-overlapping input/output objects are required.
 * Invalid/malformed timestamps do not advance the anchor. Forward gaps and
 * invalid dt DO advance a valid forward anchor. A restart never resets it.
 * timestamp_valid must be exactly 1; dt.numeric must be exactly 1 and finite.
 * Non-NULL result is initialized faulted before argument validation.
 * Return 1 on a NULL required pointer, 0 for a (possibly faulted) result. */
TC_API uint32_t tc_clock_step(const tc_clock_state *previous,
    const tc_clock_input *input, const tc_clock_policy *policy, tc_clock_result *result);
/* Compose the native clock before the existing gate. The caller's
 * cycle.clock_fault is replaced by the native clock result. The allocator and
 * guard results still belong to their external owners. Every pointer is
 * required and all input/output storage must be mutually non-overlapping.
 * Return 1 on a NULL pointer; available outputs are initialized faulted/zero.
 * No clock fault can result in an allowed or nonzero final command. */
TC_API uint32_t tc_clocked_decide(const tc_clock_state *previous_clock,
    const tc_clock_input *clock_input, const tc_clock_policy *clock_policy,
    const tc_snapshot *previous_gate, const tc_cycle *cycle, const tc_policy *gate_policy,
    tc_clock_result *clock_result, tc_decision *decision);

#endif
