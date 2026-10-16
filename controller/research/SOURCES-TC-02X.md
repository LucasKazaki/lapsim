# TC-02X source index — CAN receive-age timestamp provenance

Accessed 2026-10-04. This source index supports a portable receive-age evidence contract only. It does not establish Terps Racing CAN IDs, signal rates, interrupt latency, firmware architecture, or vehicle safety behavior.

## STMicroelectronics STM32F405/407 and STM32F415/417 errata

- STMicroelectronics, **ES0182 Rev 19, July 2026**, “STM32F405/407xx and STM32F415/417xx device errata.”
  - URL: https://www.st.com/resource/en/errata_sheet/dm00037591-stm32f405-407xx-and-stm32f415-417xx-device-limitations-stmicroelectronics.pdf
  - Applicability table includes STM32F405xx, STM32F407xx, STM32F415xx and STM32F417xx device families.
  - Section 2.13.1, page 29/45: bxCAN time-triggered communication mode is not supported; timestamp values are not available; CAN_MCR.TTCM must remain cleared; no workaround is listed.
  - The summary table marks this limitation as applicable with no workaround for every listed silicon revision in the document.
  - Applicability to the Terps Racing custom PCB still requires the exact MCU part/package/revision receipt. The user has identified STM32F405 as the intended MCU family, but the repository does not yet contain the authorized board receipt.

## STM32F4 HAL CAN driver

- Repository: https://github.com/STMicroelectronics/stm32f4xx-hal-driver
- Inspected commit: `1f6451c3e07728b4c830744de380e56bf5bc0026`
- Committer date: 2026-06-05
- License: BSD-3-Clause (`LICENSE.md` at the inspected revision).
- Header: `Inc/stm32f4xx_hal_can.h`
  - `CAN_RxHeaderTypeDef.Timestamp` is documented as a timestamp counter value captured at start of frame reception, with the explicit note that Time Triggered Communication Mode must be enabled.
  - `CAN_InitTypeDef.TimeTriggeredMode` exposes TTCM configuration in the generic HAL API.
- Source: `Src/stm32f4xx_hal_can.c`
  - `HAL_CAN_GetRxMessage()` reads the receive header timestamp field from the bxCAN receive data-length/timestamp register.
  - Generic HAL support does not override the STM32F405/407/415/417 device erratum.
- Applicability: mechanism/documentation only. This does not prove Terps Racing uses STM32 HAL, which receive path it uses, when it timestamps software reception, or how long a frame can remain queued before processing.

## Formula SAE source boundary

- Formula SAE Online, Series Resources, accessed 2026-10-04:
  https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx
- Current resource listing shows **2027 Formula SAE Rules V1**.
- TC-02X derives no CAN receive timestamp, queue-latency, signal timeout, sample-rate, or torque threshold from that ruleset.

## Repository sources this pass connects

On `research/enme408-tc00-20261001` at inspected head `2c4c8a1cfef0a34064db0362df0b8675a4e3dfc2`:

- `reference/timebase_freshness.py` blob `cfa7bf78644093e06858d6cd40b9c434b9095756` requires a valid common timestamp domain before age subtraction.
- `reference/comms_observer.py` blob `e9047958671924dbd1abccedc1e2f8f794eb38aa` treats non-fresh critical signals as communication faults but intentionally does not define how reception timestamps are obtained.
- `reference/team-interface-request.example.json` blob `915068c5cfec98e17b8a913c5c90a7fcee41106b` asks for producer sample period, consumer timeout, timestamp domain and source reference for each numeric signal.

TC-02X fills the remaining evidence gap: the timestamp itself needs source/capture provenance and a bounded lag from physical reception before it can support a conservative freshness decision.
