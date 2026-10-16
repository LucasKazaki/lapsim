#include "torque_contract.h"

#include <float.h>
#include <math.h>
#include <string.h>

/* Parity is defined for binary64 under ordinary IEEE rounding, without
 * fast-math/reassociation. Reject an incompatible build rather than silently
 * claiming agreement with Python's float contract. */
_Static_assert(sizeof(double) == 8, "binary64 double required");
_Static_assert(FLT_RADIX == 2 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "binary64 floating-point parameters required");
#if defined(__FAST_MATH__)
#error "Fast-math is incompatible with the validation contract"
#endif
#if defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0
#error "Finite-math-only is incompatible with the validation contract"
#endif

static int numeric(tc_scalar value) {
    return value.numeric == 1u && isfinite(value.value);
}

static int text_valid(const tc_text *value) {
    return value->kind == TC_TEXT_NONE ||
        (value->kind == TC_TEXT_STRING &&
         memchr(value->value, '\0', TC_TEXT_CAPACITY) != NULL);
}

static int text_nonempty(const tc_text *value) {
    return value->kind == TC_TEXT_STRING && text_valid(value) && value->value[0] != '\0';
}

static void reason_copy(char destination[TC_TEXT_CAPACITY], const char *source) {
    size_t index = 0u;
    while (index + 1u < TC_TEXT_CAPACITY && source[index] != '\0') {
        destination[index] = source[index];
        ++index;
    }
    destination[index] = '\0';
}

static double ulp(double value) {
    int exponent;
    double magnitude = fabs(value);
    if (magnitude < DBL_MIN) return DBL_TRUE_MIN;
    (void)frexp(magnitude, &exponent);
    /* Unlike nextafter(DBL_MAX, INFINITY)-DBL_MAX, this remains finite at
     * DBL_MAX and matches math.ulp, including subnormal values. */
    return ldexp(1.0, exponent - DBL_MANT_DIG);
}

static double wheel_total(const double values[TC_WHEELS]) {
    size_t index;
    double total = 0.0;
    for (index = 0u; index < TC_WHEELS; ++index) total = total + values[index];
    return total;
}

uint32_t tc_abi_version(void) { return TC_ABI_VERSION; }
uint32_t tc_numeric_contract_version(void) { return TC_NUMERIC_CONTRACT_VERSION; }

size_t tc_abi_sizeof(uint32_t kind) {
    switch (kind) {
        case TC_SIZE_SCALAR: return sizeof(tc_scalar);
        case TC_SIZE_TEXT: return sizeof(tc_text);
        case TC_SIZE_ALLOCATION: return sizeof(tc_allocation);
        case TC_SIZE_GUARD: return sizeof(tc_guard);
        case TC_SIZE_SNAPSHOT: return sizeof(tc_snapshot);
        case TC_SIZE_POLICY: return sizeof(tc_policy);
        case TC_SIZE_CYCLE: return sizeof(tc_cycle);
        case TC_SIZE_DECISION: return sizeof(tc_decision);
        default: return 0u;
    }
}

void tc_init_snapshot(tc_snapshot *snapshot) {
    if (snapshot != NULL) {
        memset(snapshot, 0, sizeof(*snapshot));
        snapshot->state = TC_INHIBITED;
    }
}

