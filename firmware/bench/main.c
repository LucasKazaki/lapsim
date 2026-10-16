/* Generic QEMU F405 data-only bench. No physical actuator transport. */
#include <stdint.h>
#include <string.h>
#include "torque_allocator.h"
#include "torque_guard.h"
#include "torque_clock.h"
#include "torque_pedal.h"
#include "build_id.h"

#define REG(x) (*(volatile uint32_t *)(x))
#define MAX_FRAME 512u
#define HEADER 20u
static uint8_t input[MAX_FRAME], output[MAX_FRAME];
static uint64_t session, last_session;
static uint32_t next_sequence;
static tc_snapshot gate_state;
static tc_clock_state clock_state;
static tc_command_guard_state guard_state;
static uint8_t transport_bad;

static void uart_put(uint8_t c) {
    while (!(REG(0x40011000u) & 0x80u)) {}
    REG(0x40011004u) = c;
}
static uint8_t uart_character(void) {
    uint8_t c;
    while (!(REG(0x40011000u) & 0x20u)) {}
    c = (uint8_t)REG(0x40011004u);
    uart_put(c); /* Explicit byte credit for the emulator host adapter. */
    return c;
}
static uint8_t nibble(uint8_t c) {
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10u;
    transport_bad=1u;return 0;
}
static uint8_t uart_get(void) {
    uint8_t high=nibble(uart_character());
    return (uint8_t)((high<<4)|nibble(uart_character()));
}
static void uart_byte(uint8_t c) {
    const char *hex="0123456789abcdef";
    uart_put((uint8_t)hex[c>>4]);uart_put((uint8_t)hex[c&15u]);
}
static uint64_t get_uint(const uint8_t *p, unsigned count) {
    uint64_t v = 0; unsigned i;
    for (i = 0; i < count; ++i) v |= (uint64_t)p[i] << (8u*i);
    return v;
}
static void put_uint(uint8_t *p, uint64_t v, unsigned count) {
    unsigned i; for (i = 0; i < count; ++i) p[i] = (uint8_t)(v >> (8u*i));
}
static double get_double(const uint8_t *p) {
    uint64_t bits = get_uint(p, 8); double value;
    memcpy(&value, &bits, 8); return value;
}
static void put_double(uint8_t *p, double value) {
    uint64_t bits; memcpy(&bits, &value, 8); put_uint(p,bits,8);
}
static tc_scalar scalar(double value) {
    tc_scalar v; v.value=value; v.numeric=1u; return v;
}
static uint32_t crc32(const uint8_t *p, unsigned count) {
    uint32_t crc=0xffffffffu; unsigned i,j;
    for (i=0;i<count;++i) {
        crc^=p[i]; for(j=0;j<8;++j) crc=(crc>>1)^((crc&1u)?0xedb88320u:0u);
    }
    return crc^0xffffffffu;
}
static void send_frame(uint8_t type, uint64_t sid, uint32_t seq, unsigned length) {
    unsigned i;
    memcpy(output,"LSC1",4); output[4]=1u; output[5]=type;
    put_uint(output+6,length,2); put_uint(output+8,sid,8); put_uint(output+16,seq,4);
    put_uint(output+HEADER+length,crc32(output,HEADER+length),4);
    for(i=0;i<HEADER+length+4;++i)uart_byte(output[i]);
}
static void error_frame(uint8_t code,uint64_t sid,uint32_t seq) {
    session=0; output[HEADER]=code; send_frame(0xffu,sid,seq,1);
}
static void copy_text(uint8_t *p, tc_text text) {
    memset(p,0,64); if(text.kind==TC_TEXT_STRING)memcpy(p,text.value,64);
}
static void reset_owners(void) {
    tc_init_snapshot(&gate_state); tc_init_clock(&clock_state);
    tc_init_command_guard_state(&guard_state);
}
static void step(uint64_t sid,uint32_t sequence) {
    tc_allocator_input ai; tc_allocator_config ac={1u,1u,50u};
    tc_allocation raw, observed;
    tc_command_guard_input gi;
    tc_command_guard_config gc;
    tc_command_guard_result base;
    tc_guard guarded;
    tc_clock_input ci; tc_clock_policy cp={10u}; tc_clock_result clock;
    tc_pedal_facts facts; tc_pedal_result pedal;
    tc_cycle cycle; tc_policy policy={2u}; tc_decision decision;
    uint8_t *body=input+HEADER,*reply=output+HEADER;
    uint8_t previous_state=gate_state.state, restart=body[77];
    unsigned i,offset;
    memset(&ai,0,sizeof(ai)); memset(&gi,0,sizeof(gi)); memset(&gc,0,sizeof(gc));
    ai.type_valid=ai.now_valid=ai.timestamp_valid=ai.limits_vector_valid=ai.enabled_vector_valid=1u;
    ai.now_ms=get_uint(body,8); ai.input_timestamp_ms=get_uint(body+8,8);
    ai.request=scalar(get_double(body+32)); ai.torque_unit.kind=TC_TEXT_STRING;
    memcpy(ai.torque_unit.value,"N*m",4);
    for(i=0;i<4;++i) { ai.limits[i]=scalar(get_double(body+40+8*i)); ai.enabled[i]=(body[72]>>i)&1u; }
    ai.external_interlock=body[76];
    gi.type_valid=gc.type_valid=1u; gi.dt_s=scalar(get_double(body+16));
    gi.accelerator=scalar(get_double(body+24));
    gi.brake=body[73];gi.comms=body[74];gi.sensors=body[75];gi.interlock=body[76];
    gc.max_rise=scalar(8000.);gc.trip=scalar(.25);gc.clear=scalar(.05);
    if(restart)for(i=0;i<4;++i)guard_state.previous[i]=scalar(0.);
    (void)tc_allocate_propulsive_torque(&ai,&ac,&raw);
    (void)tc_apply_command_guard(&raw,&gi,&gc,&guard_state,&base);
    ci.now_ms=ai.now_ms;ci.timestamp_valid=1u;ci.dt_s=gi.dt_s;
    (void)tc_clock_step(&clock_state,&ci,&cp,&clock);
    memset(&facts,0,sizeof(facts));
    facts.input_type_valid=facts.config_type_valid=facts.state_type_valid=facts.result_type_valid=1u;
    facts.previous_latched=guard_state.previous_latched;facts.base_next_latched=base.next.previous_latched;
    facts.accelerator=gi.accelerator;facts.rise=gc.max_rise;facts.trip=gc.trip;facts.clear=gc.clear;
    facts.brake=gi.brake;facts.comms=gi.comms;facts.sensors=gi.sensors;facts.interlock=gi.interlock;
    facts.candidate_type_valid=raw.type_valid;facts.candidate_status=raw.status;
    facts.guard_status=base.guard.status;facts.clock_fault_present=clock.fault.kind!=TC_TEXT_NONE;
    facts.base_reason=base.guard.reason;
    (void)tc_reconcile_pedal_latch(&facts,&pedal);
    guarded=base.guard;guarded.reason=pedal.reason;
    if(pedal.adapter_veto) {
        guarded.status=TC_GUARD_INHIBITED;guarded.output_valid=1u;
        for(i=0;i<4;++i)guarded.output[i]=scalar(0.);
    }
    observed=raw;
    if(clock.fault.kind || guarded.status==TC_GUARD_INHIBITED) {
        observed.status=TC_ALLOCATION_FAULT;observed.delivered=scalar(0.);
        for(i=0;i<4;++i)observed.wheels[i]=scalar(0.);
        observed.fault=clock.fault.kind?clock.fault:(raw.status==TC_ALLOCATION_FAULT?raw.fault:guarded.reason);
    }
    cycle.allocation=guarded.status==TC_GUARD_INHIBITED?observed:raw;
    cycle.guard=guarded;cycle.clock_fault=clock.fault;cycle.restart_requested=restart;
    (void)tc_decide(&gate_state,&cycle,&policy,&decision);
    memset(reply,0,391);
    put_uint(reply,clock.now_ms,8);offset=8;
    for(i=0;i<4;++i){put_double(reply+offset,raw.wheels[i].value);offset+=8;}
    put_double(reply+offset,raw.requested.value);offset+=8;
    put_double(reply+offset,raw.delivered.value);offset+=8;
    for(i=0;i<4;++i){put_double(reply+offset,guarded.output[i].value);offset+=8;}
    for(i=0;i<4;++i){put_double(reply+offset,decision.command[i]);offset+=8;}
    reply[offset++]=raw.status;reply[offset++]=guarded.status;reply[offset++]=decision.next.state;
    reply[offset++]=previous_state;reply[offset++]=pedal.next_latched;
    reply[offset++]=decision.command_allowed;reply[offset++]=restart;
    put_uint(reply+offset,decision.next.recovery_streak,4);offset+=4;
    put_uint(reply+offset,decision.next.generation,4);offset+=4;
    copy_text(reply+offset,clock.fault);offset+=64;
    copy_text(reply+offset,raw.fault);offset+=64;
    copy_text(reply+offset,guarded.reason);offset+=64;
    memcpy(reply+offset,decision.reason,64);offset+=64;
    guard_state.previous_latched=pedal.next_latched;
    for(i=0;i<4;++i)guard_state.previous[i]=scalar(decision.command[i]);
    gate_state=decision.next;clock_state=clock.next;
    ++next_sequence;
    send_frame(0x81u,sid,sequence,offset);
}
int main(void) {
    unsigned i,length; uint64_t sid; uint32_t sequence;
    const char *boot="LAPSIM_F405_BENCH_v1\n";
    REG(0x40023844u)|=1u<<4; REG(0x40011008u)=0x683u; REG(0x4001100cu)=0x200cu;
    while(*boot)uart_put((uint8_t)*boot++);
    reset_owners();
    for(;;) {
        transport_bad=0;
        for(i=0;i<HEADER;++i)input[i]=uart_get();
        sid=get_uint(input+8,8);sequence=(uint32_t)get_uint(input+16,4);
        length=(unsigned)get_uint(input+6,2);
        if(transport_bad||memcmp(input,"LSC1",4)||input[4]!=1u){error_frame(1,sid,sequence);continue;}
        if(length>MAX_FRAME-HEADER-4u){error_frame(2,sid,sequence);continue;}
        for(i=HEADER;i<HEADER+length+4u;++i)input[i]=uart_get();
        if(transport_bad){error_frame(1,sid,sequence);continue;}
        if((uint32_t)get_uint(input+HEADER+length,4)!=crc32(input,HEADER+length)){error_frame(3,sid,sequence);continue;}
        if(input[5]==2u) {
            if(length||!sid||sid<=last_session||sequence){error_frame(4,sid,sequence);continue;}
            session=last_session=sid;next_sequence=1;reset_owners();
            memcpy(output+HEADER,LAPSIM_BUILD_ID,64);
            put_uint(output+HEADER+64,10,4);put_uint(output+HEADER+68,50,4);put_uint(output+HEADER+72,2,4);
            send_frame(0x82u,sid,sequence,76);continue;
        }
        if(input[5]!=1u||length!=78u){error_frame(2,sid,sequence);continue;}
        if(!session||sid!=session){error_frame(4,sid,sequence);continue;}
        if(sequence!=next_sequence||sequence==0xffffffffu){error_frame(5,sid,sequence);continue;}
        if(input[HEADER+72]>15u){error_frame(6,sid,sequence);continue;}
        for(i=73;i<78;++i)if(input[HEADER+i]>1u)break;
        if(i!=78){error_frame(6,sid,sequence);continue;}
        step(sid,sequence);
    }
}
