# TC-02U source index

Accessed 2026-10-04.

## ST STM32F4 HAL IWDG

Repository: `STMicroelectronics/stm32f4xx-hal-driver`

Pinned commit: `1f6451c3e07728b4c830744de380e56bf5bc0026`, dated 2026-06-05.

- Header:
  https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Inc/stm32f4xx_hal_iwdg.h
  - blob `5273730c147899c6fa48370ec34a4bb05b60a187`
  - prescaler divisors: 4, 8, 16, 32, 64, 128, 256
  - reload range: 0 through `0x0FFF`
  - reload key: `0xAAAA`; enable key: `0xCCCC`

- Source:
  https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Src/stm32f4xx_hal_iwdg.c
  - blob `bc03a530b84ea913de0cb44d76d1c8d3e009fb9c`
  - IWDG uses LSI and remains active when the main clock fails
  - nominal 32 kHz timeout examples are about 125 us minimum and 32.7 s maximum
  - timeout varies with LSI dispersion
  - source notes LSI can be measured using TIM5 CH4 input capture
  - debug-halt counting depends on `DBG_IWDG_STOP`

- License:
  https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/LICENSE.md
  - blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`
  - BSD-3-Clause

Applicability: public family/HAL mechanisms only. These files do not establish that the Terps Racing firmware uses HAL IWDG, nor any actual prescaler, reload, refresh path, option-byte mode or timeout requirement.

## STM32F405xx/407xx datasheet

STMicroelectronics DS8626 Rev 12, March 2026:
https://www.st.com/resource/en/datasheet/stm32f405rg.pdf

Relevant current-table evidence:
- Table 35, LSI oscillator characteristics, under its stated VDD/temperature conditions: 17 kHz minimum, 32 kHz typical and 47 kHz maximum.
- Figure 34: normalized LSI deviation versus temperature.

Applicability: MCU-family characterization. It does not establish the actual board operating envelope, measured LSI frequency, calibration, debugger configuration or source-specific watchdog timing.

## Formula SAE

Official Formula SAE document resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Observed 2026-10-04: `2027 Formula SAE Rules`, Version `V1`.

No Formula SAE value is used as an IWDG timeout, refresh interval, reset deadline or torque threshold in TC-02U.
