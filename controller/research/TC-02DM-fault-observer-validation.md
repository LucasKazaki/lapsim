# TC-02DM: malformed allocator observations in the offline fault supervisor

**Target:** 2027–28 research reference, not the 2026–27 car firmware. **Status:** candidate for independent review in draft PR #66, not an approved vehicle requirement.

## Decision and counterexamples

The Python reference `fault_state.py` previously accepted non-string status objects at a set-membership boundary, converted arbitrary-sized Python integers directly to floats, and reconstructed invalid wheel vectors without checking their shape. Synthetic input could raise `TypeError` or `OverflowError`, generate non-serializable logs, or let a custom object compare equal to `"ok"`.

The proposed reference-only boundary requires the ordinary `AllocationResult` dataclass, an ordinary string status in `ok/saturated/fault`, and a four-element list/tuple of finite numerical torque values. Wrong shapes or types inhibit with `invalid_allocator_result`. It converts invalid log numerics to finite 0.0, preserving a four-element wheel log, and records synthetic status sentinels `invalid_type` or `invalid_status`. Malformed snapshot state raises the previously documented `ValueError`.

**Policy left unchanged:** existing two-consecutive-clean-sample recovery. This work does not alter the separate experimental pedal-latch recovery comparator, independent shutdown ownership, or vehicle outputs. Sentinel compatibility with downstream logging and whether equality should accept nonexact dataclass subclasses require review.

## Reproduction and evidence

Parent revision: `f910672a5872472f947ea1cf0649f3a4865a1b94`. Original source Git blob `77dd8277c9f7d991653868ae2f6c089cc2fbb31b`. Candidate source blob `5d1ba08826cb38d1142383258d017765f4ea23a5`. New targeted test blob `a1ac57417e0b81c1d68dcc618a5cb20c53a41802`.

Packaged Linux x86-64 CPython 3.13.5 standard-library-only commands (executed 2026-10-12):
```sh
cd TC-02DM
sha256sum -c MANIFEST.sha256
python3 -B -S verify_offline.py
python3 -B -S reproduce_negative.py
```
All three commands exited 0. The selected packaged suite passed **142/142 unittest methods** (8 new targeted). The negative-control original implementation generated **3 expected assertion failures and 12 expected errors** in the 8 target methods; the negative-control wrapper exited 0 because those defects were reproduced. This is **not** a complete fresh-checkout repository test run. Source files and raw logs are in the versioned TC-02DM handoff archive retained outside GitHub. Do not present these synthetic tests as MCU/HIL/vehicle measurements.

## Source index (checked 2026-10-12)

- Python 3.13 `json` documentation, https://docs.python.org/3.13/library/json.html : `allow_nan=False` rejects NaN/Infinity in strict encoding. Used for synthetic logging regression assertions, not CAN log format approval.
- Python 3.13 `dataclasses` documentation, https://docs.python.org/3.13/library/dataclasses.html : field annotations alone are not runtime validation. Applicable to offline replay records only.
- Primary repository baseline: `projects/enme408-torque-control/reference/fault_state.py` at parent SHA above. The defect and fix follow from direct reference source analysis and executed counterexamples, not public literature about vehicle fault safety.

## Next dependency-ready task

An independent reviewer should inspect sentinel compatibility and downstream log consumers, then run the full reference and repository suite from a clean checkout. Check for concurrent branch writes before applying any subsequent revision. The real team's CAN IDs/units, inverter count, torque and speed limits, STM32F405 timing, watchdog/shutdown ownership, and native Company Runtime registration/worker ACK remain **unverified**. No driverless work, firmware flash, track test, deployment, merge or course submission is authorized.

**Backlog:** TC-00 verified interface receipts (blocked by team evidence) → TC-01 offline baseline acceptance → TC-02 logging consumer compatibility and independent review (next) → TC-03 team-reviewed bench packet (blocked by interfaces and reviews).
