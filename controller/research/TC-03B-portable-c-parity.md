# TC-03B — portable C contract and final-command gate

October 15, 2026. **Host prototype for the proposed 2027–28 torque-control
project.** No firmware, CAN transport, motor enable, board startup, physical
wheel mapping, or measured STM32 behavior is included.

The C implementation makes the shared allocation-result contract and final
recovery gate executable outside Python. The reference allocator, pedal latch,
rise limiter and normalized clock remain separate owners. This is a bounded
step toward an embedded implementation, not a complete controller port.

## Implemented boundary

`reference/native/torque_contract.h` defines four fixed wheel slots, explicit
numeric/type/status tags, 64-byte diagnostic buffers, binary64 values and
32-bit recovery/generation counters. The C source uses fixed-size local storage;
its decision functions perform no allocation or IO. ABI structures have ordinary
host alignment and are not a packed message format.

`tc_validate_allocation` enforces the shared result contract. An accepted `ok`
record cannot carry a fault, a saturated record must carry `aggregate_limit`,
and a fault must carry a nonempty diagnostic and exact zero output. Invalid
numeric tags, nonfinite values, sum disagreement, and output above the request
are rejected. A fault can retain a negative diagnostic request.

`tc_decide` consumes an already-computed guard result plus an explicit previous
fault snapshot. It starts from an inhibited, exactly-zero output; validates the
candidate and guard; applies clock/allocator/guard inhibits; advances recovery;
and copies the bounded guard vector only if the final gate allows it. Unknown
status/tags, invalid text, out-of-bound guard output and unsigned-counter
overflow inhibit. Startup uses `tc_init_snapshot`; a successful function return
does **not** imply a command is allowed. `reason` reports the fault-observer
transition; the caller retains the separate guard reason in the cycle input.

Inputs and output must point to complete, aligned, non-overlapping objects.
A null required input returns an error with an initialized zero decision when
an output is available; a null output returns an error. This cannot validate an
arbitrary corrupt pointer or attest a decoder's claimed type/signal provenance.

## Numeric contract version 2

