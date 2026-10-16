# TC-02H - replayable communication evidence log

Status: portable synthetic reference only. Target remains the 2027-28 Terps Racing EV torque-control project. This note does not define CAN IDs, bitrate, signal periods, timeout thresholds, recovery behavior, torque authority, watchdog policy, or shutdown behavior.

## Decision

For future communication-fault investigation, retain **raw normalized evidence and derived classifications together**, and make the derived fields reproducible from the raw fields.

A useful record contains:

- exact producer/source revision and a capture identifier;
- contiguous sequence number;
- controller observations such as error-warning, error-passive, bus-off, and receive-FIFO overrun;
- raw timestamp evidence for each critical decoded signal, including its timebase provenance;
- decode/unit/sign validity;
- derived freshness; and
- derived communication-health status and reasons.

The portable reference recomputes freshness and communication health when a record is read. If stored derived fields no longer match the raw evidence, the record is rejected. A trace also rejects sequence gaps, duplicates, reordering, capture changes, or source-revision changes.

This is an evidence-integrity layer. It does not convert `degraded` or `fault` into actuator, derating, shutdown, watchdog, or recovery authority.

## Primary-source implication: capture before reset/recovery

Current ST STM32F4 HAL source was inspected at commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (accessed 2026-10-01).

- `Inc/stm32f4xx_hal_can.h` blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d` defines the CAN error categories used by TC-02G and exposes `HAL_CAN_GetError`, `HAL_CAN_ResetError`, and `HAL_CAN_ErrorCallback`.
- `Src/stm32f4xx_hal_can.c` blob `9278c96e1883ea0909c0c10754fed68b41ca0ef2` shows `HAL_CAN_GetError` returning the handle's current `ErrorCode`. `HAL_CAN_ResetError` clears that code when the HAL state is READY or LISTENING, otherwise it returns HAL_ERROR after recording a not-initialized error. The default error callback is weak and intended to be implemented by the user when needed.
- `CAN_InitTypeDef` includes an `AutoBusOff` configuration field. Whether it is enabled on Terps Racing hardware is unknown.

Therefore, if the eventual team firmware uses this HAL and ever clears the HAL error code or performs bus recovery, evidence intended for later replay should be captured **before** that destructive state change. This is a logging-order requirement only; it is not a recommendation to call `HAL_CAN_ResetError`, enable/disable automatic bus-off management, or implement any recovery action.

The upstream repository license is BSD-3-Clause. These sources describe available STM32F4 HAL mechanisms; they do not prove that the team's firmware uses HAL or establish its recovery policy.

Formula SAE's official news page states on 2026-09-15 that important 2027-season updates were published. The final rule body was not retrieved for this pass, so no numbered rule or competition threshold is encoded here.

## Portable prototype

A standard-library Python prototype, `comms_evidence_log.py`, was tested with a 16-test regression suite against compatibility copies of the published TC-02E/TC-02G APIs.

Exact commands:

```
python -S -m unittest -v test_comms_evidence_log.py
python -S -m py_compile timebase_freshness.py comms_observer.py comms_evidence_log.py test_comms_evidence_log.py
```

Observed: **16/16 tests passed**, 0 failed, 0 skipped; `py_compile` exited 0.

Coverage includes nominal round-trip, deterministic JSON, stale-input recomputation, bus-off and warning observations, cross-timebase faults, tampered derived-health/freshness detection, raw-timestamp tamper detection, signal/timestamp label mismatch, strict schema keys, exact source-revision syntax, contiguous traces, gap/duplicate/reorder rejection, capture/revision drift rejection, and strict boolean inputs.

Local SHA-256:

- `comms_evidence_log.py`: `a73299937b8022456b0f2e0d804a2c834e736a75f732be0bbca0cb833182cbc1`
- `test_comms_evidence_log.py`: `25ce60eac3490869024351290e732aee8beacbf90999784994c92006debeb595`

The compatibility copies used by the isolated portable run are API-compatible test fixtures, not byte-identical evidence for the branch's existing `timebase_freshness.py` and `comms_observer.py`. The result therefore proves the portable contract and counterexamples, not branch CI or native firmware behavior.

## Keep/revert rule

Keep this design only while the log remains evidence-only and deterministic. Revert or split any change that:

1. logs only a derived health label while discarding the raw observations needed to reproduce it;
2. clears/reinitializes communication error state before the evidence capture point without a separate retained pre-clear record;
3. silently accepts sequence gaps or source-revision changes as a complete trace; or
4. turns logging output directly into vehicle recovery or torque authority without reviewed team requirements.

## Next dependency-ready action

The next source-specific step still requires the TC-03A team evidence packet. After the untouched firmware build is reproduced, identify the actual CAN receive/error path and answer four bounded questions before adapting this schema:

1. Which error state is observable, and where?
2. Can any handler clear or overwrite that state before it is logged?
3. What clock domain timestamps received data and log records?
4. Where can a bounded record be emitted without altering control timing or safety ownership?

If the real architecture differs from the STM32 HAL model, adapt or discard this reference rather than forcing the firmware into it.
