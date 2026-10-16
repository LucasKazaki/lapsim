# TC-02EC: Contain synthetic timestamp-rate conversion overflow

**Context:** ENME408 / proposed 2027–28 U.S. Formula SAE Electric torque-control offline reference. This is a research and patch handoff, not deployed firmware or a verified vehicle safety control. No local worker ACK, source merge or STM32F405 timing evidence.

## Reproduced source-specific failure

At inspected draft PR #66 head `8eb0a921df526c7ef2b3480d3d601b70d0c0190d`, `projects/enme408-torque-control/reference/timebase_freshness.py` is Git blob `cfa7bf78644093e06858d6cd40b9c434b9095756`. Its `_validate_timebase` calls `float(spec.ticks_per_second)` outside an exception handler. A synthetic `TimebaseSpec('synthetic-clock',32,10**400,True,False)` produces `OverflowError: int too large to convert to float` (unmodified source negative-control process exit 1), rather than the existing `invalid_tick_frequency` reason. This does not imply an MCU can report that frequency.

Python 3.13 explicitly documents `OverflowError` for integers outside floating-point range: https://docs.python.org/3.13/library/functions.html#float (checked 2026-10-14).

## Proposed minimal candidate and regression evidence

Convert `ticks_per_second` once in `_validate_timebase` under `except (OverflowError, TypeError, ValueError)`, then check `math.isfinite` and positivity. Return existing `invalid_tick_frequency` for values that cannot be represented, retaining distinct `sample_` and `now_` reasons. Neither add a guessed physical upper frequency limit nor change timestamp wrap/half-range logic.

**Two reviewed candidate paths only:**
- Modify `projects/enme408-torque-control/reference/timebase_freshness.py`.
- Add `projects/enme408-torque-control/reference/test_tc02ec_frequency_overflow.py`.

The new test covers sample/now huge positive/negative integers, nonfinite/nonpositive/nonnumeric rates, normal finite rates, strict-JSON snapshot output, wrap and half-range invariants, and 300 seeded cases. A separate test checks 500 deterministic convertible-rate parity cases against the original source.

Actual bounded offline receipts, Linux x86-64 / CPython 3.13.5 / standard library only, 2026-10-14:

- Original unmodified negative fixture: **exit 1 expected**, `OverflowError` reproduced.
- New focused candidate tests against original source: **17 passed / 0 failed**, exit 0.
- Integrated source-pinned prior optional TC-02EB/TC-02EA regressions plus new tests: **77 passed / 0 failed**, exit 0.
- Independent original-versus-candidate parity: **2 passed / 0 failed**, exit 0. **79 distinct passing methods** across the integrated+parity suites.
- `git apply --check`, isolated application and new tests: exit 0 against both the **original** `cfa7bf...` blob and the separately **unpublished TC-02EB** bounded-snapshot blob `00a1c921...`; candidate outputs matched expected SHA-256.

Incremental patch SHA-256: `1b80aa9ce1dd6742a2ce8eb5a4011d2c87b2d7b93ec41ce4a10d221a708ca86c`.

Portable handoff archive SHA-256: `17df0a1ea69d0fff081bca2beed2148360ddba99dc50fef4c2c28554e49af1a4`. This archive and patch are retained externally for the authorized implementer; **this GitHub commit publishes documentation only**.

## Source applicability and stop conditions

- Original code and tests: private repository source blobs as stated; current published PR code was not modified.
- Official Python float documentation: https://docs.python.org/3.13/library/functions.html#float , checked 2026-10-14.
- ST STM32F405 documentation: https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html , checked 2026-10-14, RM0090 V22 dated 2026-05-28. This establishes *only* a future MCU-primary-source starting point; not a source for this host exception or team configuration. No FSAE rule compliance conclusion is made.

**Gate:** independent review accepts numeric-error classification, then authorized implementer checks fresh branch head, exact Git blob, file ownership and existing test filename, applies the two-path patch only in a disjoint worktree, and runs the full relevant checkout tests. Stop on source mismatch, concurrent writes, or changed accepted behavior. Ordinary research jobs must not register Company Runtime projects or schedule a second worker. No main merge, external communications, firmware flashing, bench/vehicle action, or assignment submission.

**Not established:** full current repository test run, independent review, Company Runtime registration/ACK, MCU timing, CAN/inverter signals, hardware-in-loop or track validation.