uint32_t tc_validate_allocation(const tc_allocation *candidate) {
    size_t index;
    double values[TC_WHEELS];
    double total;
    double requested, delivered, roundoff, commanded;
    if (candidate == NULL || candidate->type_valid != 1u)
        return TC_INVALID_CANDIDATE_TYPE;
    if (candidate->status < TC_ALLOCATION_OK || candidate->status > TC_ALLOCATION_FAULT)
        return TC_INVALID_CANDIDATE_STATUS;
    if (candidate->wheel_vector_valid != 1u) return TC_INVALID_CANDIDATE_OUTPUT;
    for (index = 0u; index < TC_WHEELS; ++index) {
        if (!numeric(candidate->wheels[index]) || candidate->wheels[index].value < 0.0)
            return TC_INVALID_CANDIDATE_OUTPUT;
        values[index] = candidate->wheels[index].value;
    }
    if (!numeric(candidate->delivered) || candidate->delivered.value < 0.0)
        return TC_INVALID_CANDIDATE_DELIVERED;
    delivered = candidate->delivered.value;
    total = wheel_total(values);
    if (!isfinite(total) || fabs(total - delivered) > 8.0 * fmax(ulp(total), ulp(delivered)))
        return TC_CANDIDATE_SUM_MISMATCH;
    if (!numeric(candidate->requested) ||
        (candidate->status != TC_ALLOCATION_FAULT && candidate->requested.value < 0.0))
        return TC_INVALID_CANDIDATE_REQUESTED;
    requested = candidate->requested.value;
    if (!text_valid(&candidate->fault)) return TC_INVALID_CANDIDATE_FAULT;
    if (candidate->status == TC_ALLOCATION_OK && candidate->fault.kind != TC_TEXT_NONE)
        return TC_CANDIDATE_STATUS_FAULT_MISMATCH;
    if (candidate->status == TC_ALLOCATION_SATURATED &&
        (candidate->fault.kind != TC_TEXT_STRING || strcmp(candidate->fault.value, "aggregate_limit") != 0))
        return TC_CANDIDATE_STATUS_FAULT_MISMATCH;
    if (candidate->status == TC_ALLOCATION_FAULT) {
        if (!text_nonempty(&candidate->fault) || delivered != 0.0)
            return TC_CANDIDATE_STATUS_FAULT_MISMATCH;
        for (index = 0u; index < TC_WHEELS; ++index)
            if (candidate->wheels[index].value != 0.0) return TC_CANDIDATE_STATUS_FAULT_MISMATCH;
    } else {
        commanded = fmax(total, delivered);
        roundoff = 8.0 * fmax(ulp(requested), ulp(commanded));
        if ((requested == 0.0 && commanded != 0.0) || commanded - requested > roundoff)
            return TC_CANDIDATE_EXCEEDS_REQUEST;
    }
    return TC_CONTRACT_OK;
}

const char *tc_contract_reason(uint32_t code) {
    switch (code) {
        case TC_CONTRACT_OK: return "";
        case TC_INVALID_CANDIDATE_TYPE: return "invalid_candidate_type";
        case TC_INVALID_CANDIDATE_STATUS: return "invalid_candidate_status";
        case TC_INVALID_CANDIDATE_OUTPUT: return "invalid_candidate_output";
        case TC_INVALID_CANDIDATE_DELIVERED: return "invalid_candidate_delivered";
        case TC_CANDIDATE_SUM_MISMATCH: return "candidate_sum_mismatch";
        case TC_INVALID_CANDIDATE_REQUESTED: return "invalid_candidate_requested";
        case TC_INVALID_CANDIDATE_FAULT: return "invalid_candidate_fault";
        case TC_CANDIDATE_STATUS_FAULT_MISMATCH: return "candidate_status_fault_mismatch";
        case TC_CANDIDATE_EXCEEDS_REQUEST: return "candidate_exceeds_request";
        default: return "unknown_contract_code";
    }
}

static int guard_valid(const tc_guard *guard, const tc_allocation *candidate) {
    size_t index;
    double values[TC_WHEELS];
    if (guard->status < TC_GUARD_OK || guard->status > TC_GUARD_INHIBITED ||
        guard->output_valid != 1u || !text_valid(&guard->reason)) return 0;
    if (guard->status == TC_GUARD_INHIBITED && !text_nonempty(&guard->reason)) return 0;
    for (index = 0u; index < TC_WHEELS; ++index) {
        if (!numeric(guard->output[index]) || guard->output[index].value < 0.0 ||
            guard->output[index].value > candidate->wheels[index].value ||
            (guard->status == TC_GUARD_INHIBITED && guard->output[index].value != 0.0)) return 0;
        values[index] = guard->output[index].value;
    }
    return isfinite(wheel_total(values));
}

