# TC-00B source delta

Accessed 2026-10-03.

- Formula SAE Series Resources: https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx
  - current observed resource: 2027 Formula SAE Rules, V1
  - applicability: resource/version identity only; no signal values or compliance inferred

- Formula SAE Electric 2027 event listing:
  https://www.fsaeonline.com/cdsweb/reg/CompAttendance.aspx?CompetitionID=14b1f772-0ac9-4eef-a96e-cd02a076097d
  - current observed dates: 1–5 June 2027
  - applicability: event identity only

- STMicroelectronics/stm32f4xx-hal-driver
  - current inspected commit: `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05)
  - license: BSD-3-Clause
  - `Inc/stm32f4xx_hal_can.h` blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`
  - `Src/stm32f4xx_hal_can.c` blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`
  - license blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`
  - applicability: CAN transport/controller mechanisms only; no Terps Racing application-level IDs, units, signs, scales, ranges, periods or timeouts

- STM32F405/415 product page:
  https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415.html
  - family capability includes up to two classic CAN interfaces
  - applicability: family capability only

Project pins:
- ENME408 README `07723b05ab5201c2bd3c5d0eeb38f5586c3b412e`
- team evidence packet `79761b624b732ceb8a9567906cdef001941732bf`
- evidence contract `227aa14acdb9e325ccb0d1d43c36013019514a89`
- TC-03A `1a90a57645f2ebc5ed7ac2230c6075edadcddefb`

No source here establishes a Terps Racing CAN identifier, payload layout, signal unit, sign convention, scale, offset, range, sample period, timeout, timestamp domain, motor/inverter count or sensor availability.
