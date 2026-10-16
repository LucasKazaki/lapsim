# SOURCES-TC-02AD — bxCAN transmit FIFO priority and local mailbox ordering

Accessed 2026-10-04.

## STMicroelectronics STM32F4 HAL

Repository: `STMicroelectronics/stm32f4xx-hal-driver`
Pinned commit: `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05T11:22:04Z)
License: BSD-3-Clause, blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`.

Pinned CAN files:
- `Inc/stm32f4xx_hal_can.h`, blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`: `CAN_InitTypeDef.TransmitFifoPriority` enables/disables transmit FIFO priority.
- `Src/stm32f4xx_hal_can.c`, blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`: `HAL_CAN_Init()` sets `CAN_MCR_TXFP` when `TransmitFifoPriority == ENABLE`; `HAL_CAN_AddTxMessage()` selects an empty hardware mailbox, writes the frame, and sets TXRQ.

Pinned URLs:
- https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Inc/stm32f4xx_hal_can.h
- https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Src/stm32f4xx_hal_can.c
- https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/LICENSE.md

## STM32F405-family RM0090

Official ST-indexed RM0090 result states:
- TXFP=0: among multiple pending local transmit mailboxes, priority follows message identifier; lower identifier wins, and equal identifiers fall back to lower mailbox number.
- TXFP=1: local mailbox priority follows transmit request order.

Official URL:
https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-407-415-417-437-455-469-application-note-stmicroelectronics.pdf

The current PDF exceeded the connected web runtime's direct fetch limit, so this pass could not perform a screenshot/page inspection and makes no additional unseen figure/table claim.

Design consequence: TXFP changes only the controller's selection among its own pending mailboxes. It is not an application-level newest-setpoint/coalescing policy and does not model external CAN arbitration against other nodes.

## Formula SAE

Official Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing: `2027 Formula SAE Rules`, V1.

TC-02AD derives no CAN identifier assignment, TXFP setting, queueing policy, freshness threshold, torque value, or safety action from those rules.

## Existing project references

- `reference/can_tx_publication_evidence.py`, blob `78857bb0edb871cb57cd2c2977be284b6a1f227d`
- `reference/timebase_freshness.py`, blob `cfa7bf78644093e06858d6cd40b9c434b9095756`

TC-02AD is additive and descriptive. No private team data was used in public queries.
