#include "torque_clock.h"

#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(double) == 8 && FLT_RADIX == 2 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "binary64 floating-point required for clock tolerance");
#if defined(__FAST_MATH__)
#error "Fast-math is incompatible with the clock contract"
#endif
#if defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0
#error "Finite-math-only is incompatible with the clock contract"
#endif

static void fault(tc_clock_result *result, const char *reason) {
    size_t index = 0u;
    result->fault.kind = TC_TEXT_STRING;
    while (index + 1u < TC_TEXT_CAPACITY && reason[index] != '\0') {
        result->fault.value[index] = reason[index];
        ++index;
    }
    result->fault.value[index] = '\0';
}

uint32_t tc_clock_contract_version(void) { return TC_CLOCK_CONTRACT_VERSION; }

size_t tc_clock_abi_sizeof(uint32_t kind) {
    switch (kind) {
        case TC_CLOCK_SIZE_STATE: return sizeof(tc_clock_state);
        case TC_CLOCK_SIZE_INPUT: return sizeof(tc_clock_input);
        case TC_CLOCK_SIZE_POLICY: return sizeof(tc_clock_policy);
        case TC_CLOCK_SIZE_RESULT: return sizeof(tc_clock_result);
        default: return 0u;
    }
}

void tc_init_clock(tc_clock_state *state) {
    if (state != NULL) memset(state, 0, sizeof(*state));
}

uint32_t tc_clock_step(const tc_clock_state *previous,
    const tc_clock_input *input, const tc_clock_policy *policy, tc_clock_result *result) {
    double expected_dt;
    if (result == NULL) return 1u;
    memset(result, 0, sizeof(*result));
    fault(result, "invalid_argument");
    if (previous == NULL || input == NULL || policy == NULL) return 1u;
    if (previous->previous_present > 1u) {
        fault(result, "invalid_clock_state"); return 0u;
    }
    if (policy->period_ms == 0u || policy->period_ms > 60000u) {
        fault(result, "invalid_clock_policy"); return 0u;
    }
    result->next = *previous;
    memset(&result->fault, 0, sizeof(result->fault));
    if (input->timestamp_valid != 1u) {
        fault(result, "invalid_cycle_timestamp");
    } else {
        result->now_valid = 1u;
        result->now_ms = input->now_ms;
        if (previous->previous_present == 1u && input->now_ms <= previous->previous_tick) {
            fault(result, "nonmonotonic_cycle_timestamp");
        } else {
            /* Subtraction is safe only in this strictly-forward branch. It
             * does not wrap at UINT64_MAX and never converts ticks to double. */
            if (previous->previous_present == 1u &&
                input->now_ms - previous->previous_tick != policy->period_ms)
                fault(result, "cycle_period_mismatch");
            result->next.previous_present = 1u;
            result->next.previous_tick = input->now_ms;
        }
    }
    expected_dt = (double)policy->period_ms / 1000.0;
    if ((input->dt_s.numeric != 1u || !isfinite(input->dt_s.value) ||
         fabs(input->dt_s.value - expected_dt) > 1e-12) && result->fault.kind == TC_TEXT_NONE)
        fault(result, "guard_period_mismatch");
    return 0u;
}

uint32_t tc_clocked_decide(const tc_clock_state *previous_clock,
    const tc_clock_input *clock_input, const tc_clock_policy *clock_policy,
    const tc_snapshot *previous_gate, const tc_cycle *cycle, const tc_policy *gate_policy,
    tc_clock_result *clock_result, tc_decision *decision) {
    tc_cycle checked_cycle;
    /* Initialize both available outputs, including all partial-NULL cases. */
    (void)tc_clock_step(NULL, NULL, NULL, clock_result);
    (void)tc_decide(NULL, NULL, NULL, decision);
    if (previous_clock == NULL || clock_input == NULL || clock_policy == NULL ||
        previous_gate == NULL || cycle == NULL || gate_policy == NULL ||
        clock_result == NULL || decision == NULL) return 1u;
    (void)tc_clock_step(previous_clock, clock_input, clock_policy, clock_result);
    checked_cycle = *cycle;
    checked_cycle.clock_fault = clock_result->fault;
    return tc_decide(previous_gate, &checked_cycle, gate_policy, decision);
}
