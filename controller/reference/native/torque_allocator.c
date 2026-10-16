#include "torque_allocator.h"

#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(double) == 8, "binary64 double required");
_Static_assert(FLT_RADIX == 2 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "binary64 floating-point parameters required");
_Static_assert(FLT_EVAL_METHOD == 0, "binary64 evaluation without excess precision required");
#if defined(__FAST_MATH__)
#error "Fast-math is incompatible with allocator parity"
#endif
#if defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0
#error "Finite-math-only is incompatible with allocator parity"
#endif

static void set_fault(tc_allocation *result, const char *reason) {
    size_t index = 0u;
    result->status = TC_ALLOCATION_FAULT;
    result->fault.kind = TC_TEXT_STRING;
    memset(result->fault.value, 0, TC_TEXT_CAPACITY);
    while (index + 1u < TC_TEXT_CAPACITY && reason[index] != '\0') {
        result->fault.value[index] = reason[index];
        ++index;
    }
}

static void initialize(tc_allocation *result) {
    size_t index;
    memset(result, 0, sizeof(*result));
    result->type_valid = 1u;
    result->wheel_vector_valid = 1u;
    result->requested.numeric = 1u;
    result->delivered.numeric = 1u;
    for (index = 0u; index < TC_WHEELS; ++index) result->wheels[index].numeric = 1u;
    set_fault(result, "missing_allocator_input");
}

static int numeric(tc_scalar value) {
    return value.numeric == 1u && isfinite(value.value);
}

static uint32_t fault(tc_allocation *result, const tc_allocator_input *input,
                      const char *reason) {
    if (numeric(input->request)) result->requested.value = input->request.value;
    set_fault(result, reason);
    return 0u;
}

static int supported_unit(const tc_text *unit) {
    return unit->kind == TC_TEXT_STRING &&
        memchr(unit->value, '\0', TC_TEXT_CAPACITY) != NULL &&
        strcmp(unit->value, "N*m") == 0;
}

uint32_t tc_allocator_version(void) { return TC_ALLOCATOR_VERSION; }

size_t tc_allocator_abi_sizeof(uint32_t kind) {
    switch (kind) {
        case 1u: return sizeof(tc_allocator_config);
        case 2u: return sizeof(tc_allocator_input);
        default: return 0u;
    }
}

uint32_t tc_allocate_propulsive_torque(const tc_allocator_input *input,
    const tc_allocator_config *config, tc_allocation *result) {
    size_t index;
    unsigned active_count = 0u;
    uint8_t active[TC_WHEELS] = {0u, 0u, 0u, 0u};
    double remaining, share, capacity, threshold, total;
    const double epsilon = 1e-12;
    if (result == NULL) return 1u;
    initialize(result);
    if (input == NULL || config == NULL) return 1u;
    if (config->type_valid != 1u) {
        set_fault(result, "invalid_allocator_config_type");
        return 0u;
    }
    if (input->type_valid != 1u) {
        set_fault(result, "invalid_allocator_input_type");
        return 0u;
    }
    if (config->max_input_age_valid != 1u)
        return fault(result, input, "invalid_max_input_age");
    if (!supported_unit(&input->torque_unit))
        return fault(result, input, "unsupported_torque_unit");
    if (input->request.numeric != 1u)
        return fault(result, input, "invalid_request_numeric");
    if (!isfinite(input->request.value))
        return fault(result, input, "nonfinite_request");
    if (input->request.value < 0.0)
        return fault(result, input, "negative_request_unsupported");
    if (input->limits_vector_valid != 1u || input->enabled_vector_valid != 1u)
        return fault(result, input, "invalid_wheel_vector");
    for (index = 0u; index < TC_WHEELS; ++index)
        if (input->enabled[index] > 1u)
            return fault(result, input, "invalid_wheel_enabled");
    if (input->external_interlock > 1u)
        return fault(result, input, "invalid_external_interlock");
    for (index = 0u; index < TC_WHEELS; ++index)
        if (!numeric(input->limits[index]) || input->limits[index].value < 0.0)
            return fault(result, input, "invalid_wheel_limit");
    if (input->external_interlock == 0u)
        return fault(result, input, "external_interlock_open");
    if (input->now_valid != 1u || input->timestamp_valid != 1u)
        return fault(result, input, "invalid_input_timestamp");
    if (input->input_timestamp_ms > input->now_ms)
        return fault(result, input, "input_timestamp_in_future");
    if (input->now_ms - input->input_timestamp_ms > config->max_input_age_ms)
        return fault(result, input, "stale_input");
    result->status = TC_ALLOCATION_OK;
    result->fault.kind = TC_TEXT_NONE;
    memset(result->fault.value, 0, TC_TEXT_CAPACITY);
    if (input->request.value == 0.0) return 0u;
    for (index = 0u; index < TC_WHEELS; ++index) {
        if (input->enabled[index] != 0u && input->limits[index].value > 0.0) {
            active[index] = 1u;
            ++active_count;
        }
    }
    if (active_count == 0u) return fault(result, input, "no_available_wheels");
    remaining = input->request.value;
    while (active_count != 0u && remaining > epsilon) {
        uint8_t saturated[TC_WHEELS] = {0u, 0u, 0u, 0u};
        unsigned saturated_count = 0u;
        share = remaining / (double)active_count;
        for (index = 0u; index < TC_WHEELS; ++index) {
            if (active[index] != 0u) {
                capacity = input->limits[index].value - result->wheels[index].value;
                threshold = share + epsilon;
                if (capacity <= threshold) {
                    saturated[index] = 1u;
                    ++saturated_count;
                }
            }
        }
        if (saturated_count == 0u) {
            for (index = 0u; index < TC_WHEELS; ++index)
                if (active[index] != 0u)
                    result->wheels[index].value = result->wheels[index].value + share;
            remaining = 0.0;
            break;
        }
        for (index = 0u; index < TC_WHEELS; ++index) {
            if (saturated[index] != 0u) {
                capacity = input->limits[index].value - result->wheels[index].value;
                if (!(capacity > 0.0)) capacity = 0.0;
                result->wheels[index].value = result->wheels[index].value + capacity;
                remaining = remaining - capacity;
                active[index] = 0u;
                --active_count;
            }
        }
    }
    total = 0.0;
    for (index = 0u; index < TC_WHEELS; ++index)
        total = total + result->wheels[index].value;
    result->requested.value = input->request.value;
    result->delivered.value = total;
    if (remaining > 1e-9) {
        set_fault(result, "aggregate_limit");
        result->status = TC_ALLOCATION_SATURATED;
    }
    return 0u;
}
