# SOURCES-TC-03B21 — bxCAN loopback/silent bench-test evidence

Accessed 2026-10-04.

## STM32F405-family reference manual

STMicroelectronics RM0090, STM32F405/415, STM32F407/417, STM32F427/437 and
STM32F429/439 advanced Arm-based 32-bit MCUs.

Official current documentation page:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html

Official RM0090 URL:
https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-407-415-417-437-455-469-application-note-stmicroelectronics.pdf

Current ST documentation listing was rechecked on 2026-10-04. The connected
web runtime could not open the current PDF because it exceeded the direct PDF
fetch limit, so no page screenshot from the current file is claimed in this
pass. ST's indexed RM0090 section 32.5 exposes these bxCAN test-mode semantics:

- Silent mode: bxCAN can receive valid data/remote frames, sends only recessive
  bits on the bus, and cannot start a transmission.
- Loopback mode: transmitted messages are fed back internally and stored if
  they pass acceptance filtering; the CANRX input is disregarded; acknowledge
  errors are ignored for the self-test; transmitted activity remains observable
  on CANTX.
- Silent + loopback: internal loopback is retained while CANRX is disconnected
  and CANTX is held recessive. RM0090 describes this as a hot self-test that
  does not affect a running CAN system through dominant CANTX output.

Applicability:
These are bxCAN controller semantics. They do not prove the Terps Racing
transceiver, GPIO alternate-function configuration, board isolation, wiring,
termination, bus bitrate, peer acknowledgement, or inverter communication.

## STM32F4 HAL driver

Repository:
https://github.com/STMicroelectronics/stm32f4xx-hal-driver

Current head rechecked:
`1f6451c3e07728b4c830744de380e56bf5bc0026`

Pinned files:
- `Inc/stm32f4xx_hal_can.h`
  - blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`
  - defines `CAN_MODE_NORMAL`, `CAN_MODE_LOOPBACK`, `CAN_MODE_SILENT`, and
    `CAN_MODE_SILENT_LOOPBACK`.
- `Src/stm32f4xx_hal_can.c`
  - blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`
  - `HAL_CAN_Init()` writes `hcan->Init.Mode` into the CAN bit-timing register
    together with SJW, BS1, BS2, and prescaler.
- `LICENSE.md`
  - BSD-3-Clause.

Applicability:
HAL mode constants/configuration prove API support only. They do not prove
Terps Racing uses this HAL or any particular mode.

## Formula SAE

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing at access:
- `2027 Formula SAE Rules` — Version `V1`.

TC-03B21 derives no CAN test-mode requirement, bus bitrate, torque threshold,
bench acceptance, or vehicle-safety conclusion from Formula SAE rules.

## Evidence boundary

TC-03B21 classifies evidence scopes only:
- internal controller Tx->Rx/filter roundtrip;
- passive external receive observation;
- controller-output nonintrusiveness under the configured test mode.

It explicitly does not promote an internal-mode receipt into evidence for:
- transceiver operation;
- CAN_H/CAN_L wiring or termination;
- peer ACK;
- real arbitration;
- normal-mode integration;
- inverter receipt;
- vehicle safety or performance.
