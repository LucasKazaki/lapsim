# TC-03B16 source delta

Accessed 2026-10-03.

Primary sources:

- STMicroelectronics `stm32f4xx-hal-driver`
  commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05).
  License: BSD-3-Clause; license blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`.
  https://github.com/STMicroelectronics/stm32f4xx-hal-driver

  Exact inspected files:
  - `Inc/stm32f4xx_ll_system.h`
    blob `84ea5c4d1a32511168b9bc305d26583d410cd350`.
    Used for the existence/meaning of STM32F4 DBGMCU timer-freeze controls.
  - `Inc/stm32f4xx_hal.h`
    blob `f7eb847b3c1546bbe5b1c775e76f56dcd9cf9d84`.
    Used for HAL timer freeze/unfreeze macros.
  - `Src/stm32f4xx_hal_pwr.c`
    blob `5ccde6489e2405b5b3a2347f01364fd831bec0db`.
    Used for STM32F4 Sleep/Stop entry paths and the documented Stop-wakeup
    system-clock behavior.

  Applicability:
  Available STM32F4 HAL mechanisms only. They do not establish Terps Racing
  low-power-mode reachability, debug-freeze configuration, selected timer, or
  runtime clock restoration.

- Arm CMSIS-Core DWT documentation:
  https://arm-software.github.io/CMSIS_6/main/Core/structDWT__Type.html
  Used for the 32-bit DWT CYCCNT architectural counter boundary.
  Applicability: counter availability does not prove continuity through debug
  halt, Sleep, Stop, explicit reset, or source-specific firmware reconfiguration.

- STMicroelectronics STM32F405/415 family page:
  https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415.html
  Used only for family-level low-power/debug context.

No source in this packet establishes the Terps Racing exact timebase, low-power
reachability, debug-freeze state, runtime clock transitions, epoch policy,
freshness/timeout thresholds, or vehicle acceptance criteria.
