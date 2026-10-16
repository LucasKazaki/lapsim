# SOURCES-TC-02AH — wrap-safe uint32 timebase freshness

Accessed 2026-10-06.

## Current repository boundary

PR #66 head before this write attempt:
`1fa9d3c0d62f300fe1cc745f16647fc143b2c30f`.

The TC-01Q power-budget signal gate is still not persisted on this branch.
TC-02AH is therefore an additive embedded-feasibility reference, not a production
edit to TC-01Q.

## ST STM32F4 HAL timebase

Official STMicroelectronics STM32F4 HAL driver:
https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/master/Src/stm32f4xx_hal.c

Current source observations:
- `uwTick` is declared `__IO uint32_t`;
- the default HAL timebase increments `uwTick`;
- `HAL_GetTick()` returns `uint32_t`;
- `HAL_Delay()` stores a `uint32_t tickstart` and compares
  `(HAL_GetTick() - tickstart) < wait`.

Applicability:
This demonstrates that ST's default HAL uses unsigned modular subtraction for
elapsed-time logic. It does not prove the Terps Racing firmware uses HAL_GetTick,
the default SysTick implementation, a 1 ms tick, or this timebase for torque
control.

## STM32F405/415 documentation

Current ST documentation catalogue:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html

At access:
- RM0090 reference manual V22.0, updated 28 May 2026;
- DS8626 datasheet V12.0, updated 15 Apr 2026;
- PM0214 programming manual V11.0, updated 27 Feb 2025.

Current product information:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405oe.html

The product page identifies STM32F405/407 as Cortex-M4 devices up to 168 MHz and
lists two general-purpose 32-bit timers. TC-02AH does not infer which timer, if
any, the team firmware uses.

## Formula SAE Electric scope

Official Formula SAE competition resources:
https://www.fsaeonline.com/app/CompetitionResources.aspx

Official Formula SAE Electric 2027 event:
https://www.fsaeonline.com/cdsweb/reg/CompAttendance.aspx?CompetitionID=14b1f772-0ac9-4eef-a96e-cd02a076097d

At access the official site lists Formula SAE Electric 2027 for 1–5 June 2027.

TC-02AH derives no CAN timing, timeout, control-loop period, or vehicle response
from Formula SAE rules.

## Portable design decision

For a modulo-2^32 counter:

`delta = (now - sample) mod 2^32`.

Interpret `delta` as forward elapsed time only when `delta < 2^31`.
Exactly `2^31` is ambiguous; above the half range is future-or-ambiguous.

The rule is valid only when both timestamps use the same monotonic counter domain
and the physical interval being classified is guaranteed to be less than half
the counter range.

For a true 1 ms uint32 counter:
- full wrap: 2^32 ms, about 49.71 days;
- half range: 2^31 ms, about 24.86 days.

Those durations are arithmetic properties of that hypothetical counter, not
Terps Racing requirements.

## Explicit unknowns

Unverified:
- actual firmware time source;
- timestamp width;
- tick period;
- clock domain shared by producer and receiver;
- reset/restart behavior;
- whether timestamps are local-receive time or producer time;
- stale threshold;
- maximum interval assumption;
- actual compiler and generated target code;
- selected vehicle response on invalid timing evidence.
