#include "torque_guard.h"

#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(double) == 8 && FLT_RADIX == 2 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "binary64 required for command guard");
#if defined(__FAST_MATH__)
#error "Fast-math is incompatible with the command guard"
#endif
#if defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0
#error "Finite-only math is incompatible with the command guard"
#endif

static int ordinary(tc_scalar value) { return value.numeric == 1u && isfinite(value.value); }

static void set_reason(tc_text *destination, const char *source) {
    size_t index = 0u;
    memset(destination, 0, sizeof(*destination));
    destination->kind = TC_TEXT_STRING;
    while (index + 1u < TC_TEXT_CAPACITY && source[index] != '\0') {
        destination->value[index] = source[index];
        ++index;
    }
}

void tc_init_command_guard_state(tc_command_guard_state *state) {
    size_t index;
    if (state == NULL) return;
    memset(state, 0, sizeof(*state));
    state->type_valid = state->previous_vector_valid = 1u;
    for (index = 0u; index < TC_WHEELS; ++index) state->previous[index].numeric = 1u;
}

static void initialize(tc_command_guard_result *result) {
    size_t index;
    memset(result, 0, sizeof(*result));
    tc_init_command_guard_state(&result->next);
    result->next.previous_latched = 1u;
    result->guard.status = TC_GUARD_INHIBITED;
    result->guard.output_valid = 1u;
    for (index = 0u; index < TC_WHEELS; ++index) result->guard.output[index].numeric = 1u;
    set_reason(&result->guard.reason, "invalid_argument");
}

static void inhibit(tc_command_guard_result *result, uint8_t latch, const char *reason) {
    result->next.previous_latched = latch;
    set_reason(&result->guard.reason, reason);
}

uint32_t tc_command_guard_version(void) { return TC_COMMAND_GUARD_VERSION; }
size_t tc_command_guard_abi_sizeof(uint32_t kind) {
    switch (kind) {
        case 1u: return sizeof(tc_command_guard_config);
        case 2u: return sizeof(tc_command_guard_input);
        case 3u: return sizeof(tc_command_guard_state);
        case 4u: return sizeof(tc_command_guard_result);
        default: return 0u;
    }
}

uint32_t tc_apply_command_guard(const tc_allocation *candidate,
    const tc_command_guard_input *input, const tc_command_guard_config *config,
    const tc_command_guard_state *previous, tc_command_guard_result *result) {
    size_t index;
    uint8_t latched;
    int rate_limited = 0;
    double max_step;
    if (result == NULL) return 1u;
    initialize(result);
    if (candidate == NULL || input == NULL || config == NULL || previous == NULL) return 1u;
    if (previous->type_valid != 1u) {
        inhibit(result, 1u, "invalid_guard_state_type"); return 0u;
    }
    if (previous->previous_latched > 1u) {
        inhibit(result, 1u, "invalid_pedal_latch_state"); return 0u;
    }
    latched = previous->previous_latched;
    if (config->type_valid != 1u) {
        inhibit(result, latched, "invalid_guard_config_type"); return 0u;
    }
    if (!ordinary(config->max_rise) || config->max_rise.value <= 0.0) {
        inhibit(result, latched, "invalid_max_rise_rate"); return 0u;
    }
    if (!ordinary(config->trip) || !ordinary(config->clear) ||
        !(config->clear.value >= 0.0 && config->clear.value < config->trip.value && config->trip.value <= 1.0)) {
        inhibit(result, latched, "invalid_pedal_threshold"); return 0u;
    }
    if (previous->previous_vector_valid != 1u) {
        inhibit(result, latched, "invalid_previous_output"); return 0u;
    }
    for (index = 0u; index < TC_WHEELS; ++index) {
        if (!ordinary(previous->previous[index]) || previous->previous[index].value < 0.0) {
            inhibit(result, latched, "invalid_previous_output"); return 0u;
        }
    }
    if (input->type_valid != 1u) {
        inhibit(result, latched, "invalid_guard_input_type"); return 0u;
    }
    if (!ordinary(input->dt_s) || input->dt_s.value <= 0.0) {
        inhibit(result, latched, "invalid_dt"); return 0u;
    }
    if (!ordinary(input->accelerator) || input->accelerator.value < 0.0 || input->accelerator.value > 1.0) {
        inhibit(result, latched, "invalid_accelerator_fraction"); return 0u;
    }
    if (input->brake > 1u || input->comms > 1u || input->sensors > 1u || input->interlock > 1u) {
        inhibit(result, latched, "invalid_boolean_input"); return 0u;
    }
    result->contract_code = tc_validate_allocation(candidate);
    if (result->contract_code != TC_CONTRACT_OK) {
        inhibit(result, latched, tc_contract_reason(result->contract_code)); return 0u;
    }
    if (latched == 1u) {
        if (input->accelerator.value <= config->clear.value) latched = 0u;
    } else if (input->brake == 1u && input->accelerator.value >= config->trip.value) latched = 1u;
    if (candidate->status == TC_ALLOCATION_FAULT) {
        inhibit(result, latched, "allocator_fault"); return 0u;
    }
    if (input->interlock == 0u) {
        inhibit(result, latched, "external_interlock_open"); return 0u;
    }
    if (input->comms == 0u) {
        inhibit(result, latched, "critical_communication_loss"); return 0u;
    }
    if (input->sensors == 0u) {
        inhibit(result, latched, "sensor_disagreement"); return 0u;
    }
    if (latched == 1u) {
        inhibit(result, latched, "brake_accelerator_overlap"); return 0u;
    }
    max_step = config->max_rise.value * input->dt_s.value;
    if (!isfinite(max_step)) {
        inhibit(result, latched, "invalid_rise_step"); return 0u;
    }
    for (index = 0u; index < TC_WHEELS; ++index) {
        double prior = previous->previous[index].value;
        double target = candidate->wheels[index].value;
        double command = target;
        if (target > prior) {
            double ceiling = prior + max_step;
            /* Preserve finite-product/addition-overflow behavior: a finite
             * target wins against +Inf. Tiny label differences remain exactly
             * the Python source's existing 1e-12 diagnostic comparison. */
            command = target <= ceiling ? target : ceiling;
            rate_limited = rate_limited || command < target - 1e-12;
        }
        result->guard.output[index].value = command;
        result->next.previous[index].value = command;
    }
    result->next.previous_latched = latched;
    result->guard.status = candidate->status == TC_ALLOCATION_SATURATED || rate_limited ? TC_GUARD_LIMITED : TC_GUARD_OK;
    memset(&result->guard.reason, 0, sizeof(result->guard.reason));
    if (rate_limited && candidate->status == TC_ALLOCATION_SATURATED)
        set_reason(&result->guard.reason, "aggregate_and_rise_rate_limit");
    else if (candidate->status == TC_ALLOCATION_SATURATED) set_reason(&result->guard.reason, "aggregate_limit");
    else if (rate_limited) set_reason(&result->guard.reason, "rise_rate_limit");
    return 0u;
}
