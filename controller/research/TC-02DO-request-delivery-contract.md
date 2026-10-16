# TC-02DO: Offline fault observer request–delivery consistency

**Scope:** 2027–28 Terps Racing EV research reference only; no vehicle controller or approved firmware limits.

## Finding

At parent 61e3b954b403437ea08a632b73a9b003304b7d66, `reference/allocator.py` declares a nonnegative propulsive torque request. Its nonfault allocation produces delivered torque no greater than requested. Yet `reference/fault_state.py` accepted synthetic `AllocationResult((10.,)*4, 10., 40., "ok", None)` as `ready` with `reference_gate_allowed=True`. Negative requests with `ok/saturated` and zero requests with tiny positive delivery also bypassed that consistency check. This is a software replay invariant, not a demonstrated vehicle failure.

## Proposed bounded correction

For `ok` or `saturated` records: require nonnegative `requested_nm`, `delivered_nm <= requested_nm + 1e-9` N·m, and zero delivered torque when the request is exactly zero. Violations become inhibited `invalid_allocator_result` observations. Retain legitimate `fault` records for unsupported negative requests so `negative_request_unsupported` provenance is not lost. Preserve existing sum tolerance, two-sample recovery policy, and separation from the command guard and experimental pedal-latch policy. The absolute tolerance comes from existing synthetic code; it is not a measured vehicle threshold.

## Verification / evidence (2026-10-12)

Source parent: `61e3b954b403437ea08a632b73a9b003304b7d66`; source Git blob before fix: `5d1ba08826cb38d1142383258d017765f4ea23a5`. Linux x86-64, CPython 3.13.5 standard library. Selected packaged regression: `python3 -B -S -m unittest discover -s . -p 'test_*.py' -v`, **148/148 passed**, exit 0 (142 existing + 6 new). Six new methods against the frozen original: 6 expected assertion failures, exit 1. Initial packaging had a missing relative-path historical guard fixture and one setup error; restored the fixture and reran 148/148. Not a complete fresh-checkout test. No STM32F405/HIL/vehicle or native worker evidence.

## Source index and review gate

- Repository allocator Git blob `5fb87a9509c69eed4d7160b8a649f7972bb16f02`; reference four-wheel synthetic propulsive allocator.
- Repository fault-state original Git blob `5d1ba08826cb38d1142383258d017765f4ea23a5`; missing consistency check.
- Python 3.13 dataclasses reference: https://docs.python.org/3.13/library/dataclasses.html (annotations alone do not validate runtime invariants).
- Official U.S. Formula SAE resources, checked 2026-10-12: https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx lists 2027 rules V1. No rules clause supplied a numerical tolerance.

Next: independent reviewer to evaluate comparison tolerance, zero-request semantics and downstream logging consumers; run complete branch reference suite from an authorized fresh checkout. Separate local controller registration/ACK remains unverified. No main merge, autonomous driving, vehicle actions, firmware flashing or course submission authorized.
