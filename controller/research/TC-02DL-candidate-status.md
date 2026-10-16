# TC-02DL: malformed allocator-status input in offline guard

Scope: 2027-28 Terps Racing EV torque-control research; CPython reference only. No firmware, MCU, CAN interface or safety-system behavior was evaluated. The 2026-27 team build is outside this experiment.

## Decision / counterexample
At parent commit `8daab1c762b2d7d021b3473cb6c3a5c2dbab98f2`, `apply_command_guard()` performed set membership on `candidate.status` without a type check. A status supplied as a list, dict, set or bytearray can raise `TypeError: unhashable type`. Dataclass annotations do not enforce input types. This is relevant to replay of malformed synthetic records, not a demonstrated vehicle failure.

Validate `isinstance(candidate.status, str)` before checking membership in the existing `{"ok", "saturated", "fault"}` vocabulary. Malformed statuses now inhibit with zero output and `invalid_candidate_status`; existing valid strings and fault precedence stay unchanged.

## Evidence and source index
- Repository source: `8daab1c762b2d7d021b3473cb6c3a5c2dbab98f2`, `projects/enme408-torque-control/reference/command_guard.py` (original Git blob `51839ad573acb276b066086e2b4b8d9818d1607d`).
- Python 3.13 language reference, set/hashability: https://docs.python.org/3.13/library/stdtypes.html#set-types-set-frozenset . Python source semantics only, not a vehicle or regulatory requirement.
- Explicit hypothetical controls: 100 N*m/s per-wheel rise, 0.05 s sample, zero initial output. Not measured parameters for any Terps Racing car.

## Portable test receipt (Linux x86-64, CPython 3.13.5, standard library)
Run from `projects/enme408-torque-control/reference`:
- Pre-fix: `python -B -S -m unittest test_tc02dl_candidate_status_domain -v`: exit 1; 5 test methods, 7 expected TypeError subtest errors.
- Post-fix: same command: exit 0; 5/5 methods passed.
- Selected packaged reference regression: `python -B -S -m unittest discover -s . -p 'test_*.py' -v`: exit 0; 116/116 passed.
The packaged suite came from the prior TC-02DK reproducible archive, with SHA of the pre-fix remote `command_guard.py` verified. This is not a complete live repository or independent worker test.

## Review gates and backlog
- Independently inspect reason compatibility with downstream replay/logging and whether subclasses of `str` are supported.
- Run complete reference tests from a fresh current Git checkout, and retain a review/CI receipt before moving draft PR #66 forward.
- Keep TC-02DI/DJ alternate latch-recovery policy experimental until independent team approval; do not combine policy changes with this type-validation fix.
- TC-00 motor/inverter count, CAN units/signs, watchdog/shutdown ownership and firmware timing are unknown pending authorized team evidence. No local Company Runtime registration/worker ACK was observed.
- No scheduler, firmware, vehicle, publication, submission, safety-system or unrelated changes are authorized.
