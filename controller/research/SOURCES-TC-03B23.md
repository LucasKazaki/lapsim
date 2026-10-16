# SOURCES-TC-03B23 — bxCAN live error state, HAL error history, and bus-off recovery

Accessed 2026-10-04.

## STMicroelectronics RM0090

Official current product documentation:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html

Official RM0090 URL:
https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-407-415-417-437-455-469-application-note-stmicroelectronics.pdf

Current catalogue status at access:
- RM0090 Version 22.0
- latest update 29 May 2026

The connected PDF runtime could not open the current >10 MiB PDF, so no page
screenshot from Rev 22 is claimed.

Official ST-indexed RM0090 Rev 21 text supplies the detailed bxCAN error-state
semantics used here:
- CAN_ESR.REC[7:0] is the receive error counter.
- CAN_ESR.TEC[7:0] is only the least significant byte of the 9-bit transmit
  error counter.
- EWGF is asserted when REC or TEC reaches the warning limit (>=96).
- EPVF is asserted when REC or TEC exceeds 127.
- BOFF is asserted when the transmit error counter overflows beyond 255.
- In bus-off, bxCAN can no longer transmit or receive.
- With ABOM set, bxCAN begins the recovery sequence automatically after entering
  bus-off.
- With ABOM cleared, software must request initialization entry/exit to initiate
  recovery.
- In either case recovery still requires the CAN-standard idle sequence of 128
  occurrences of 11 consecutive recessive bits monitored on CANRX.
- Initialization mode itself does not monitor CANRX and therefore cannot
  complete that recovery sequence.

Primary indexed sources:
https://www.st.com/resource/en/reference_manual/rm0090-stm32f407-advanced-armbased-32bit-mcus-stmicroelectronics.pdf

Applicability:
These are controller semantics. They do not establish the Terps Racing
AutoBusOff/ABOM setting, physical bus health, transceiver, wiring, recovery
policy, application response, or safe torque behavior.

## STM32F4 HAL driver

Repository:
https://github.com/STMicroelectronics/stm32f4xx-hal-driver

Current inspected head:
`1f6451c3e07728b4c830744de380e56bf5bc0026`
Commit timestamp:
`2026-06-05T11:22:04Z`

Pinned files:
- `Inc/stm32f4xx_hal_can.h`
  - blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`
  - defines `HAL_CAN_ERROR_EWG`, `HAL_CAN_ERROR_EPV`, `HAL_CAN_ERROR_BOF`, the
    protocol-error bits, `CAN_IT_ERROR_WARNING`, `CAN_IT_ERROR_PASSIVE`,
    `CAN_IT_BUSOFF`, and `CAN_IT_LAST_ERROR_CODE`.
  - `CAN_InitTypeDef.AutoBusOff` configures automatic bus-off management.
- `Src/stm32f4xx_hal_can.c`
  - blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`
  - `HAL_CAN_Init()` maps `AutoBusOff == ENABLE` to `CAN_MCR_ABOM`.
  - the IRQ handler reads EWGF/EPVF/BOFF/LEC, ORs the corresponding HAL error
    bits into `hcan->ErrorCode`, then calls the error callback.
  - `HAL_CAN_GetError()` returns the software handle's `ErrorCode`.
  - `HAL_CAN_ResetError()` clears that software error word only when HAL state is
    READY or LISTENING; it does not clear CAN_ESR hardware fault state.

License:
BSD-3-Clause.

Applicability:
HAL error history and live CAN_ESR state are different evidence sources.
Clearing the HAL software word is not hardware bus-off recovery, and a stale HAL
history bit is not proof that BOFF is still asserted now.

## Formula SAE

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing:
- `2027 Formula SAE Rules` — Version `V1`.

TC-03B23 derives no CAN recovery policy, error-counter threshold beyond bxCAN
hardware semantics, torque reaction, or bench acceptance rule from Formula SAE.

## Existing project boundary

TC-03B21 defines controller-local loopback/silent test evidence.
TC-03B22 defines bit-timing provenance before an external bench.

TC-03B23 adds the live error-state/history/recovery evidence needed before a
physical-bus receipt can safely say whether the controller is currently active,
warning, passive, or bus-off and whether an earlier fault is merely historical.

No private team data was used in public queries.
