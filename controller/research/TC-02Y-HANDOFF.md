# TC-02Y handoff

Portable research only; no firmware, hardware, scheduling, or vehicle action.

Source: STMicroelectronics stm32f4xx-hal-driver commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (2026-06-05).

Finding: the STM32F4 HAL CAN IRQ path records FIFO overrun in `hcan->ErrorCode` while clearing the peripheral overrun flag. `HAL_CAN_ResetError()` later clears that software latch. A cleared raw FOVR bit therefore does not by itself prove an overrun-free receive window.

Decision: treat FIFO overrun as continuity-compromising evidence. Do not infer exact lost-frame count or identity from the sticky bit, and do not treat a later fresh frame as proof that continuity was restored.

Portable reference and tests are retained in the external TC-02Y handoff. They passed 33/33 tests under Python 3.13.5. No vehicle authority is encoded.
