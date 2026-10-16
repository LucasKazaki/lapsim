# TC-03F — Portable base command-guard owner

The new C11 owner generates the base guard's proposed torque vector, latch
transition, status and diagnostic for the supported offline record domain.
The real Python `apply_command_guard` remains the reference policy, unchanged.
The allocator still supplies an already computed candidate, and the offline
runner still orchestrates calls. Four synthetic slots do not establish a
physical motor order, a signal mapping, or vehicle authority.

The [protocol](TC-03F-base-command-guard-protocol.json) was committed at
`dbede789d4270f0eb0e5bbc706532cfa69d36a10` before adding C implementation.
It is based on the green PR73 checkpoint
`e00f7d8feb2f18698c8406352bbcffc6b1d8d469`. The prior three-unit host builder,
Cortex-M4 source cohort/protocol, source policy and historical receipts remain
intact. The separate new host library compiles four units; the original
Cortex-M4 experiment says nothing about this new guard unit.

## Interface and domain

`native/torque_guard.h` defines separate version-1 config/input/state/result
structures and `tc_apply_command_guard`. It reuses the existing tagged
binary64 scalars, four-slot vector checks, allocation validator, guard status
and bounded diagnostic text. The existing torque ABI remains 1 and its numeric
contract remains 2. The initializer creates a valid zero history and a clear
latch. Required null pointers and malformed C-only outer schema tags produce
defined inhibited results; available output starts with positive zero and a
conservative true latch. Aligned, complete, non-overlapping objects are required.

Python/C result parity covers ordinary records and numeric values converted to
binary64, including explicitly invalid numeric/Boolean/vector/status payloads.
Python custom numeric conversion hooks, duck-typed outer records, unbounded
text, and values outside the existing bounded decoder domains are not newly
claimed as representable. C-only schema/null checks are reported separately
where Python could raise instead of returning a result.

The floating environment assumes ordinary IEEE binary64 round-to-nearest with
retained subnormals. The new build explicitly disables fast math, finite-only
math and contraction and requests standard excess precision. No different
floating environment or MCU runtime behavior is inferred.

## Preserved policy

Validation preserves the source's fault priority: prior latch, config rise and
pedal thresholds, prior vector, duration, accelerator, Boolean fields, then the
shared allocation contract. Only after those checks does the base latch evolve.
Allocator fault, interlock, communication, sensor and latch inhibits precede
the rise-step calculation. Every inhibit immediately resets proposed output
and its history to exact positive zero.

Each decrease takes effect immediately. Each increase is capped at
`previous + max_rise * dt`. A nonfinite product inhibits; finite-product addition
overflow retains the source's finite target-wins behavior. Underflow and the
existing `commanded < target - 1e-12` status-label comparison are preserved,
including tiny reduced outputs that retain an `ok` label. Valid negative-zero
targets retain their sign bits. These are explicit source semantics, not newly
selected physical margins.

Base latch behavior remains distinct from trusted observation/clear adapters.
A base trip can precede a later communication inhibit; a valid fault cycle can
clear the raw base latch at low pedal. The existing trusted adapters retain the
latch when that clearance is untrusted. The offline composed experiment now
uses the actual C-generated base result before the existing C pedal, normalized
clock and recovery/final gates. Clock faults cannot be sole latch-clear evidence.
Restart preserves the latch and clock anchor. Slew history is the actually
proposed final command, so held recovery cycles do not accumulate rise credit.

## Local evidence

The actual GCC 12.1 host build passed these source-bound comparisons twice:

| Scope | Cases/cycles |
|---|---:|
| Direct source/compiled guard results | 3,886 |
| Stateful base-guard stream cycles | 8,192 |
| Actual native guard/pedal/clock/final composition | 8,262 |
| Separate ABI/domain checks | 6,665 |

The composed set includes the prior 8,248 scenarios and 14 explicit cross-fault,
latch, restart and recovery cycles. It contains 4,090 allowed and 4,172 held
proposed commands, including 319 clock-fault cycles. Every held command has
positive-zero bits. Result signatures compare binary64 hex values, preserving
valid negative zeros. Seven focused tests pin the numerical/latch corner cases
and compare two independently built temporary-directory DLL hashes. The full
reference suite passed 481 tests. The plain host C guard probe also exited zero.

These local results do not imply sanitizer execution. A fourth finite ASAN/UBSan
probe and guard parity artifact are added to the existing GCC/Clang × Python
3.11/3.12/3.13 workflow; actual push-CI execution and independent practical
review remain required before publishing the draft. No local-model output is
used as a correctness oracle.

From the repository root:

```powershell
py -3.12 -B projects/enme408-torque-control/reference/guard_parity.py --output new-guard-parity.json
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p test_guard_parity.py -v
```

The parity output is create-only and includes source/protocol/compiler/flags,
binary hash, repeated behavior signatures, reason counts, named corner results,
and ABI/domain evidence. This is host-only proposed-control evidence: no native
allocator or scheduler, target execution/parity, complete stack/flash/RAM fit,
firmware, CAN, HIL, timing/WCET, independent shutdown ownership or safety approval.
