# TC-03A — source-to-command replay for team review

October 15, 2026. Proposed 2027–28 Terps Racing EV project, U.S. Formula SAE
Electric. **Executable host reference; no live transport or hardware IO.**

The review question is now concrete: given a timestamped source record, which
proposed wheel-slot commands survive allocation, pedal/communication checks,
and recovery qualification? Previously those layers had separate result
validators, and the observer's gate was easy to leave disconnected from the
command path.

## What changed

`allocation_contract.py` is the shared acceptance boundary for the command guard,
fault observer, and former request-check adapter. An `ok` result carrying
`external_interlock_open` is inconsistent and commands zero. Positive output
with a zero request, over-request delivery, malformed status/fault fields,
custom numeric conversion hooks, and vector/aggregate disagreement fail closed.
Only the allocator's `saturated` / `aggregate_limit` pair is accepted as a
non-inhibiting limit. A real allocator fault retains a negative diagnostic
request but requires exactly zero aggregate and wheel output.

Float consistency uses eight ULPs (representable floating-point steps), replacing
the observer's absolute `1e-9` request allowance. That allowance admitted
proportionally large excess at tiny magnitudes. It is a numerical tolerance,
not a motor resolution or vehicle requirement. Legacy fixtures asserting an
unsafe bypass now assert inhibition; nominal large-number fixtures now supply
their actual nonzero request.

`control_pipeline.py` composes the actual source allocator, the trusted pedal
latch adapter, and the fault observer. It enforces the observer gate on the
final proposed vector. Every guard inhibit enters fault recovery. Startup and
restart require consecutive healthy, unsaturated observations; held commands
stay zero without accumulating hidden slew credit. Restart retains a pedal
latch. A fixed-period host replay rejects duplicated/backward timestamps,
missing periods, and an inflated guard `dt`.

`bench_replay.py` accepts strict bounded JSON and emits source-hashed JSON plus
a flat CSV. Unknown/duplicate fields, nonfinite JSON, oversized input, and more
than 4,096 cycles are rejected. The CLI refuses to overwrite its source with
either output. All signals remain normalized offline inputs; no CAN IDs,
physical wheel order, or torque scaling have been invented.

## Reproduce from the repository root

No third-party Python packages are needed. Python 3.12 is the locally tested
interpreter; the scoped CI matrix also requests 3.12/3.13 on Windows and Linux.

```powershell
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p "test_*.py" -q
py -3.12 -B projects/enme408-torque-control/reference/bench_replay.py projects/enme408-torque-control/reference/bench-scenario.example.json --output enme408-bench-replay.json --csv enme408-bench-trace.csv
```

The 18-cycle synthetic fixture covers startup, a capacity limit, brake/accelerator
overlap, communication loss, trusted latch clearance, restart, stale input, and
an open external interlock. Expected totals: **9 allowed cycles, 9 zero-command
cycles, 4 inhibited cycles, 5 recovery-pending cycles**. Read each event rather
than treating a total or green test as hardware approval.

The receipt preserves the input-byte SHA-256 and exact Python source hashes.
The CSV contains sequence/time, original allocation and guard status, recovery
state, final command eligibility/reason, and all four proposed wheel-slot
torques in `N*m`. The companion LapSim bench viewer can open the JSON locally;
its chart and keyboard cycle control are presentation only. Rerun this CLI to
verify a receipt against source; simply opening a JSON file does not authenticate it.

## Verification retained with this candidate

Windows x64, local CPython 3.12: **438 reference tests passed**. The new tests
exercise both consumers against 2,000 seeded actual allocator outputs, malformed
and contradictory results, startup/restart, command gating, period faults,
latch clearance, bounded replay, strict JSON, source hashes, real CLI output,
and preservation of the input file even when outputs alias it through hardlinks.
The 18-cycle example was executed through the real CLI, not a mocked allocator.

An independent source review reran all 438 tests and separately reproduced the
clock/latch, hardlink, and JSON-depth regression cases after repair. A rejected
clock cycle now cannot be the only low-pedal observation clearing a latch;
existing-file aliases fail before either output is written. There were no
remaining actionable findings in that host-only review. The controls team has
not reviewed this candidate, and the new cross-platform CI must be read at its
actual run status rather than assumed to pass.

## Policy requiring the software lead's review

| Reference decision | Current synthetic setting | Evidence needed for a vehicle implementation |
| --- | --- | --- |
| Wheel order | `slot_0` through `slot_3` | Motor count, physical mapping, direction and gearbox conventions |
| Task cadence | 50 ms fixed period | Firmware scheduling and timestamp/wrap handling measurements |
| Input age | 50 ms | Per-message age/deadline policy and measured CAN behavior |
| Rise rate | 100 N*m/s per slot | Inverter/motor limits and team-approved torque response |
| Pedal trip / clear | 0.6 / 0.2 normalized accelerator | Actual APPS/BPPS signals, plausibility and shutdown ownership |
| Recovery | Two healthy unsaturated samples | Approved latch/reset criteria and independence of shutdown logic |

These example numbers have **no vehicle authority**. The earlier kinematic
e-diff and four-wheel dynamics remain separate experiments; this patch does
not add slip/yaw control or establish traction/handling improvement.

## Next measurable step

The software lead can provide a sanitized capture and the signed-off signal
contract. Write an explicit decoder that normalizes that capture into this
scenario schema, preserving source identity and physical units. Replay it
without a transmitter, compare expected fault transitions, then review a
separate target implementation. STM32F405 WCET, stack/heap, watchdog,
communication age, inverter response, independent shutdown, and HIL evidence
are still unmeasured. No flashing, bench energizing, vehicle actuation,
compliance claim, course submission, or master's approval is included here.
