# TC-02DQ: Bounded offline fault-state replay inputs

Scope: 2027–28 Terps Racing EV torque-control **synthetic reference only**. No MCU, CAN, firmware, shutdown, or vehicle action authorized.

## Source finding (inspected 2026-10-14)

At draft PR #66 head `8641a8bf04199201f204b5fe20be462a26ff2a62`, `reference/fault_state.py` (Git blob `95f676a0bd82726b4fb1ec10144a9ee7662b97af`) constructs `set(restart_before)` and `tuple(results)` without an input-length cap. Large finite iterators can consume excessive offline memory; an infinite iterator can prevent completion. This is an analyst resource limitation, **not a vehicle defect**.

The reference allocator (blob `5fb87a9509c69eed4d7160b8a649f7972bb16f02`) limits offline replay to `MAX_OFFLINE_REPLAY_STEPS = 4096`. The existing `bounded_guard_replay.py` (blob `2d34640ef6d1a0aad3c82408e505cb7d62c90461`) caps both synthetic input streams; the fault-state replay has no corresponding bounded wrapper.

## Proposed additive correction

An isolated `bounded_fault_state_replay.py` adapter consumes up to `cap + 1` elements per iterable, with `cap <= 4096`; detects overflow before delegating; validates restart indices; sorts/deduplicates restart markers to preserve the existing set semantics; and calls the original supervisor once through an explicit callback. This preserves the original function and does not impose any real-time limit. A pathological blocking `next()` or blocking callback cannot be protected by the wrapper.

The associated **unsent code and tests** are in the TC-02DQ local handoff package, pending a reviewed source-specific integration test. Do not assume this document deployed them.

## Verification in standalone Python 3.13.5 / Linux x86-64

- `python3 -B -S -m unittest discover -s . -p 'test_bounded_fault_state_replay.py' -v`: 17/17 pass, exit 0, with 200 seeded deterministic fixtures, explicit overflow and finite-iterator consumption checks.
- A **finite-only** deliberately unbounded implementation accepts six samples against cap five and fails its assertion as intended, exit 1. Do not run that negative control on an infinite iterator.
- Archived TC-02DP predecessor: manifest check and 15/15 portable regression tests passed, exit 0.
- **Not run:** full live repository suite, direct original-`fault_state` import/integration, native worker, STM32F405, HIL, vehicle.

## Handoff gate

Reread PR #66 head, source blobs, comments/reviews, and active writer ownership before adding the portable code and tests under `projects/enme408-torque-control/reference/`. Test parity against real `fault_state.replay_fault_states` on finite synthetic sequences; only then consider this a repository-integrated reference. No source rewrite, forced ref update, automatic merge, runtime registration or hardware actions.

Source index: PR #66 https://github.com/LucasKazaki/lucas-agent-studio/pull/66 ; official U.S. Formula SAE resources https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx (2027 rules V1 displayed 2026-10-14, no target-car compliance conclusion); ST reference manual RM0090 https://www.st.com/resource/en/reference_manual/dm00031020.pdf (peripheral reference, no team timing evidence).

**Next action:** independently validate the additive wrapper on the authorized repository checkout and obtain review of whether the offline 4096-step cap should be shared across the reference replayers.
