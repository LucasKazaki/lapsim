# TC-02A - deterministic fault-state and logging reference

Status: portable synthetic reference only. Parent research branch: `research/enme408-tc00-20261001`. Target car context remains 2027-28; no Terps Racing CAN, sensor, motor, inverter, calibration, watchdog, firmware, HIL, or vehicle behavior is asserted here.

## Decision

Add a small supervisory fault-state model around allocator results before attempting embedded timing or CAN integration. The model keeps four states: `ready`, `limited`, `inhibited`, and `recovery_pending`.

- `ready`: allocator result is valid and unconstrained.
- `limited`: allocator reported aggregate saturation. The reference treats this as a constrained operating condition rather than an input-validity failure.
- `inhibited`: allocator reported a fault, or the supervisor received a malformed/non-finite allocator result.
- `recovery_pending`: after an inhibit or synthetic restart, only consecutive `ok` allocator samples advance recovery. Saturated samples do not count toward recovery.

The reference policy uses `valid_samples_to_recover=2` only to exercise transition logic. This is a dimensionless synthetic replay count, not a time interval, debounce requirement, watchdog setting, CAN timeout, or Terps Racing requirement. Real recovery behavior must come from team safety/interface requirements and review.

The model deliberately does not modify allocator output. It emits a simulation-only indication and a structured event record so recovery behavior can be tested before any firmware implementation. It does not replace independent vehicle safety functions or team-approved firmware logic.

## Restart and recovery behavior

A synthetic restart increments an event `generation` and clears the supervisor's recovery streak. It does not clear an active allocator fault. If the first post-restart sample is healthy, the state re-enters through `recovery_pending` and must satisfy the configured synthetic valid-sample count before returning to `ready`.

This gives a portable test for the property we care about now: a process restart must not turn a still-invalid input into an immediately healthy state. It does not prescribe actual MCU reset handling, boot sequencing, or inverter enable logic.

## Event/logging schema

Each event record contains only finite JSON-safe values:

- monotonic replay `sequence`
- synthetic restart `generation`
- `restart_requested`
- `previous_state` and `next_state`
- allocator `status` and `fault`
- requested/delivered torque and four output values
- current recovery streak
- simulation-only reference indication
- transition `reason`

Malformed allocator results, unknown status strings, non-finite values, output-sum inconsistency, nonzero outputs while allocator status is `fault`, or negative outputs are classified as `invalid_allocator_result` and enter `inhibited`. Logs replace non-finite numerical payloads with zero after classifying the record invalid so strict JSON serialization can use `allow_nan=False`.

## Embedded-research boundary

ST's current STM32F405/415 documentation page lists RM0090 V22.0 dated 2026-05-28 and ES0182 V19.0 dated 2026-07-19. RM0090 is the current family reference for later CAN/watchdog implementation research. The STM32F405/415 product page confirms up to two CAN 2.0B interfaces and a 168 MHz Cortex-M4/FPU family baseline. None of this identifies the exact Terps Racing part/package, clock tree, transceiver, CAN topology, watchdog configuration, or firmware ownership.

SAE's official Formula SAE news page shows `Important Updates for the 2027 Formula SAE Season` on 2026-09-15 and states that the 2027 rules were published. The current rules body still was not retrieved in this pass, so this work makes no 2027 rule-number or compliance claim.

## Portable verification

Environment: Python 3.13.5, Linux 6.18.44 x86_64, standard library only.

Commands:

```text
python -m unittest -v test_allocator.py test_fault_state.py
python -m py_compile allocator.py fault_state.py test_allocator.py test_fault_state.py
```

Observed for the branch-compatible TC-01A + TC-02A subset: 27/27 tests passed, 0 failed, 0 skipped; `py_compile` exited 0. This includes 14 existing TC-01A allocator tests and 13 new TC-02A state/logging tests. The previously prepared TC-01B replay package was also regression-tested locally in the broader 40-test sandbox, but it remains a separate unsent artifact and is not treated as branch evidence here.

TC-02A coverage includes nominal ready state, aggregate saturation as limited state, immediate inhibit on allocator fault, configured recovery streak, saturation during recovery, persistent fault across synthetic restart, healthy restart recovery path, deterministic replay, strict JSON event serialization, malformed/non-finite allocator results, unknown allocator status, invalid policy, and invalid restart indexes.

These tests do not measure STM32 execution time, CAN traffic/error behavior, watchdog timing, task scheduling, motor/inverter response, HIL behavior, track behavior, or vehicle safety.

## Keep/revert rule

Keep this layer only while it remains an isolated, deterministic reference and all real timing/recovery values stay explicitly unverified. Split or revert changes that encode real watchdog timeouts, CAN error recovery, actuator enable logic, safety authority, or team-specific interfaces without authorized evidence and review.

## Next bounded task

TC-02B: add an embedded-feasibility measurement plan and portable instrumentation contract. Define what the team/local implementer must measure on the actual STM32F405 firmware (cycle time, worst-case execution time, stack/RAM, CAN receive age/error state, reset cause and log retention) without inventing thresholds. Keep real watchdog/CAN/recovery policy pending the exact PCB, firmware, and team requirements.
