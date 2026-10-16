#include <stdint.h>
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
int main(void);
void Default_Handler(void) { for (;;) {} }
void Reset_Handler(void) {
    uint32_t *source = &_sidata, *target = &_sdata;
    while (target < &_edata) *target++ = *source++;
    for (target = &_sbss; target < &_ebss;) *target++ = 0;
    (void)main();
    for (;;) {}
}
__attribute__((section(".isr_vector"), used))
const uintptr_t vectors[16] = {
    (uintptr_t)&_estack, (uintptr_t)Reset_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler,
    (uintptr_t)Default_Handler, (uintptr_t)Default_Handler
};
