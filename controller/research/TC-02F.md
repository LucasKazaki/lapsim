# TC-02F — supervisor input-integrity hardening

Status: portable synthetic reference only. No STM32, CAN, HIL, dynamometer, track, or vehicle execution.

## Counterexample

The unpublished TC-02A supervisor called `math.isfinite()` directly on allocator fields. A malformed nonnumeric wheel value such as `(1.0, "bad", 1.0, 1.0)` raised `TypeError` before the supervisor could classify the input invalid.

Observed pre-fix reproducer: exit code 1, `TypeError: must be real number, not str`.

## Change

The reference supervisor now:

- validates numeric allocator fields before finite arithmetic and rejects booleans as numeric values;
- requires allocator fault code to be `str | None`;
- classifies malformed allocator payloads invalid before sanitizing them to strict-JSON-safe finite values;
- rejects malformed `FaultSnapshot` state/counters; and
- rejects malformed sequence/restart metadata.

The synthetic recovery count remains a replay fixture, not a Terps Racing requirement or timing threshold.

## Portable verification

Environment: Python 3.13.5, Linux x86_64, standard library only.

```text
python -m unittest -v test_allocator.py test_command_guard.py test_fault_state.py
python -m py_compile allocator.py command_guard.py fault_state.py test_allocator.py test_command_guard.py test_fault_state.py
```

Observed against the published-equivalent portable files: **48/48 tests passed**, 0 failed, 0 skipped; `py_compile` exited 0.

The 48 tests comprise 14 allocator tests, 16 command-guard tests and 18 supervisor tests. This is portable logic evidence only, not branch CI, firmware timing, bus behavior or vehicle validation.

## Current source boundary

ST's current STM32F405/415 documentation page lists RM0090, PM0214 and ES0182 for the family. The page currently identifies PM0214 V11.0 dated 2025-02-27. PM0214 describes Cortex-M4 core peripherals; RM0090 documents watchdog peripherals. These do not identify the Terps Racing package, clock tree, watchdog configuration, CAN topology, firmware ownership, or acceptance thresholds.

Formula SAE's official resource system exposes the 2027 season / Formula SAE Electric 2027 surface. No numbered 2027 rule or compliance threshold is encoded here without the final rules body.

## Keep/revert rule

Keep this layer only as an isolated deterministic reference. Do not convert these replay states into real actuator-enable, shutdown, watchdog, reset or CAN-recovery authority without exact team firmware/interface evidence and review.

## Next action

TC-02B: define a measurement/instrumentation contract for real firmware receipts covering cycle time/WCET, stack/RAM, CAN receive age/error state, reset cause and log retention, with no invented numeric thresholds.
