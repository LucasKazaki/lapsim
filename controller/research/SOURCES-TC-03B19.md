# TC-03B19 sources

Accessed 2026-10-03.

- STMicroelectronics stm32f4xx-hal-driver head: `1f6451c3e07728b4c830744de380e56bf5bc0026`.
- CAN header blob: `b4c229b209c494669ce05cdef1d4e62ad8c9079d`. The Rx header documents a timestamp captured at receiver start of frame when TTCM is enabled, with values through 0xFFFF.
- CAN source blob: `9278c96e1883ea0909c0c10754fed68b41ca0ef2`. HAL_CAN_GetRxMessage reads the receive TIME field; FIFO retrieval may occur later.
- ST HAL driver license blob: `479c4f682608052abf9c99e8b71fb6bc2d8d15d7` (BSD-3-Clause).
- ST documentation currently lists RM0090 Version 22.0, updated 2026-05-29, for STM32F405/415-family devices.
- Formula SAE official resources currently list 2027 Formula SAE Rules V1.

Applicability: receiver SOF timestamp evidence does not establish producer sample time, clock mapping, signal age, CAN IDs, periods, or vehicle timeout thresholds.
