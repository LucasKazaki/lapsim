/* Finite host-only memory/UB checks. No target code or hardware IO. */
#include "torque_guard.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <string.h>

static void zero(const tc_command_guard_result *r) {
    size_t i;
    assert(r->guard.status == TC_GUARD_INHIBITED);
    for (i = 0u; i < TC_WHEELS; ++i) {
        assert(r->guard.output[i].numeric == 1u && r->guard.output[i].value == 0.0 && !signbit(r->guard.output[i].value));
        assert(r->next.previous[i].numeric == 1u && r->next.previous[i].value == 0.0 && !signbit(r->next.previous[i].value));
    }
}

int main(void) {
    tc_allocation a;
    tc_command_guard_input in;
    tc_command_guard_config cfg;
    tc_command_guard_state previous;
    tc_command_guard_result result;
    size_t i;
    unsigned tag, field;
    memset(&a, 0, sizeof(a)); memset(&in, 0, sizeof(in)); memset(&cfg, 0, sizeof(cfg));
    tc_init_command_guard_state(&previous);
    a.type_valid = a.wheel_vector_valid = 1u; a.status = TC_ALLOCATION_OK;
    a.requested = (tc_scalar){40.0, 1u}; a.delivered = (tc_scalar){40.0, 1u};
    for (i = 0u; i < TC_WHEELS; ++i) a.wheels[i] = (tc_scalar){10.0, 1u};
    cfg.type_valid = 1u; cfg.max_rise = (tc_scalar){100.0, 1u};
    cfg.trip = (tc_scalar){0.6, 1u}; cfg.clear = (tc_scalar){0.2, 1u};
    in.type_valid = 1u; in.dt_s = (tc_scalar){0.05, 1u}; in.accelerator = (tc_scalar){0.3, 1u};
    in.comms = in.sensors = in.interlock = 1u;
    assert(tc_apply_command_guard(&a, &in, &cfg, &previous, &result) == 0u);
    assert(result.guard.status == TC_GUARD_LIMITED && result.guard.output[0].value == 5.0);
    for (field = 0u; field < 21u; ++field) {
        for (tag = 0u; tag < 256u; ++tag) {
            tc_allocation x = a;
            tc_command_guard_input y = in;
            tc_command_guard_config z = cfg;
            tc_command_guard_state s = previous;
            uint8_t *fields[] = {&x.type_valid, &x.wheel_vector_valid, &y.type_valid, &z.type_valid,
                &s.type_valid, &s.previous_vector_valid, &y.dt_s.numeric, &y.accelerator.numeric,
                &z.max_rise.numeric, &z.trip.numeric, &z.clear.numeric,
                &x.wheels[0].numeric, &x.wheels[1].numeric, &x.wheels[2].numeric, &x.wheels[3].numeric,
                &s.previous[0].numeric, &s.previous[1].numeric, &s.previous[2].numeric, &s.previous[3].numeric,
                &x.requested.numeric, &x.delivered.numeric};
            *fields[field] = (uint8_t)tag;
            assert(tc_apply_command_guard(&x, &y, &z, &s, &result) == 0u);
            if (tag != 1u) zero(&result);
        }
    }
    for (field = 0u; field < 5u; ++field) {
        for (tag = 2u; tag < 256u; ++tag) {
            tc_command_guard_input y = in;
            tc_command_guard_state s = previous;
            uint8_t *fields[] = {&y.brake, &y.comms, &y.sensors, &y.interlock, &s.previous_latched};
            *fields[field] = (uint8_t)tag;
            assert(tc_apply_command_guard(&a, &y, &cfg, &s, &result) == 0u);
            zero(&result);
            if (field == 4u) assert(result.next.previous_latched == 1u);
        }
    }
    for (field = 0u; field < 5u; ++field) {
        memset(&result, 255, sizeof(result));
        assert(tc_apply_command_guard(field == 0u ? NULL : &a, field == 1u ? NULL : &in,
            field == 2u ? NULL : &cfg, field == 3u ? NULL : &previous,
            field == 4u ? NULL : &result) == 1u);
        if (field != 4u) { zero(&result); assert(result.next.previous_latched == 1u); }
    }
    a.fault.kind = TC_TEXT_STRING; memset(a.fault.value, 'A', sizeof(a.fault.value));
    assert(tc_apply_command_guard(&a, &in, &cfg, &previous, &result) == 0u); zero(&result);
    memset(&a.fault, 0, sizeof(a.fault));
    a.requested.value = a.delivered.value = -0.0;
    for (i = 0u; i < TC_WHEELS; ++i) a.wheels[i].value = -0.0;
    assert(tc_apply_command_guard(&a, &in, &cfg, &previous, &result) == 0u);
    for (i = 0u; i < TC_WHEELS; ++i) assert(signbit(result.guard.output[i].value));
    a.wheels[0].value = a.requested.value = a.delivered.value = DBL_MAX;
    previous.previous[0].value = DBL_MAX * 0.75;
    cfg.max_rise.value = DBL_MAX * 0.75; in.dt_s.value = 1.0;
    assert(tc_apply_command_guard(&a, &in, &cfg, &previous, &result) == 0u);
    assert(result.guard.status == TC_GUARD_OK && result.guard.output[0].value == DBL_MAX);
    previous.previous[0].value = 0.0;
    a.wheels[0].value = a.requested.value = a.delivered.value = DBL_TRUE_MIN;
    cfg.max_rise.value = in.dt_s.value = DBL_TRUE_MIN;
    assert(tc_apply_command_guard(&a, &in, &cfg, &previous, &result) == 0u);
    assert(result.guard.status == TC_GUARD_OK && result.guard.output[0].value == 0.0 && result.guard.reason.kind == TC_TEXT_NONE);
    tc_init_command_guard_state(NULL);
    assert(tc_command_guard_abi_sizeof(999u) == 0u);
    return 0;
}
