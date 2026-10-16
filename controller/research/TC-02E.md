# TC-02E — timebase-provenance freshness contract

Status: portable synthetic reference only. Target-car context remains 2027-28. No Terps Racing CAN IDs, sample periods, timeout thresholds, firmware timebase, watchdog policy, or vehicle behavior is asserted here.

## Decision

A freshness/staleness check is valid only when the sample timestamp and the comparison timestamp are proven to come from the same clock domain with compatible width, frequency, monotonicity, and pause behavior.

The current portable contract therefore refuses to subtract raw timestamp values when:

- their timebase domain identifiers differ;
- the tick frequencies differ;
- the clock is not proven monotonic;
- the clock can pause during the interval being judged; or
- the timestamp width/values or maximum-age bound violate the 32-bit half-range contract from TC-02D.

This is deliberately stricter than ordinary integer subtraction. A numerically small difference is not evidence that two timestamps are comparable.

## Counterexample

A raw value of 100 from a hypothetical HAL millisecond tick and a raw value of 110 from a DWT cycle counter look only 10 counts apart. Subtracting them has no defined physical meaning because the counters represent different clock domains and frequencies. The reference reports `timebase_domain_mismatch` and performs no age calculation.

Within one verified unsigned 32-bit clock, wrap handling still uses the TC-02D half-range rule. For example, `sample=0xfffffff0` and `now=0x00000010` is 32 ticks old. A separation of exactly `0x80000000` remains ambiguous and fails closed.

## Primary-source boundary

Inspected STMicroelectronics `stm32f4xx-hal-driver` master commit `1f6451c3e07728b4c830744de380e56bf5bc0026`, source blob `862ec732ee46eec100fd2678bb500bcdb5d732c9` (accessed 2026-10-01). Its default `HAL_GetTick()` returns `uint32_t`, the default implementation is SysTick-based, tick functions are weak/overrideable, and `HAL_SuspendTick()` can stop the default tick interrupt. Upstream license: BSD-3-Clause.

Inspected STMicroelectronics `cmsis-core` release commit `afc5ca6af0a49232fde7eb4548dd0962d119ce14`, `core_cm4.h` blob `770908a619b47e43d9bdbaf909b83a9b917d095b` (accessed 2026-10-01). The Cortex-M4 DWT structure declares `CYCCNT` as a separate `uint32_t` Cycle Count Register. Upstream license: Apache-2.0.

These upstream facts establish candidate mechanisms only. They do **not** establish that Terps Racing uses either source, uses the default HAL tick, runs DWT, shares timestamps across tasks, or has a non-pausable control freshness clock.

Formula SAE Online currently exposes a 2027 season and Formula SAE Electric 2027 competition resource surface. No numbered rule, signal timeout, watchdog interval, or torque-control threshold is derived from it in this pass.

## Portable reference

`reference/timebase_freshness.py` models:

- a `TimebaseSpec` carrying clock-domain provenance;
- a per-signal timestamp sample with caller-supplied synthetic maximum age;
- statuses `fresh`, `stale`, `future`, `ambiguous`, and `invalid_timebase`; and
- a multi-signal snapshot whose synthetic `all_fresh` value is true only when every configured sample is fresh.

The snapshot boolean is suitable only as an offline input to other reference logic such as the existing command guard. It is not a real CAN-health, inverter-enable, watchdog, shutdown, or vehicle-safety decision.

## Portable verification

Environment: CPython 3.13.5, Linux x86_64, standard library only.

Commands:

```text
python -S -m unittest -v test_timebase_freshness.py
python -S -m py_compile timebase_freshness.py test_timebase_freshness.py
```

Observed: **15/15 tests passed**, 0 failed, 0 skipped; `py_compile` exited 0.

Coverage includes nominal fresh/stale classification, inclusive age threshold, wrap crossing, future timestamps, exact half-range ambiguity, cross-domain rejection, same-domain frequency drift, pausable/non-monotonic clocks, malformed timebase objects, invalid counter/threshold values, duplicate labels, non-vacuous empty snapshots, deterministic replay, and strict JSON serialization.

These tests are synthetic host-language evidence. They do not test STM32 execution, ISR/task scheduling, CAN reception timing, oscillator accuracy, HIL behavior, vehicle behavior, or safety compliance.

## Keep/revert rule

Keep this contract only while it remains a provenance/freshness reference with synthetic thresholds. Do not infer a real timeout or accepted timebase from the existence of HAL or DWT upstream.

If the team firmware uses a different counter width, multiple synchronized domains with an explicit conversion contract, a hardware timer, RTOS time, or a clock that legitimately pauses, replace this reference with a source-specific contract backed by the actual firmware.

## Next action

Populate TC-00/team evidence with the real firmware timestamp source(s), width, frequency, ownership, reset/wrap behavior, and whether the freshness clock can pause. Then bind each critical input to one verified timestamp domain and a team-reviewed age requirement before connecting freshness status to any embedded torque command path.
