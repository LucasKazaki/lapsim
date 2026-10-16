# TC-02EB: Bound offline timebase freshness snapshot ingestion

**Scope:** proposed 2027–28 Terps Racing EV offline reference only, U.S. FSAE Electric context. **No** MCU/CAN/vehicle authority, native worker ACK, approved team signal count, or firmware timing evidence.

## Source-pinned finding

At draft PR #66 head `855690ab20e199b7b8b0fb0fc51c982f62a4fab0`, `reference/timebase_freshness.py` Git blob `cfa7bf78644093e06858d6cd40b9c434b9095756` does `sample_list = tuple(samples)` without a length limit. A nonterminating or overlong host iterable may consume unbounded memory/time before `classify_freshness`. This is unlike the existing 4,096-step host-only `allocator.replay` limit. The number 4,096 is **not** an authorized physical signal limit.

A finite negative control yielded 4,097 synthetic `TimestampSample` records and raised `RuntimeError` when upstream requested the 4,098th item. The original reference made that extra read rather than rejecting a bounded length. No unbounded original generator was run.

## Proposed isolated candidate

Replace unbounded tuple materialization with `tuple(itertools.islice(iter(samples), 4097))`, raise `ValueError` for length > 4096 **before classification**, and add a focused synthetic test file. This changes only host-side input ingestion, not freshness arithmetic or control outputs. Iterator `next()` itself can still block or have side effects.

**Review-only patch paths:**
- Modified: `projects/enme408-torque-control/reference/timebase_freshness.py`
- Added: `projects/enme408-torque-control/reference/test_tc02eb_bounded_snapshot.py`

The proposed patch is retained in the external portable TC-02EB handoff, **not applied to GitHub** by this research note.

## Actual offline receipts (2026-10-14)

Linux x86-64, CPython 3.13.5, Python standard library, source-matched fixture:

- `cd reference && python3 -B -S -m unittest discover -s . -p 'test_*.py' -q`: **60 passed**, exit 0 (32 original allocator/supervisor, 17 previous compact candidate, 11 new).
- Independent source-parity fixture: **2 methods passed**, including **350 deterministic upstream-vs-candidate snapshot scenarios**, exit 0.
- Finite negative control against original code: expected `RuntimeError`, exit 1, demonstrating request for item 4,098.
- `git apply --check`, isolated apply, and 60-test patched-fixture rerun: exit 0; changed-file SHA-256 matched the staged patch.
- New patched source Git blob `00a1c921e1d693537df813339172f707d6ab53e7`.
- **Not run:** complete current repository suite, independent review, registered local executor, STM32F405, HIL, bench or vehicle testing.

## Primary source index and pending review

- Original repository source: `timebase_freshness.py` at blob `cfa7bf78644093e06858d6cd40b9c434b9095756`.
- Python `itertools.islice` official documentation: https://docs.python.org/3.13/library/itertools.html#itertools.islice , checked 2026-10-14.
- Separate unpatched finding: `TimebaseSpec(ticks_per_second=10**400)` triggers `OverflowError` inside original `_validate_timebase`. See Python's official float conversion documentation: https://docs.python.org/3.13/library/functions.html#float . This is a later independent numeric-domain task, not part of TC-02EB.

**Next gate:** independently review the host-only 4,096-signal cap; reread live branch head, original blob, and writer ownership; apply the two-path patch only in a disjoint authorized checkout; run the full relevant suite. Stop on source mismatch. No forced updates, main merge, deployment, local runtime changes, hardware actions, or course submission.