static void inhibit(tc_decision *output, const char *reason) {
    output->next.state = TC_INHIBITED;
    output->next.recovery_streak = 0u;
    output->command_allowed = 0u;
    memset(output->command, 0, sizeof(output->command));
    reason_copy(output->reason, reason);
}

uint32_t tc_decide(const tc_snapshot *previous, const tc_cycle *cycle,
                    const tc_policy *policy, tc_decision *output) {
    uint8_t prior_state;
    size_t index;
    if (output == NULL) return 1u;
    memset(output, 0, sizeof(*output));
    inhibit(output, "invalid_argument");
    if (previous == NULL || cycle == NULL || policy == NULL) return 1u;
    output->next.generation = previous->generation;
    if (previous->state < TC_READY || previous->state > TC_RECOVERY_PENDING) {
        inhibit(output, "invalid_snapshot_state"); return 0u;
    }
    if (policy->valid_samples_to_recover == 0u) {
        inhibit(output, "invalid_recovery_policy"); return 0u;
    }
    if (cycle->restart_requested > 1u || !text_valid(&cycle->clock_fault) ||
        (cycle->clock_fault.kind == TC_TEXT_STRING && !text_nonempty(&cycle->clock_fault))) {
        inhibit(output, "invalid_cycle_flags"); return 0u;
    }
    if (cycle->restart_requested == 1u && previous->generation == UINT32_MAX) {
        inhibit(output, "counter_overflow"); return 0u;
    }
    output->next.generation += cycle->restart_requested;
    prior_state = cycle->restart_requested == 1u ? TC_INHIBITED : previous->state;
    output->next.recovery_streak = cycle->restart_requested == 1u ? 0u : previous->recovery_streak;
    output->contract_code = tc_validate_allocation(&cycle->allocation);
    if (output->contract_code != TC_CONTRACT_OK) {
        inhibit(output, "invalid_allocator_result"); return 0u;
    }
    if (!guard_valid(&cycle->guard, &cycle->allocation)) {
        inhibit(output, "invalid_guard_result"); return 0u;
    }
    if (cycle->clock_fault.kind == TC_TEXT_STRING) {
        inhibit(output, cycle->clock_fault.value); return 0u;
    }
    if (cycle->allocation.status == TC_ALLOCATION_FAULT) {
        inhibit(output, cycle->allocation.fault.value); return 0u;
    }
    if (cycle->guard.status == TC_GUARD_INHIBITED) {
        inhibit(output, cycle->guard.reason.value); return 0u;
    }
    if (prior_state == TC_INHIBITED || prior_state == TC_RECOVERY_PENDING) {
        output->next.state = TC_RECOVERY_PENDING;
        if (cycle->allocation.status == TC_ALLOCATION_SATURATED) {
            output->next.recovery_streak = 0u;
            reason_copy(output->reason, "recovery_waiting_for_unsaturated_valid_sample");
            return 0u;
        }
        if (output->next.recovery_streak == UINT32_MAX) {
            inhibit(output, "counter_overflow"); return 0u;
        }
        ++output->next.recovery_streak;
        if (output->next.recovery_streak < policy->valid_samples_to_recover) {
            reason_copy(output->reason, "recovery_valid_sample"); return 0u;
        }
        output->next.state = TC_READY;
        reason_copy(output->reason, "recovery_criteria_met");
    } else {
        output->next.recovery_streak = 0u;
        output->next.state = cycle->allocation.status == TC_ALLOCATION_SATURATED ? TC_LIMITED : TC_READY;
        reason_copy(output->reason, cycle->allocation.status == TC_ALLOCATION_SATURATED ? "aggregate_limit" : "allocator_ok");
    }
    output->command_allowed = 1u;
    for (index = 0u; index < TC_WHEELS; ++index)
        output->command[index] = cycle->guard.output[index].value;
    return 0u;
}
