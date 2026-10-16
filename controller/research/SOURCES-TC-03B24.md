# SOURCES-TC-03B24 — bxCAN 32-bit acceptance-filter evidence

Accessed 2026-10-05.

## STMicroelectronics RM0090

Official current documentation page:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html

Official RM0090 URL:
https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-407-415-417-437-455-469-application-note-stmicroelectronics.pdf

Current ST catalogue status rechecked at access:
- RM0090 Version 22.0
- latest update 29 May 2026

The connected PDF fetcher could not open the current >10 MiB RM0090 as a page
object. A screenshot call was attempted for the relevant bxCAN filter section
and failed because the fetch result was not exposed as application/pdf. No
unseen Rev 22 page screenshot is claimed.

ST-indexed RM0090 section 32.7.4 / Figure 342 provides the filter semantics used
by TC-03B24:

- filter-bank mode selects identifier-mask or identifier-list operation;
- scale selects 16-bit or 32-bit organization;
- for one 32-bit identifier-mask filter, FR1 contains the identifier and FR2
  contains the mask;
- for two 32-bit identifier-list filters, FR1 and FR2 each contain one
  identifier;
- the 32-bit comparison word maps:
  `STID[10:0] | EXID[17:0] | IDE | RTR | 0`;
- masked filters compare only the masked bits;
- unused filters should remain deactivated;
- accepted frames carry a Filter Match Index according to the controller's
  filter-priority/index rules.

Primary indexed source:
https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-407-415-417-437-455-469-application-note-stmicroelectronics.pdf

Applicability:
TC-03B24 implements only the 32-bit mask/list comparison geometry. It does not
model 16-bit filters, multi-bank priority, FMI numbering, CAN1/CAN2 bank
partition ownership, FIFO overrun, or any team-specific identifiers.

## STM32F4 HAL driver

Repository:
https://github.com/STMicroelectronics/stm32f4xx-hal-driver

Pinned project revision:
`1f6451c3e07728b4c830744de380e56bf5bc0026`

`Inc/stm32f4xx_hal_can.h`
blob:
`b4c229b209c494669ce05cdef1d4e62ad8c9079d`

Relevant current declarations:
- `CAN_FILTERMODE_IDMASK`
- `CAN_FILTERMODE_IDLIST`
- `CAN_FILTERSCALE_16BIT`
- `CAN_FILTERSCALE_32BIT`
- `CAN_FilterTypeDef`
- `CAN_RxHeaderTypeDef.FilterMatchIndex`

For dual-CAN instances, the header documents 28 shared filter banks and
`SlaveStartFilterBank`; for single-CAN instances it documents 14 dedicated
banks. TC-03B24 therefore does not infer bank ownership from a filter-bank
number alone.

`Src/stm32f4xx_hal_can.c`
blob:
`9278c96e1883ea0909c0c10754fed68b41ca0ef2`

Relevant current behavior:
- for 32-bit scale, HAL writes
  `FR1 = (FilterIdHigh << 16) | FilterIdLow`;
- `FR2 = (FilterMaskIdHigh << 16) | FilterMaskIdLow`;
- FM1R selects mask vs list mode;
- FIFO assignment is configured separately;
- `HAL_CAN_GetRxMessage()` copies the hardware FMI field into
  `RxHeader.FilterMatchIndex`.

Applicability:
HAL source proves the public API/register mapping, not Terps Racing firmware,
filter contents, IDs, FIFO assignment, or payload semantics.

## Existing ENME408 project boundary

- `research/SOURCES-TC-03B21.md`: internal loopback/silent test evidence;
  loopback frames still pass acceptance filtering before reaching an Rx mailbox.
- `reference/can_rx_age_evidence.py`
  blob `ab13e6b5de1180d1853b3784c5897439da7bb88f`: receive-age provenance.
- `reference/can_tx_publication_evidence.py`
  blob `78857bb0edb871cb57cd2c2977be284b6a1f227d`: command intent/enqueue/terminal
  transmit evidence.

TC-03B24 adds exact 32-bit filter comparison and a frame-class collision
counterexample. It does not redefine message freshness or Tx publication.

## Formula SAE

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing at access:
- `2027 Formula SAE Rules` — Version `V1`.

TC-03B24 derives no CAN identifier, filter requirement, torque response, or
safety threshold from Formula SAE rules.

No private team data was used in public web queries.