Independent review found a real gap in the first C parity candidate despite its
original tests passing. CPython 3.12 uses compensated floating-point summation
in builtin `sum`; ordered C additions can differ by a rounding step. The pinned
[CPython 3.12.2 implementation](https://raw.githubusercontent.com/python/cpython/v3.12.2/Python/bltinmodule.c)
shows that compensation in the float-sum path.

For `u = ulp(1.5)` and wheel values `(1.5, u/2, u/2, 0)`, the historical Python
total is `1.5 + u`, while the initial C total was `1.5`. With delivered torque
`1.5 - 8u`, Python rejected the aggregate mismatch but C accepted it; at
`1.5 + 9u`, the verdicts reversed. The exact original cases, outcomes and source
hash are retained in [the numeric-change record](TC-03B-numeric-contract-change.json).
The initial source/receipt snapshot and failing regression log are also
preserved locally; the historical PR 68 and PR 13 commits remain unchanged.

The new branch explicitly defines **numeric contract version 2**: start with
binary64 zero and add the four values in slot order, rounding each addition.
One Python helper owns allocator delivery and allocation validation; one C
helper owns allocation and guard validation. The remaining Python guard,
observer and final-gate owners have no separate floating aggregate reduction.
Bench summary sums count integer events. The eight-ULP tolerance and exact-zero
rules are retained.

This is a narrow, documented policy change: aggregate delivery can differ in
its last bits, and rounding-boundary classifications can change. It is not a
claim that the earlier implementation always matched C. Per-wheel allocation,
physical request/limit assumptions, pedal policy, slew policy and recovery
settings are not retuned by this change. The C ABI layout remains version 1;
numeric version 2 is separately exported and checked. Compiled parity receipts
advance to schema `enme408-portable-c-parity/v2`. Structurally compatible bench
receipts retain their v1 wire schema and add `numeric_contract_version: 2`.
Historical receipts retain their original source hashes and absence of that field.

## Reproduce

From the repository root, Python plus a GCC/Clang-compatible **host** compiler
are sufficient; no third-party Python packages are required:

```powershell
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p "test_*.py" -q
py -3.12 -B projects/enme408-torque-control/reference/c_parity.py --output enme408-c-parity.json
```

Select a compiler explicitly with `--cc` or `CC`. The locally verified toolchain
is the installed MSYS2 GCC 12.1.0 on Windows x64. The build uses C11, warnings as
errors, binary64 checks and strict math flags. Fast-math and finite-math-only
builds are explicitly rejected. MinGW's PE timestamp and preferred image base
are fixed for repeatable binary hashes while its ASLR dynamic-base flag remains
enabled (observed DLL characteristics `0x160`). No target linker or flash image
is produced.

The actual DLL is loaded in a finite child process, so Windows releases it
before the parent removes the temporary build directory. Receipts are written
only after child exit and cleanup succeed. Output paths cannot overwrite the
contributing sources, including aliases through hardlinks.

## Actual checks

The local Windows/CPython 3.12 suite passes **445 tests**. Each compiled parity
pass compares **2,179 allocation records** covering every acceptance/diagnostic
outcome, and **8,210 decisions** from the actual source allocator/guard/pipeline.
It repeats the experiment and compares deterministic results. There are
**4,068 allowed cycles, 4,142 held cycles, 297 clock-fault cycles and 230 restarts**
per pass. Counts describe synthetic cases, not vehicle performance.

Thirty-four additional C ABI/domain checks exercise malformed numeric/Boolean
tags, guard status/output bounds, unterminated text, null inputs/output,
`UINT32_MAX` transitions and exact zeroing. A separate compiled host probe passed
768 tagged-field substitutions plus numerical/text/null/counter cases. The
dedicated CI passed GCC and Clang on Python 3.11/3.12/3.13, including actual
AddressSanitizer and UndefinedBehaviorSanitizer execution on the standalone
probe ([first successful matrix run](https://github.com/LucasKazaki/lucas-agent-studio/actions/runs/38688489034)).
The first existing Windows workflow exposed a test-fixture issue: its checkout
and default temporary folder occupied different volumes, so a hardlink could
not be created. The alias fixture now creates its temporary directory beside
the source, preserving the real hardlink assertion across that layout.

The source-hashed parity receipt records compiler/version/flags, binary hash,
ABI sizes, numerical version, seeds and result signatures. It is a reproduction
receipt, not an MCU WCET, memory budget or empirical safety result.

A separate agent re-reviewed numeric version 2, reran all 445 tests, and checked
another 1,728 mixed-scale/ULP cases, 2,304 tagged-field substitutions and six
null/counter edges against the compiled code. Both original summation
counterexamples now agree with the declared v2 outcomes. No actionable finding
remained in that host-only review; this is not controls-team approval.

## Local-model review and its limits

The local Qwen alias was run on the RTX 5080 to propose bounded numerical and
counter tests. Its first structured response was truncated. A compact retry
returned valid JSON but two incorrect expected outcomes: a genuine `DBL_MIN`
sum discrepancy was predicted valid, and an overflowing recovery count was
predicted to remain pending. Deterministic checks rejected both expected
outcomes. The counter edge was already covered by explicit inhibition; it was
not an accepted defect report.

[The raw-response assessment](TC-03B-local-model-assessment.json) preserves model
identity, response text, receipt/prompt hashes, observed GPU residency and each
proposal's disposition. Local-model output assisted test exploration; it did
not establish correctness or replace independent review. The mixed-scale
summation defect came from the independent code reviewer.

## Next target evidence

Review the numerical policy, state ownership, decoder obligations and exact
signal contract with the software lead. The C final gate does not independently
implement pedal trust, slew history, input freshness, clock wrap or persistence.
Port those owners with parity fixtures before any target integration. Actual
STM32 compiler/ABI, execution time, stack/heap/code size, restart behavior,
watchdog independence, CAN/inverter response and HIL still need measured
receipts and the appropriate team review. No bench/vehicle action is authorized
by a host test passing.
