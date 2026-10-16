# TC-02D — wrap-safe 32-bit timestamp-age reference

Status: portable synthetic reference only. Target-car context remains 2027-28. No Terps Racing timebase, CAN message, sample period, timeout, firmware, or hardware behavior is asserted here.

## Decision

A future STM32 firmware port must not translate the existing offline stale-input checks into naïve signed subtraction of wrapping 32-bit timestamps. For a verified common unsigned 32-bit tick domain, compute `(now - sample) mod 2^32` and use the half-range rule:

- delta < 2^31: sample is in the past by `delta` ticks;
- delta > 2^31: sample is future-dated by `2^32 - delta` ticks;
- delta == 2^31: temporal ordering is ambiguous and fails closed.

Any configured maximum accepted age must stay below 2^31 ticks. This rule still requires evidence that the two timestamps share one monotonic timebase and that the timebase cannot pause during the control interval being checked.

## Counterexample

For `sample=0xfffffff0` and `now=0x00000010`, the true modular age is 32 ticks. Plain mathematical subtraction yields `-4294967264`, which can be misclassified as future/invalid or converted incorrectly if a firmware port uses a signed type.

The half-range rule has its own explicit boundary: a separation of exactly `0x80000000` cannot be ordered from endpoint values alone. The reference reports `ambiguous` instead of guessing.

## Primary-source boundary

Inspected STMicroelectronics `stm32f4xx-hal-driver` master commit `1f6451c3e07728b4c830744de380e56bf5bc0026` (accessed 2026-10-01), source blob `862ec732ee46eec100fd2678bb500bcdb5d732c9`.

In `Src/stm32f4xx_hal.c`, the default `HAL_GetTick()` returns `uint32_t`; the default implementation increments `uwTick` from SysTick and documents a 1 ms basis. The same source marks `HAL_GetTick` / tick initialization weak so an application may override the implementation. `HAL_Delay` itself compares elapsed ticks with unsigned subtraction, `HAL_GetTick() - tickstart`. The file also exposes `HAL_SuspendTick()`, which disables the SysTick interrupt in the default implementation.

Therefore the upstream HAL is useful evidence for unsigned wrap behavior, but it does **not** establish that Terps Racing uses the default HAL tick, a 1 ms control timebase, SysTick, or a timebase that is never suspended. Those facts remain TC-00/TC-03 evidence requirements. The upstream HAL component is BSD-3-Clause licensed.

Official Formula SAE resources currently expose a 2027 season and Formula SAE Electric 2027 resource section, but the final rules body was not available through the unauthenticated resource path inspected in this pass. No rule-number or vehicle timeout is derived here.

## Portable reference

`reference/tick_age.py` implements a strict unsigned-32 classifier with statuses `fresh`, `stale`, `future`, and `ambiguous`. It has no physical units and accepts no real vehicle timeout. `max_age_ticks` is a synthetic caller-supplied bound and must be less than half the counter range.

The reference is intentionally separate from `allocator.py`. It is a firmware-porting guardrail, not a claim that the current Python allocator should adopt a 32-bit MCU tick representation.

## Portable verification

Environment: CPython 3.13.5, Linux 6.18.44 x86_64, standard library only.

Commands:

```text
python -S -m unittest -v test_tick_age.py
python -S -m py_compile tick_age.py test_tick_age.py
```

Observed after correcting one test-fixture orientation mistake: **13/13 tests passed**, 0 failed, 0 skipped; `py_compile` exited 0.

Coverage includes nominal fresh/stale samples, wrap crossing, inclusive threshold behavior, future timestamps, exact half-range ambiguity, boundary values, invalid/bool/out-of-range inputs, deterministic replay, and strict JSON serialization.

The initial negative run is retained in the handoff receipt: an “extreme future” test incorrectly used a timestamp whose modular separation was actually a valid past age under the half-range convention. The implementation was unchanged; the fixture was corrected to encode the intended future relation.

## Keep/revert rule

Keep this helper only as a portable reference until the actual firmware timebase is verified. Do not assign millisecond meaning, CAN timeouts, watchdog thresholds, or safety authority from this file.

If the team source shows a different timestamp width, a non-monotonic/suspendable control timebase, multiple unsynchronized clock domains, or a dedicated hardware timer contract, replace this reference with one derived from that evidence rather than adapting it by assumption.

## Next action

Populate the team evidence packet with the actual timestamp source(s), width, frequency, wrap semantics, and whether the control freshness clock can pause. If the real firmware uses a wrapping 32-bit common tick, the next native patch can adapt this half-range contract and add source-specific tests without changing torque allocation or safety policy.
