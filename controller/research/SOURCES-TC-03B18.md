# TC-03B18 sources

Accessed 2026-10-03.

Primary source: STMicroelectronics stm32f4xx-hal-driver at commit
`1f6451c3e07728b4c830744de380e56bf5bc0026`, BSD-3-Clause.

- `Inc/stm32f4xx_hal_can.h`
  blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`
  documents `CAN_RxHeaderTypeDef.Timestamp` as captured at start of frame
  reception when Time Triggered Communication Mode is enabled.
- `Src/stm32f4xx_hal_can.c`
  blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2`
  copies the receive FIFO mailbox timestamp into the Rx header and documents
  FIFO fill-level inspection plus deferred retrieval.
- `LICENSE.md`
  blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`.

ST STM32F405/415 documentation:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html

Formula SAE resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx
Current observed rules resource: `2027 Formula SAE Rules`, Version `V1`.

Existing project sources:
- TC-02E blob `46524a3234ca3b2a7a8620ef5e4c2bd8faa3e021`
- TC-02G blob `a7ef63dc5f201021ebaa4de5a23d69ab3ffb941f`
- TC-03B17 blob `18d695f157dfdcd01f71f68263028ed971476a16`

These sources do not establish the team's message map, TTCM setting, timestamp
assignment point, queueing path, source-sample timing, critical-signal list, or
timeout requirement.
