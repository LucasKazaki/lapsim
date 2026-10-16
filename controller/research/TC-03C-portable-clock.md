# TC-03C — portable normalized-clock owner

October 15, 2026. **Host prototype for the proposed 2027–28 torque-control
project.** This increment ports one previously external owner into C: the
fixed-period check on already-normalized millisecond timestamps and guard dt.
It composes that owner before the existing native final gate. It does not read
a timer, normalize counter wrap, schedule a task or transmit a command.

The [protocol](TC-03C-clock-protocol.json) was committed as `9876391` before
native clock edits, based on PR 69's `9baeb614` source. It freezes supported
semantics and checks; subsequent evidence must not redefine those semantics
merely to agree with the implementation.

## Preserved source semantics

The original clock block in `control_pipeline.py` now delegates to
`cycle_clock.observe_cycle_clock`. A frozen legacy block in the source tests
checks 12,672 cases, including Python timestamps beyond the C domain. No Python
timestamp policy was narrowed by the extraction.

| Observation | Fault | Next anchor |
| --- | --- | --- |
| First ordinary nonnegative integer timestamp | None if dt is valid | That timestamp |
| Malformed/negative timestamp | `invalid_cycle_timestamp` | Previous anchor |
| Duplicate or backward timestamp | `nonmonotonic_cycle_timestamp` | Previous anchor |
| Forward interval unequal to configured period | `cycle_period_mismatch` | New timestamp |
| Valid forward timestamp with wrong/malformed dt | `guard_period_mismatch` | New timestamp |
| Restart request | Clock unchanged by restart | Follow the same timestamp rules |

Timestamp faults take precedence over the dt fault. A valid source timestamp
remains visible in normalized `now_ms` even if it was backward or gapped; an
invalid timestamp normalizes to absent. A rejected forward observation can
advance the anchor, but the existing final gate still inhibits the command and
requires recovery. The source guard retains its prior clock-fault latch-clear
protection. This port does not independently own that pedal latch.

The period is an ordinary integer in `[1, 60000]` milliseconds. Ordinary finite
dt must be within an absolute `1e-12` seconds of `period_ms / 1000`, with zero
relative tolerance. This tolerance is inherited from the synthetic reference;
it is not a measured scheduler jitter budget or target oscillator guarantee.

## Native domain and composition

`native/torque_clock.h` adds separate clock contract/layout version 1. Existing
torque ABI version 1 and numeric contract 2 remain intact. Four bounded host
structures hold the prior anchor, tagged timestamp/dt, period and clock result.
All storage is fixed; no allocation, IO or global mutable clock is used.

Python retains unbounded integer time. C accepts normalized uint64 milliseconds
with exact validity tags. The adapter rejects positive timestamps beyond
`UINT64_MAX` and invalid prior anchors; it never truncates, wraps or converts
timestamps to floating point. A raw counter rolling from `UINT64_MAX` to zero
is rejected as backward time. Normalize any actual hardware counter upstream
under an explicit, reviewed policy before using this interface.

`tc_clock_step` preserves the source owner in that representable domain. It
subtracts only after checking the new timestamp is strictly greater than the
prior anchor. Invalid C state/policy produces a named fault with the next anchor
and normalized now initialized absent/zero. An absent anchor
ignores its stored tick field. Null required arguments produce an error and
initialize any available result to a faulted, absent state.

`tc_clocked_decide` replaces `cycle.clock_fault` with its own clock result,
then invokes the existing native gate. It initializes both available outputs
before validating every required pointer. Malformed allocation and guard
records retain the prior gate's validation priority. Every held output remains
exact positive zero. A successful function return can still mean inhibition;
read `command_allowed` and the diagnostic fields.

Pointers must designate aligned, complete, mutually non-overlapping objects.
These are host ABI structures, not a packed wire format. Validity tags represent
decoder obligations; the code cannot authenticate their claimed source. The
same normalized timestamp must also be used by the external allocation/freshness
owner. Native composition cannot attest that caller-level relationship.

