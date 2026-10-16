# TC-02R — CAN transmit publication evidence boundary

Status: portable synthetic reference only. Target remains the 2027-28 Terps Racing EV torque-control project.

## Decision

A future source-specific torque-control implementation must distinguish at least three facts:

1. a torque/control command was computed;
2. a CAN transmission request was accepted into a transmit mailbox; and
3. that mailbox later produced positive transmission-complete evidence.

Do not log `HAL_CAN_AddTxMessage(...) == HAL_OK` as “command delivered.” In the current STM32F4 HAL, `HAL_CAN_AddTxMessage()` loads one empty mailbox, sets `TXRQ`, and returns. The separate interrupt path later distinguishes `TXOK` completion from arbitration loss, transmission error, or abort.

This matters for torque-control evidence because a controller can calculate a perfectly bounded command while the transport fails to enqueue or complete it. Offline command traces must not silently collapse those stages into one “sent” label.

## Primary-source boundary

STMicroelectronics `stm32f4xx-hal-driver` commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05), BSD-3-Clause, was inspected.

`Src/stm32f4xx_hal_can.c` blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2` shows:

- `HAL_CAN_AddTxMessage()` checks the three transmit-mailbox-empty bits, selects an empty mailbox, writes frame metadata/data, sets its transmission-request bit, and returns `HAL_OK`.
- If all transmit mailboxes are full, that function returns `HAL_ERROR` after updating the HAL error code.
- `HAL_CAN_GetTxMailboxesFreeLevel()` counts the free transmit mailboxes.
- `HAL_CAN_IsTxMessagePending()` reports whether a selected mailbox still has a pending transmission request.
- The transmit IRQ path treats `TXOK` as the successful mailbox-complete callback. Arbitration-lost and transmission-error conditions are recorded separately; otherwise the abort callback is invoked.

`Inc/stm32f4xx_hal_can.h` blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d` defines per-mailbox arbitration-lost and transmit-error categories and the three transmit-mailbox callback IDs.

These are public STM32F4 HAL mechanisms. They do not prove that Terps Racing uses this HAL, that torque commands are CAN-transmitted, which IDs or payloads exist, which mailbox/priority policy is used, or what a receiving inverter considers valid.

## Portable model

`can_tx_publication_evidence.py` keeps command intent, mailbox enqueue, and terminal transmission result separate.

Each synthetic command has a contiguous evidence sequence and non-vehicle `request_tag`.

States:
- `computed_not_enqueued`
- `enqueue_rejected`
- `pending`
- `transmitted`
- `tx_failed`

Terminal failure reasons are represented separately as `arbitration_lost`, `transmit_error`, and `aborted`.

The model validates an optional HAL-like free-level observation from 0 through 3, but does not infer which command completed from free level alone.

`transmitted` means only that the synthetic evidence stream contains a positive transmit-complete event. It does not establish receiving-node application, motor/inverter acceptance, commanded torque production, vehicle response, or safety.

## Source-specific handoff

After TC-03A/TC-03B0:

1. identify the actual command-output path and whether it uses CAN;
2. identify the exact enqueue call and its return handling;
3. identify mailbox-complete/error/abort evidence and whether those callbacks are already owned elsewhere;
4. capture requested-command sequence separately from transport result;
5. bind timestamps to the verified clock domain from TC-03A;
6. if transmit instrumentation is added, include its RAM/flash impact in TC-03B1/B2 and its execution overhead in TC-03B3;
7. test mailbox saturation, pending completion, arbitration/error paths and logging-buffer loss without changing retry or vehicle-control policy;
8. do not infer inverter acceptance from MCU transmit completion.

No CAN transmission, firmware flashing, HIL, dyno, track test, watchdog/shutdown change or vehicle actuation is authorized by this packet.
