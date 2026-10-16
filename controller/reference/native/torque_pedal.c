#include "torque_pedal.h"

#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(double) == 8 && FLT_RADIX == 2 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "binary64 required for pedal thresholds");
#if defined(__FAST_MATH__)
#error "Fast-math is incompatible with the pedal contract"
#endif
#if defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0
#error "Finite-math-only is incompatible with the pedal contract"
#endif

static int ordinary(tc_scalar value) { return value.numeric == 1u && isfinite(value.value); }

static void reason_set(tc_text *destination, const char *value) {
    size_t index = 0u;
    memset(destination, 0, sizeof(*destination));
    destination->kind = TC_TEXT_STRING;
    while (index + 1u < TC_TEXT_CAPACITY && value[index] != '\0') {
        destination->value[index] = value[index];
        ++index;
    }
}

static int reason_valid(const tc_text *value) {
    return value->kind == TC_TEXT_NONE || (value->kind == TC_TEXT_STRING &&
           memchr(value->value, '\0', TC_TEXT_CAPACITY) != NULL);
}

static void fallback(tc_text *value, const char *reason) {
    if (value->kind == TC_TEXT_NONE || value->value[0] == '\0') reason_set(value, reason);
}

uint32_t tc_pedal_adapter_version(void) { return TC_PEDAL_ADAPTER_VERSION; }
size_t tc_pedal_abi_sizeof(uint32_t kind) {
    if (kind == 1u) return sizeof(tc_pedal_facts);
    if (kind == 2u) return sizeof(tc_pedal_result);
    return 0u;
}

uint8_t tc_trusted_overlap_trip(const tc_pedal_facts *facts) {
    if (facts == NULL || facts->input_type_valid != 1u || facts->config_type_valid != 1u ||
        facts->state_type_valid != 1u || facts->previous_latched > 1u ||
        facts->brake != 1u || facts->comms != 1u || facts->sensors != 1u ||
        !ordinary(facts->accelerator) || !ordinary(facts->rise) ||
        !ordinary(facts->trip) || !ordinary(facts->clear)) return 0u;
    return (uint8_t)(facts->rise.value > 0.0 && facts->clear.value >= 0.0 &&
        facts->clear.value < facts->trip.value && facts->trip.value <= 1.0 &&
        facts->accelerator.value >= 0.0 && facts->accelerator.value <= 1.0 &&
        facts->accelerator.value >= facts->trip.value);
}

uint8_t tc_trusted_clear_cycle(const tc_pedal_facts *facts) {
    return (uint8_t)(facts != NULL && facts->candidate_type_valid == 1u &&
        (facts->candidate_status == TC_ALLOCATION_OK || facts->candidate_status == TC_ALLOCATION_SATURATED) &&
        facts->input_type_valid == 1u && facts->comms == 1u && facts->sensors == 1u && facts->interlock == 1u &&
        facts->result_type_valid == 1u && (facts->guard_status == TC_GUARD_OK || facts->guard_status == TC_GUARD_LIMITED));
}

uint32_t tc_reconcile_pedal_latch(const tc_pedal_facts *facts, tc_pedal_result *result) {
    uint8_t latched;
    if (result == NULL) return 1u;
    memset(result, 0, sizeof(*result));
    result->adapter_veto = result->next_latched = 1u;
    reason_set(&result->reason, "invalid_argument");
    if (facts == NULL) return 1u;
    result->trip_observed = tc_trusted_overlap_trip(facts);
    result->clear_cycle_trusted = tc_trusted_clear_cycle(facts);
    if (facts->previous_latched > 1u) {
        reason_set(&result->reason, "invalid_pedal_latch_state"); return 0u;
    }
    if (facts->base_next_latched > 1u) {
        reason_set(&result->reason, "invalid_pedal_result_latch"); return 0u;
    }
    if (facts->clock_fault_present > 1u) {
        reason_set(&result->reason, "invalid_pedal_clock_flag"); return 0u;
    }
    if (facts->input_type_valid != 1u || facts->config_type_valid != 1u ||
        facts->state_type_valid != 1u || facts->result_type_valid != 1u ||
        facts->guard_status < TC_GUARD_OK || facts->guard_status > TC_GUARD_INHIBITED ||
        !reason_valid(&facts->base_reason)) {
        reason_set(&result->reason, "invalid_pedal_adapter_metadata"); return 0u;
    }
    result->adapter_veto = 0u;
    result->reason = facts->base_reason;
    latched = facts->base_next_latched;
    if (result->trip_observed == 1u && latched != 1u) {
        latched = 1u;
        result->adapter_veto = 1u;
        fallback(&result->reason, "brake_accelerator_overlap");
    }
    if (facts->previous_latched == 1u && latched == 0u && result->clear_cycle_trusted == 0u) {
        latched = 1u;
        result->adapter_veto = 1u;
        fallback(&result->reason, "untrusted_overlap_latch_clear");
    }
    result->next_latched = (uint8_t)(latched == 1u ||
        (facts->clock_fault_present == 1u && facts->previous_latched == 1u));
    return 0u;
}
