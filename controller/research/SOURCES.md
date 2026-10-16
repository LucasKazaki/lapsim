# ENME408 torque-control source index — 2026-10-01

This index records public research provenance for the scoped ENME408 torque-control reference work. It does not establish Terps Racing hardware, vehicle parameters, firmware architecture, rule compliance, or measured performance.

## Official STM32 sources

- STMicroelectronics, STM32F405/415 documentation catalogue: RM0090 v22.0, updated 2026-05-28; PM0214 v11.0, updated 2025-02-27. Used as the current STM32F405-family documentation baseline. Exact team part/package, PCB, clocks, wiring, peripherals, and firmware remain unverified.
- STMicroelectronics/stm32f4xx-hal-driver commit `1f6451c3e07728b4c830744de380e56bf5bc0026`, accessed 2026-10-01, BSD-3-Clause.
  - `Inc/stm32f4xx_hal_can.h` blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`: CAN error-warning, error-passive, bus-off, FIFO-overrun categories; interrupt/error APIs; `AutoBusOff` configuration field.
  - `Src/stm32f4xx_hal_can.c` blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`: `HAL_CAN_GetError` returns the handle error code, `HAL_CAN_ResetError` can clear it in READY/LISTENING state, and `HAL_CAN_ErrorCallback` is a weak user-overridable callback.
  - Applicability: mechanisms available in the current STM32F4 HAL. This does **not** prove Terps Racing uses this HAL or any particular CAN/recovery configuration.
- STMicroelectronics/cmsis-core commit `afc5ca6af0a49232fde7eb4548dd0962d119ce14`, Apache-2.0. `CMSIS/Core/Include/core_cm4.h` blob `770908a619b47e43d9bdbaf909b83a9b917d095b` was used for the TC-02 cycle-counter boundary. It exposes the Cortex-M4 DWT cycle-counter interface; actual team use remains unverified.

## Official Formula SAE source

- Formula SAE Online, “Important Updates for the 2027 Formula SAE Season,” published 2026-09-15, accessed 2026-10-01. Confirms 2027-season updates/rules publication. The final rules body was not retrieved into this research branch, so no numbered rule or compliance threshold is claimed from this source.

## Controls literature

- Sun, Lee and Tian, “Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE Racing Car,” SAE 2021-01-0373, published 2021-04-06. Supports separating an upper yaw objective from lower torque distribution. Different vehicle; not a source of Terps Racing parameters.
- “Performance Prediction of a 4WD High-Performance Electric Vehicle Using a Model-Based Torque-Vectoring Approach,” World Electric Vehicle Journal 14(7):183, published 2023-07-13. Supports telemetry-calibrated modeling before performance claims. Not Terps Racing validation.

## Current use in this branch

- TC-01A: conservative synthetic allocation baseline.
- TC-02D/TC-02E: wrap-safe timestamp age and timebase provenance.
- TC-02G: communication-health observation taxonomy.
- TC-02H: replayable communication evidence logging and evidence-before-reset ordering.

Web/public-source access date: 2026-10-01.


## TC-02O ADC sampling provenance

- STMicroelectronics/stm32f4xx-hal-driver commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05), BSD-3-Clause.
  - `Inc/stm32f4xx_hal_adc.h` blob `c79a073e913dc6bd23b29561db4916755c75ff22`: regular scan-mode rank ordering, per-channel sampling time, and the documented conversion-time formula (sampling plus 12/11/9/7 ADC-clock processing cycles at 12/10/8/6-bit resolution).
  - `Src/stm32f4xx_hal_adc.c` blob `f37d00e1fda16a9aa6cc6f952771e640d7d66746`: polling, interrupt, and DMA conversion paths plus conversion/overrun handling.
  - Applicability: public STM32F4 HAL behavior only; this does not establish the Terps Racing ADC clock, channel order, DMA use, timestamping, or firmware architecture.

Current branch use:
- TC-02O: portable sample-coherence analysis before pedal-channel plausibility comparison.


## TC-03B0 build-reproduction provenance

- Git project, `git-rev-parse` documentation, accessed 2026-10-01. The current manual identifies version 2.56.0 dated 2026-09-28 and documents `--verify` plus `^{commit}` for resolving/verifying a commit object.
- Git project, `git-status` documentation, accessed 2026-10-01. Porcelain format v1 is guaranteed not to change incompatibly across Git versions or user configuration and is intended for machine parsing.
- Git project, `git-submodule` documentation, accessed 2026-10-01. `status --recursive` reports checked-out submodule commits and prefixes uninitialized, mismatched and conflicted states with `-`, `+` and `U`.
- GitHub Docs, “Artifact attestations,” accessed 2026-10-01. Used only for the provenance principle that artifacts should be bound to source/build context; GitHub explicitly notes that attestation does not guarantee artifact security.

Current branch use:
- TC-03B0: untouched-build reproduction receipt and exact source/build/artifact provenance boundary before source-specific instrumentation.

## TC-03B3 timing-measurement provenance

- Arm Cortex-M4 Technical Reference Manual, ARM DDI 0439B, Chapter 9, accessed 2026-10-01. The DWT is an optional profiling/debug unit; when present it includes the clock-cycle counter `CYCCNT`, and `DWT_CYCCNT` is listed as the read/write Cycle Count Register.
- ARM-software/CMSIS_6 release `v6.3.0`, Apache-2.0. `CMSIS/Core/Include/core_cm4.h` blob `770908a619b47e43d9bdbaf909b83a9b917d095b` exposes the 32-bit DWT cycle-counter register and its control/debug enable definitions. License blob: `8dada3edaf50dbc082c9a125058f25def75e625a`.
- STMicroelectronics STM32F405 product/documentation pages, accessed 2026-10-01. Family material states operation up to 168 MHz; that is a family maximum, not evidence of the Terps Racing board's actual core clock.

Applicability: public processor/family capability only. DWT availability/enablement, actual core clock, debugger state, interrupt policy and the real control-loop deadline remain unverified team-source items.
