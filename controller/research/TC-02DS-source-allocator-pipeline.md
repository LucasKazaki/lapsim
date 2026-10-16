# TC-02DS: Full upstream allocator to bounded fault-state replay

Inspected 2026-10-14. Offline synthetic reference for the proposed 2027–28 Terps Racing EV torque-control project only. This is not firmware, a measured vehicle property, an independent review, or a safety-compliance finding.

## Source-specific dependency closed

The prior TC-02DR replay parity experiment used a minimal `allocator.py` symbol fixture. This pass obtained and independently Git-blob-hashed the **complete, byte-identical upstream allocator**, then exercised the existing source-matched `fault_state.py` against a new, reversible host-only composition: `allocator.replay()` -> proposed `run_bounded_fault_replay()` -> `fault_state.replay_fault_states()`.

At checked draft PR #66 head `dbb9ecef5797288fc79c6e9f8f8a19c46af589e5`:
- `reference/allocator.py`: Git blob `5fb87a9509c69eed4d7160b8a649f7972bb16f02`.
- `reference/fault_state.py`: Git blob `95f676a0bd82726b4fb1ec10144a9ee7662b97af`.

The upstream allocator buffers at most 4097 synthetic inputs and rejects a 4097th sample before invoking any per-sample allocation. The optional fault adapter rejects more than 4096 restart markers, also consuming at most 4097 of them before running the supervisor. That 4096 limit is an offline analysis resource bound, **not** an STM32F405 sample rate, watchdog, CAN, safety, or vehicle limit. A blocking iterator's individual `next()` cannot be timed out by this synchronous adapter.

## Actual portable verification

Linux x86_64, CPython 3.13.5, standard library only:
- `python3 -B -S -m unittest test_bounded_fault_state_replay test_bounded_fault_state_integration test_bounded_fault_pipeline -q`: **38 passed**, exit 0 (**25 predecessor tests, 13 new**).
- New replay parity: 300 deterministic sequences of **actual allocator outputs**, replayed twice; predecessor parity: 200 synthetic supervisor scenarios.
- Tested nominal, saturation, zero request, stale/future signals, unit/sign/interlock/nonfinite faults, restart generation, recovery, strict JSON, 4096 exact boundary, 4097 overflow before actual allocation (asserted with `unittest.mock`), and restart-marker overconsumption.
- Deliberately defective finite negative control drops a restart marker, predictably fails with exit 1.
- Original repository-wide regressions, native runtime, HIL, MCU and vehicle tests **not run**. No local worker ACK, Company Runtime registration, or independent controls-team review verified.

**Decision:** preserve the accepted original allocator and supervisor. The new `bounded_fault_pipeline.py`, its tests, and the previously unsent bounded replay adapter/test files are retained in a source-pinned local handoff, **not installed by publication of this note**. No vehicle command, firmware flashing, scheduler, or unrelated project work performed.

## Primary sources and applicability

- Authorized repository PR #66: https://github.com/LucasKazaki/lucas-agent-studio/pull/66 , source head and Git blobs above.
- Python `itertools.islice` semantics: https://docs.python.org/3.13/library/itertools.html (host-side consumption contract only).
- SAE U.S. Formula SAE Series Resources: https://www.fsaeonline.com/cdsweb/gen/documentresources.aspx (listed 2027 Formula SAE Rules V1 on 2026-10-14; specific competition year/compliance not established).
- ST STM32F405/415 documents: https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html (RM0090 V22.0 dated 2026-05-28; not team board/firmware timing evidence).

Next action: in a clean authorized PR #66 checkout, verify exact source blobs and non-conflicting writer ownership, apply only the five additive reference files from the reproducible handoff, run the 38 focused tests **and existing upstream** `test_allocator.py` / `test_fault_state.py`, then seek independent review. No main merge or hardware use.
