# TC-02I — bounded evidence-buffer loss accounting

Status: portable synthetic reference only. Target remains the 2027-28 Terps Racing EV torque-control project. This note does not define CAN IDs, bit rate, message periods, logging byte size, RAM allocation, interrupt policy, torque authority, recovery policy, watchdog behavior, or any vehicle acceptance threshold.

## Decision

A future communication/evidence logger should treat **upstream CAN receive loss** and **downstream software logging-buffer loss** as separate evidence classes.

The previous TC-02H record makes raw CAN/timestamp observations replayable, but a real embedded logger will also have finite storage. If the software evidence queue fills, silently overwriting or dropping records would make a later replay look more complete than it was. TC-02I therefore requires any bounded evidence buffer to:

- cap retained record count explicitly;
- make its overflow policy explicit rather than implicit;
- preserve monotonically increasing producer sequence numbers;
- report every software-buffer loss through bounded metadata;
- mark a drained batch incomplete whenever such loss occurred;
- keep CAN/FIFO-overrun evidence inside the record payload rather than conflating it with logging-buffer overflow; and
- refuse sequence gaps/duplicates at the producer boundary instead of inventing continuity.

The portable reference supports two deliberately explicit policies for comparison only: `drop_new` and `overwrite_oldest`. Neither is selected for the vehicle. The eventual policy must be reviewed against actual firmware timing, RAM, interrupt context, logging sink, and diagnostic objectives.

## Primary-source boundary

STMicroelectronics `stm32f4xx-hal-driver` commit `1f6451c3e07728b4c830744de380e56bf5bc0026` was inspected on 2026-10-01. The repository is BSD-3-Clause licensed.

- `Inc/stm32f4xx_hal_can.h` blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d` defines separate Rx FIFO overrun error bits (`HAL_CAN_ERROR_RX_FOV0`, `HAL_CAN_ERROR_RX_FOV1`) and Rx FIFO overrun interrupts.
- `Src/stm32f4xx_hal_can.c` blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2` exposes `HAL_CAN_GetRxFifoFillLevel()` and `HAL_CAN_GetRxMessage()`. Its IRQ handler records FIFO-overrun errors and clears the corresponding hardware overrun flag.

These mechanisms show that receive-side loss can exist independently of any application logging queue. They do **not** prove that Terps Racing uses this HAL, these callbacks, these FIFOs, or any particular interrupt/recovery configuration.

ST's current STM32F405/415 documentation catalogue lists RM0090 V22.0 dated 2026-05-28 and PM0214 V11.0 dated 2025-02-27. The exact team MCU part/package, board, clocks, CAN configuration, and firmware remain unverified.

The current Formula SAE competition site exposes Formula SAE Electric 2027, but this pass does not derive any numbered rule or logging requirement from it.

## Portable prototype

`evidence_buffer.py` is a standard-library, single-threaded host-language reference. It bounds **record count**, not bytes. Payload byte size, allocator overhead, ISR safety, lock-free behavior, WCET, and actual STM32 RAM consumption are explicitly outside this result.

Each append binds an exact producer sequence. When full:

- `drop_new` retains existing records and reports the rejected new sequence;
- `overwrite_oldest` retains the new record and reports the evicted sequence.

Loss metadata is constant-shape (`count`, first sequence, last sequence, reason) rather than one metadata object per dropped record. This prevents the loss-reporting mechanism itself from becoming an unbounded list in the portable model.

A drain preserves capture/source identity, configured capacity and policy, next expected sequence, high-water mark, retained records, and the software-loss summary. `complete` is false whenever software-buffer loss occurred.

## Portable verification

Environment: CPython 3.13.5, Linux 6.18.44 x86_64, standard library only.

Commands:

```text
python -S -m unittest -v test_evidence_buffer.py
python -S -m py_compile evidence_buffer.py test_evidence_buffer.py
```

Observed: **17/17 tests passed**, 0 failed, 0 skipped; `py_compile` exited 0.

Coverage includes lossless drain, both overflow policies, exact loss accounting, 10,000-append bounded-record stress, constant-shape loss metadata, sequence-gap/duplicate rejection, strict-JSON rejection of NaN/bytes, payload copy isolation, drain/reset behavior, empty drains, deterministic canonical JSON, invalid capacity/policy/source revision, tampered completeness/loss reasons, out-of-order record rejection, and separation of CAN-overrun evidence from software-buffer overflow.

Local SHA-256:

- `evidence_buffer.py`: `9d3fd92a73d75daa8cf735318617714e85ac01d9c4381ae5141f7b6a65562923`
- `test_evidence_buffer.py`: `56eb2cdd2a570786792634914309c42832a1eeb5556cd7f2a41e673159b606f1`

This is synthetic host-language evidence only. It does not establish firmware timing, RAM suitability, ISR safety, CAN behavior, or vehicle safety.

## Keep/revert rule

Keep this contract only while logging loss remains explicit and separate from vehicle-control authority. Rework or reject an implementation that:

1. silently drops or overwrites evidence without a retained loss indicator;
2. treats software logging overflow as equivalent to CAN FIFO overrun, or vice versa;
3. allocates a record capacity from guessed STM32 memory availability;
4. claims a Python record-count bound is a byte/RAM/WCET proof; or
5. makes torque, recovery, reset, watchdog, or shutdown decisions from this logger without reviewed team requirements.

## Next useful action

TC-03B remains blocked on the TC-03A team evidence packet. Once the untouched firmware build is reproduced, inspect the actual logging and receive contexts. Then determine whether a bounded evidence queue is needed at all, and if so measure record size, producer rate, drain rate, execution context, worst observed occupancy, and overflow behavior on the real source revision before selecting a capacity or overflow policy.
