# SOURCES-TC-02AE — bxCAN receive FIFO locked-mode retention under overrun

Accessed 2026-10-04.

## STMicroelectronics STM32F4 HAL

Repository: `STMicroelectronics/stm32f4xx-hal-driver`
Pinned commit: `1f6451c3e07728b4c830744de380e56bf5bc0026`
Commit date: 2026-06-05T11:22:04Z
License: BSD-3-Clause, blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`.

Pinned CAN files:
- `Inc/stm32f4xx_hal_can.h`, blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`: `CAN_InitTypeDef.ReceiveFifoLocked` enables/disables Receive FIFO Locked mode.
- `Src/stm32f4xx_hal_can.c`, blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`: `HAL_CAN_Init()` sets `CAN_MCR_RFLM` when `ReceiveFifoLocked == ENABLE` and clears it otherwise; `HAL_CAN_GetRxMessage()` releases the FIFO output after reading; the IRQ path records Rx FIFO overrun in the HAL error code and clears the peripheral overrun flag.

Pinned URLs:
- https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Inc/stm32f4xx_hal_can.h
- https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Src/stm32f4xx_hal_can.c
- https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/LICENSE.md

Applicability: these public HAL facts do not establish the Terps Racing firmware stack, actual `ReceiveFifoLocked` value, filter/FIFO assignment, interrupt policy, traffic rate, or freshness threshold.

## STM32F405-family RM0090

ST's current STM32F405/415 documentation catalogue lists RM0090 Version 22.0, updated 2026-05-29. The connected PDF runtime could not open the current >10 MiB PDF for screenshot inspection in this pass.

Official ST-indexed RM0090 Rev 21 bxCAN text states:
- each receive FIFO becomes full when three messages are stored;
- a valid message arriving while full causes overrun;
- RFLM=0: the last message stored in the FIFO is overwritten by the new incoming message, so the latest message remains available;
- RFLM=1: the incoming message is discarded, leaving the three older messages available.

Official ST URL:
https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-407-415-417-437-455-469-application-note-stmicroelectronics.pdf

The portable reference models only this retention distinction and the fact that either branch still represents message loss.

## Formula SAE

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing at access: `2027 Formula SAE Rules`, Version `V1`.

TC-02AE derives no CAN FIFO mode, signal period, timeout, resynchronization rule, torque threshold, or safety action from Formula SAE rules.

## Existing project references

- `reference/can_rx_age_evidence.py`, blob `ab13e6b5de1180d1853b3784c5897439da7bb88f`: receive-age/freshness evidence; it does not establish continuity after overrun.
- `research/TC-02Y-HANDOFF.md`, blob `69a4a28fe3a33fac2a72688d9e4ac7d45f404e59`: prior finding that FIFO overrun compromises continuity and a later fresh frame alone does not prove restoration.
- `research/TC-02Y-RECEIPT.md`, blob `d7cfe1848e329218fbf454d87fcf4c9f14f75866`.

TC-02AE adds the configuration-specific survivor question: after the same overrun, which message remains available depends on RFLM. It does not replace TC-02Y's continuity rule.

No private team data was used in public web queries.