## Reproduce and inspect

From the repository root with Python and a GCC/Clang-compatible host compiler:

```powershell
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p "test_*.py" -q
py -3.12 -B projects/enme408-torque-control/reference/clock_parity.py --output enme408-clock-parity.json
```

`--cc` or `CC` selects the compiler. The finite child process releases the loaded
Windows DLL before temporary cleanup; a receipt is published only after that
lifecycle succeeds. Source/hardlink output aliases are rejected before build.
Builds reject fast-math/finite-math-only, require binary64 and retain the prior
deterministic host binary settings.

The local Windows/GCC 12.1.0/Python 3.12 suite passes **452 tests**. Each clock
experiment compares **14,837 direct cases**, **4,096 stateful clock cycles** and
**8,248 native-clock-plus-gate cycles**, then repeats the experiment exactly.
Composition includes **4,087 allowed / 4,161 held cycles**, **318 clock faults**
and **253 restarts**. Independent scalar/type boundaries, one-step timestamp
differences beyond `2**53`, uint64 extrema, nextafter dt tolerance edges and the
original clock/latch regression sequences are exercised.

Another **793 ABI/domain checks** include all **768 byte-tag substitutions**
for the timestamp tag, dt numeric tag and previous-anchor tag, invalid periods,
null arguments and exact-zero outputs. A standalone compiled host probe also
passed its 768 substitutions and uint64/null/composition cases. The dedicated
[GCC/Clang × Python 3.11/3.12/3.13 matrix](https://github.com/LucasKazaki/lucas-agent-studio/actions/runs/38689995207)
also passed, including actual AddressSanitizer/UBSan execution of both standalone
probes. Target timing and memory behavior remain unmeasured.

Independent review caught a mismatch in the initial candidate: invalid C policy
faulted the gate but retained the previous anchor, contrary to the frozen
initialized-output requirement. A new regression failed on that candidate.
Period validation now precedes copying the prior state; invalid-policy results
retain absent/zero clock outputs. The [repair record](TC-03C-review-repair.json)
binds the original source/receipt, failing log and final source hashes. The
frozen clock semantics were preserved; the original gate already inhibited.

After the repair, a separate reviewer reran all 452 tests, then independently
checked 420,000 dt-boundary cases covering every period from 1 to 60000 at exact
`UINT64_MAX` cadence, 12 tabulated fault/anchor/precedence cases, 640 clock-fault
compositions across gate states/counters/restarts, eight stateful clock cycles
and nine invalid-policy initialization cases. No further actionable finding
remained in that host-only review. This is practical source review, not target
validation or approval by the controls team.

The prior allocation/gate experiment still has identical result signatures
across 2,179 allocation records and 8,210 cycles. All 18 published synthetic bench
records match the numeric-v2 checkpoint exactly. New bench receipts add
`clock_contract_version: 1` and hash the extracted owner; old receipts stay intact.
Counts characterize finite synthetic tests, not on-vehicle behavior.

The local Qwen alias ran a bounded review on the RTX 5080 in 10.32 seconds.
Its gap and bad-dt examples were made concrete and confirmed as existing
behavior. Its claim that fault precedence was unspecified was rejected: the
pre-edit protocol specifies timestamp precedence, and three combined-fault
compiled cases confirm it. [Raw response and dispositions](TC-03C-local-model-assessment.json)
retain source/prompt/receipt hashes. No defect or approval was inferred from
the model's prose. The model saw the clock logic before the separate
strict-math compile guard and independent invalid-policy initialization repair;
the exact verified source hashes are retained.

## Remaining owners and target evidence

The allocator, trusted pedal/latch logic and slew limiter still execute outside
C. The final gate consumes their validated proposed results. Input freshness,
signal units/calibration, actual motor mapping, counter normalization, retained
state, watchdog independence, MCU timing/stack/heap and CAN/inverter behavior
remain separate work. No firmware, flash, vehicle action, HIL, target execution
or controls-team/safety approval is established by this host increment.
