# TC-01AD | Bound validity through a held command (offline research)

**Inspected 2026-10-14.** Synthetic hypothetical 2027–28 U.S. Formula SAE Electric torque-control research; not 2026–27 vehicle data, not firmware, and not an authorized vehicle command.

## Decision and counterexample

Keep the previous TC-01AC conditional wheel-speed ceiling as a research reference, but require an externally supplied ceiling to cover the **entire expected command-hold interval**. A ceiling can be valid at the decision instant and expire before the command stops being held.

Frozen example, on a hypothetical monotonic 1,000-tick/s clock: the speed sample is at tick 1000, decision at 1020, upper-speed bound valid for 50 ticks from its sample, and proposed command hold for 40 ticks. Sample age is 20. The incorrect start-only check accepts `20 <= 50`, but the full coverage check rejects `20 + 40 > 50`: the bound expires at tick 1050, command hold ends at 1060. With four *synthetic* channels of 100 N·m, observed speed 20 rad/s, bound 25 rad/s, and 9,000 W **wheel-mechanical** budget, the frozen TC-01AC power screen would produce approximately 90 N·m/channel if called. The proposed TC-01AD wrapper instead returns `bound_invalid` and a four-zero diagnostic result without calling that screen.

The implementation is a **portable, unmerged proposal**, not an accepted ECU fail-safe. Its timestamp validation assumes an externally justified non-pausing monotonic clock, compatible domain and tick frequency, unsigned 32-bit ordering with intervals shorter than 2^31 ticks, explicit sensor-age limit, and a validity lifetime that starts at the speed sample. A matching clock label cannot prove synchronization, and these tests cannot prove a physical wheel-speed ceiling.

## Source pin, current status and reproducibility

GitHub source inspected: draft PR #66, branch `research/enme408-tc00-20261001`, pre-publication head `b3266aa1cce725c02be7ed07f6e79a6dd5f7a7bc`. Published `reference/aggregate_power_budget.py` Git blob `dfc336f099101d71e897374543f3ba8268a39a29` uses a wheel-speed snapshot. Published `reference/timebase_freshness.py` blob `cfa7bf78644093e06858d6cd40b9c434b9095756` implements a related synthetic clock-domain/half-range freshness contract. `research/TC-01AC-speed-interval-power.md` blob `28c97d2ad462be9e0e969d4e24b9ee3e94c401c9` states the conditional speed-ceiling prerequisite.

New isolated Python candidate: `tc01ad_interval_validity.py` SHA-256 `c0cba851e1aba7aef8d7b5cb56ed20a49c7b5631e9396a0efc2e472491ba2bd3`. It depends on the **frozen previous TC-01AC handoff**, whose implementation was not asserted published to GitHub. Portable Linux x86-64, CPython 3.13.5, standard-library verification: `python3 -B -S verify_offline.py`, **43 passed** (23 new + 20 frozen previous), exit 0, and one expected assertion failure in an intentionally defective start-only gate. 400 seeded timing scenarios repeated deterministically. A downloadable handoff artifact holds the reference/tests, frozen predecessor and exact receipts; the code was **not** committed in this note. Full live GitHub suite, independent reviewer, AI-PC worker ACK, Company Runtime registration, STM32F405, HIL, CAN, and vehicle tests: **not verified**.

## Dependency / review gate

TC-00 needs a team-confirmed measurement/command clock, conversion across independent clocks, actual update/hold/latency envelopes, a scientifically justified speed ceiling, its valid-through provenance, and independently owned inverter/shutdown behavior. TC-01 next: reproduce this scenario in an authorized isolated checkout and review against current `timebase_freshness.py`; do not modify already accepted modules or promote the wrapper without independent review. No automation, controller registry, firmware, vehicle, course, spending, or main-merge changes.

Primary documentation checked on 2026-10-14: ST official STM32F405/415 documentation catalog (RM0090 V22.0, 2026-05-28) https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html ; official U.S. SAE Formula SAE resources portal (2027 Formula SAE Rules V1) https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx . No rules-clause compliance or actual hardware timing is inferred.
