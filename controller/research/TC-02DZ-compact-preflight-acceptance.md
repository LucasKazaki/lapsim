# TC-02DZ: consolidated offline replay preflight candidate

Scope: synthetic Python replay for the proposed 2027–28 Terps Racing EV; no firmware, CAN configuration, shutdown-system, HIL, or vehicle authority.

## Decision

The staged TC-02DQ–DV pipeline currently uses multiple optional wrappers for the same offline input-validation boundary. To reduce review/integration dependencies, test one compact adapter importing only the existing source-pinned `allocator.py` and `fault_state.py`, preserving all allocator and fault-state behavior.

The adapter checks exact configuration and policy types *before consuming iterables*. It bounds both sample and restart-marker streams to 4,096 elements (4,097 sentinel reads), checks sample element types and restart indices *before any torque allocation*, deduplicates restart markers, then calls the original allocator and supervisor. The strict-type policy may reject subclasses or duck-typed objects; independent compatibility review remains required. Blocking/side-effecting iterator reads cannot be bounded in wall-clock time.

This is a simpler **alternative** to the staged preflight wrappers, not a new mandatory layer, and intentionally does not absorb the optional TC-02DW–DY trace-integrity proposals.

## Source-pinned test evidence (2026-10-14)

Linux x86-64, CPython 3.13.5, Python standard library. Local selected fixture command: `python3 -B -S -m unittest discover -s . -p 'test_*.py' -q`; exit 0, **164 passed, 0 failed**, comprising 147 staged/original and 17 new tests. `python3 -B -S -m py_compile compact_preflight_replay.py test_compact_preflight_replay.py` exited 0. The new tests include **500 deterministic synthetic parity scenarios** and invalid-input/boundary fixtures.

Counterexample: on one valid sample and restart index 1, the older allocation-first TC-02DS path makes one allocator call before raising; this candidate rejects the invalid index with zero allocator calls. This demonstrates offline validation ordering only, not a vehicle defect.

Verified original Git blobs: allocator `5fb87a9509c69eed4d7160b8a649f7972bb16f02`; supervisor `95f676a0bd82726b4fb1ec10144a9ee7662b97af`. New candidate source SHA-256 `0ac03bf8fde57ff7aef893013a654d4f246ea08da2f7664cece24b65c026ac05`; test SHA-256 `579ac0a381e0ee44030c61bc15d77bf8ce0b5708b4a733893f38fff6a2226fe0`. Inspected PR #66 head: `1d27970815b9ea835df06312ad1078c19d309006`.

Not run: current full repository suite, actual local worker/registration, independent review, MCU build/timing, HIL, bench or vehicle. No existing source is modified.

## Next gated action

In an authorized disjoint checkout, inspect current PR head/writer ownership, compare compact candidate with the staged chain, and select a *single* reviewed integration path. Run the original regression suite and preserve all negative controls. No automatic main merge, firmware flashing, actuation or independent-review claim.

Official ST STM32F405 documentation (RM0090 V22.0 listed 2026-05-28): https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html . Official U.S. Formula SAE document resources (recheck actual competition-year version before compliance claims): https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx .