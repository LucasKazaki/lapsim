# TC-03B17 source delta

Accessed 2026-10-03.

Primary sources:

- STMicroelectronics stm32f4xx-hal-driver
  - repository: https://github.com/STMicroelectronics/stm32f4xx-hal-driver
  - current master observed at commit 1f6451c3e07728b4c830744de380e56bf5bc0026, dated 2026-06-05
  - license: BSD-3-Clause
  - Src/stm32f4xx_hal_pwr.c blob 5ccde6489e2405b5b3a2347f01364fd831bec0db
    - documents Stop-mode clock shutdown behavior
  - Inc/stm32f4xx_ll_system.h blob 84ea5c4d1a32511168b9bc305d26583d410cd350
    - exposes timer debug-freeze bits such as LL_DBGMCU_APB1_GRP1_TIM2_STOP
  - Inc/stm32f4xx_hal.h blob f7eb847b3c1546bbe5b1c775e76f56dcd9cf9d84
    - exposes HAL timer freeze/unfreeze macros
  - license blob 479c4f682608052abf9c99e8b71fb6bc2d8d15d7

- Arm CMSIS-Core DWT reference:
  https://arm-software.github.io/CMSIS_6/main/Core/structDWT__Type.html
  - CYCCNT is exposed as a uint32_t cycle-count register.
  - applicability: register availability does not prove continuity across any team-specific sleep, halt, reset or reclock path.

- Formula SAE Series Resources:
  https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx
  - current observed resource on 2026-10-03: 2027 Formula SAE Rules, Version V1.
  - applicability: rules-resource identity only. TC-03B17 derives no timeout, recovery duration or control threshold from it.

Project sources:
- projects/enme408-torque-control/research/TC-03B16.md
  blob e77d6ebe50bd4b8b839235d6d2e758b79b08311d
- projects/enme408-torque-control/reference/timebase_freshness.py
  blob cfa7bf78644093e06858d6cd40b9c434b9095756
- projects/enme408-torque-control/README.md
  blob 07723b05ab5201c2bd3c5d0eeb38f5586c3b412e

No source here establishes the real 2027-28 critical signal set, timebase source,
epoch ownership, recovery action, CAN interface, watchdog behavior or torque-resume policy.
