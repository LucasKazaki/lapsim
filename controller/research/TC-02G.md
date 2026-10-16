# TC-02G - CAN observation health classification

Status: portable synthetic reference only. Target remains the 2027-28 Terps Racing EV torque-control project. No real CAN ID, bitrate, signal period, timeout, motor/inverter interface, recovery policy, or vehicle threshold is asserted here.

## Decision

Keep controller-level CAN evidence separate from decoded-signal evidence before either is connected to torque-command logic.

The reference `comms_observer.py` normalizes two evidence layers:

1. controller observations: error-warning, error-passive, bus-off, RX FIFO0 overrun, and RX FIFO1 overrun;
2. decoded critical-input observations: freshness, decode validity, unit validity, and sign validity.

It returns `nominal`, `degraded`, or `fault`.

- Bus-off, receive FIFO overrun, any non-fresh critical signal, decode failure, unit mismatch, sign mismatch, or absence of critical-signal evidence yields `fault`.
- Error-warning or error-passive yields `degraded` only when no stronger fault is present.
- `nominal` requires no recorded controller warning/fault and all supplied critical signals to be fresh and valid.

The `degraded` category is observational. It does **not** authorize torque, prescribe derating, or define recovery. Team safety/interface requirements must decide what those controller states mean for the real vehicle.

## Why this is separate from the existing command guard

The portable command guard currently receives one abstract `critical_comms_ok` boolean. Replacing that boolean with a richer source-specific policy now would silently invent vehicle behavior.

TC-02G therefore stops at evidence classification. It can later supply deterministic fixtures to a reviewed policy layer after the actual firmware, CAN map, signal ownership, error handling, and safety requirements are known.

## Primary-source boundary

The current ST STM32F4 HAL driver head inspected for this pass is commit `1f6451c3e07728b4c830744de380e56bf5bc0026`, dated 2026-06-05. In `Inc/stm32f4xx_hal_can.h`, Git blob `b4c229b209c494669ce05cdef1d4e62ad8c9079d`, ST defines CAN error categories including:

- `HAL_CAN_ERROR_EWG`: protocol error warning;
- `HAL_CAN_ERROR_EPV`: error passive;
- `HAL_CAN_ERROR_BOF`: bus-off;
- `HAL_CAN_ERROR_RX_FOV0` and `HAL_CAN_ERROR_RX_FOV1`: receive FIFO overrun.

The same header also exposes error-warning, error-passive, bus-off and receive-overrun interrupt/flag concepts. The repository is the STM32CubeF4 HAL/LL component and is BSD-3-Clause licensed.

This source taxonomy shows mechanisms that may exist when the team's firmware uses this HAL. It does not prove that Terps Racing uses STM32 HAL, which CAN instance is active, how errors are recovered, or which states should inhibit/derate torque.

ST's current STM32F405/415 documentation catalogue lists RM0090 V22.0 dated 2026-05-28 and PM0214 V11.0 dated 2025-02-27. The family documentation does not identify the team's PCB wiring, transceiver, clocks, firmware, filters, message map, or error policy.

Official Formula SAE resources expose the 2027 season / Formula SAE Electric 2027 surfaces and the September 2026 announcement that 2027 rules were published. The final rule body was not retrieved for this pass, so no numbered rule or compliance threshold is encoded here.

Access date: 2026-10-01.

## Portable verification

A standard-library Python regression suite was run against the reference design:

    python -S -m unittest -v test_comms_observer.py
    python -S -m py_compile timebase_freshness.py comms_observer.py test_comms_observer.py

Observed: **16/16 tests passed**, 0 failed, 0 skipped; `py_compile` exited 0.

Coverage includes nominal health; warning/passive degradation; bus-off and FIFO-overrun faults; stale/future/ambiguous/invalid-timebase signal faults; independent decode/unit/sign failures; fault precedence; missing critical-signal evidence; duplicate labels; strict boolean validation; freshness-label mismatch; unsupported freshness states; deterministic reason ordering; and strict JSON serialization.

The local compatibility copy of `timebase_freshness.py` used by this isolated test preserves the published FreshnessResult API but is not represented as byte-identical branch evidence. The branch's authoritative freshness implementation remains its existing `reference/timebase_freshness.py`.

These are host-language synthetic tests only. No STM32 build/run, CAN traffic, HIL, dyno, track, firmware flash, or vehicle action occurred.

## Keep/revert rule

Keep this layer only while it remains observation-only and deterministic. Revert or split any change that turns `degraded` or `fault` directly into real actuator, shutdown, watchdog, bus-recovery or torque-derating authority without exact team evidence and review.

## Next dependency-ready action

TC-03B remains blocked on the actual TC-03A evidence packet: exact firmware revision and build command, STM32F405 part/package and board revision, clock configuration, CAN/message-map source, control-path files, watchdog/reset ownership, and logging path.

Once that packet is complete, reproduce the untouched firmware build first. Then identify the actual receive/error/timestamp APIs in the bound source and either map this observation contract to them or discard it if the team architecture differs. No firmware flashing is authorized.
