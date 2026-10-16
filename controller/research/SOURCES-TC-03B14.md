# TC-03B14 source delta

Accessed 2026-10-03.

- STMicroelectronics `stm32f4xx-hal-driver`, commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05), BSD-3-Clause.
  - `Src/stm32f4xx_hal_tim.c` blob `2d9babf28655f0d6ec0fc47928e71d5c39148052`: current HAL update IRQ path clears `TIM_FLAG_UPDATE` before calling `PeriodElapsedCallback`.
  - `Inc/stm32f4xx_hal_tim.h` blob `bbc933f6298d19aaf684404937d751e5b9641571`: current status-flag and counter-access macros.
  - Repository: https://github.com/STMicroelectronics/stm32f4xx-hal-driver
- Arm CMSIS-Core, current Cortex-M core register access:
  https://arm-software.github.io/CMSIS_6/main/Core/group__Core__Register__gr.html
  - documents PRIMASK read/write helpers and that interrupt requests may become pending while interrupt activation is masked.
- ST STM32F405/415 documentation catalogue:
  https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html
  - current catalogue lists RM0090 v22.0, updated 29 May 2026.

Applicability: these sources establish public HAL/architecture mechanisms only. They do not establish the Terps Racing timer, software overflow-extension design, interrupt priorities, reader context, high-word writer, flag-clear owner, service-latency bound, or publication atomicity.
