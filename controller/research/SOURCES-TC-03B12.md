# TC-03B12 source delta

Accessed 2026-10-02.

Primary sources:

- STMicroelectronics, STM32F405OE product page:
  https://www.st.com/en/microcontrollers-microprocessors/stm32f405oe.html
  Claims used: STM32F405 family up to 168 MHz; 4–26 MHz crystal oscillator; internal 16 MHz factory-trimmed RC summarized as 1% accuracy.
  Applicability: family summary only. It is not a board-level clock tolerance receipt.

- STMicroelectronics, STM32F405xx/STM32F407xx datasheet DS8626 Rev 12, March 2026:
  https://www.st.com/resource/en/datasheet/stm32f405rg.pdf
  Directly inspected in this pass:
  - cover/page 1: current revision and family clock summary;
  - PDF page 104 / document page 105, Table 34: HSI accuracy ranges of -8/+4.5% over -40 to 105 °C, -4/+4% over -10 to 85 °C, and -1/+1% at 25 °C with the stated factory-calibration condition;
  - PDF page 103 / document page 104: external-crystal discussion directs designers to the resonator manufacturer for frequency/package/accuracy characteristics.
  Applicability: MCU oscillator characterization. It does not identify the Terps Racing oscillator source or operating envelope.

- STMicroelectronics documentation catalogue for STM32F4:
  RM0090 version 22.0, latest update 29 May 2026.
  Used only to pin the current reference-manual revision for later source-specific clock-tree work.

- Formula SAE Online news/resources:
  https://www.fsaeonline.com/cdsweb/app/news.aspx
  Current site shows 2027-season resources/news. No numbered Formula SAE rule or timing threshold is claimed in TC-03B12 because the final rules body is not needed for this clock-uncertainty calculation.

No source in this packet establishes the Terps Racing oscillator/crystal part, HSI/HSE selection, trim/calibration, PLL error, operating temperature/voltage range, timebase accuracy, synchronization between clock domains, or any vehicle timeout/persistence threshold.
