# TC-03D — portable trust predicates and pedal-latch adapters

October 15, 2026. **Host metadata component for the proposed torque-control
project.** The C implementation ports the two narrow trust predicates and the
adapter decisions around an externally computed command guard. It adds native
ownership of missed-trip observation, untrusted-clear veto and clock-fault
latch retention. It does not port the base latch/slew algorithm or generate a
torque command.

The [protocol](TC-03D-pedal-protocol.json) was committed as `d3e1f2b` before
native pedal edits, based on PR 70's `be45cc62`. The Python behavioral owners
remain unchanged. Pedal-adapter contract/layout version 1 is additive to the
existing torque ABI 1, numeric contract 2 and normalized-clock contract 1.

## Ownership and source trust

`native/torque_pedal.h` defines fixed-size metadata facts and a result containing
the observed trip, narrow clearance predicate, veto, next latch and reason.
**No positive torque vector or command authorization exists in this API.** A
veto requires an inhibited, exact-zero guard before the final gate. A non-veto
retains the already-computed base guard and grants no independent authority.

The external base guard must still compute and validate its original result,
including the allocation contract, numeric/config/input checks, base latch and
slew. Native predicates do not authenticate pedal provenance or prove that
supplied metadata came from that producer. The native final gate separately
validates candidate/guard output and enforces recovery. Replacing the base
guard with arbitrary status/latch metadata is outside this component's domain.

The source has a subtle distinction: its base guard can set a latch before a
later communication/sensor inhibit. The trusted-observation adapter adds missed
trips on earlier faults; it does not undo such a base trip. This candidate
preserves that behavior and does not label every base trip trusted.

## Preserved predicates and transitions

The overlap-trip predicate requires expected input/config/state types, ordinary
Boolean latch state, brake/comms/sensor flags true, finite ordinary accelerator
and policy values, positive rise rate, `0 <= clear < trip <= 1`, accelerator in
`[0, 1]`, and accelerator at or above trip. The narrow predicate deliberately
does not inspect external interlock or dt; it can record a missed trip even
when a separate early fault inhibits the cycle.

The clear-cycle predicate requires normal candidate type/status (`ok` or
`saturated`), expected input type, comms/sensor/interlock flags that are ordinary
true Booleans, and normal result type/status (`ok` or `limited`). This faithfully
matches the source helper; it is not a second full allocation or output
validator and does not itself authorize latch clearance or torque.

| Adapter observation | Native action |
| --- | --- |
| Trusted trip missing from base next latch | Veto, retain true latch; preserve reason or use `brake_accelerator_overlap` |
| Prior true → proposed false without trusted clear cycle | Veto, retain true latch; preserve reason or use `untrusted_overlap_latch_clear` |
| Clock fault while prior latch was true | Retain true latch; clock/final gate independently inhibits |
| New conservative trip during clock fault | Preserve that trip |
| Valid base transition without adapter veto | Retain the external base guard |

Malformed prior/proposed latch tags, clock tags, required input/config/state/
result type tags, guard status or bounded diagnostic text conservatively veto
with a true latch. Candidate type/status and individual source trust flags
affect the narrow predicates; complete candidate/input validation remains
with the external base guard. Null required arguments
return an error and initialize any available output to veto/true-latch. These
ABI protections are explicit extensions for malformed native metadata, not
claims that impossible base-guard outputs occurred in Python.

Numbers are tagged ordinary binary64; type tags must be exactly 1 and Boolean
tags encode 0/1 without coercion. Diagnostic text uses the existing 64-byte
representation. The input/output objects must be aligned, complete and
non-overlapping. They are host ABI structures, not a packed signal format.

## Reproduce and current evidence

```powershell
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p "test_*.py" -q
py -3.12 -B projects/enme408-torque-control/reference/pedal_parity.py --output enme408-pedal-parity.json
```

The local Windows/GCC 12.1.0/Python 3.12 suite passes **456 tests**. Each compiled
experiment repeats **2,774 predicate cases**, **2,559 actual source-adapter
cases** (including a frozen seed-410 sample), and **8,248 adapter/clock/gate
cycles**. The source-adapter cases produce 174 vetoes. Composed cycles retain
the previous 4,087 allowed / 4,161 held outcomes, including 318 clock faults.

Another **5,634 ABI/domain checks** cover byte tags, exact threshold boundaries,
reason fallbacks, null pointers, malformed text and clock-retained latches.
Held native gate commands are checked as exact positive-zero bytes. The
standalone compiled host probe passed 512 tagged-field substitutions plus
threshold/null/reason/clock cases without local sanitizers. The source passed
the [six GCC/Clang × Python 3.11/3.12/3.13 jobs](https://github.com/LucasKazaki/lucas-agent-studio/actions/runs/38691373581),
including actual ASAN/UBSan execution of all three native probes, and the
[four Windows/Linux reference jobs](https://github.com/LucasKazaki/lucas-agent-studio/actions/runs/38691373548).

Practical independent review reran 456 tests and checked 69,984 real-source
cross-fault cases, 139,968 clock-retention metadata observations and 69,984 native
gate compositions (69,966 held at exact positive zero, 18 allowed). It preserved
168 trusted missed trips despite separate interlock/dt faults and 48 preexisting
base trips before a later trust inhibit. No unsafe transition was found in the
declared supported path.

That review also checked the boundary explicitly: forged status metadata can
make the raw clear predicate true for a contradictory payload, while the real
base guard inhibits and retains the latch. The adapter is not a replacement for
that base producer. A documentation overstatement about candidate metadata
always vetoing was corrected; no runtime policy changed for that correction.

Receipts bind source/protocol hashes, compiler/strict-math flags, binary hash,
ABI sizes and deterministic result signatures. The finite child releases its
DLL before temporary cleanup. Source/hardlink output aliases are rejected
before build. Existing Python bench receipts and behavioral owners remain
intact; no new source-policy retuning is hidden in this adapter port.

## Remaining implementation and evidence

Port the actual base guard/latch/slew owner before presenting a complete native
pedal or controller implementation. Review per-signal provenance, calibration,
clock/freshness ownership and the relation between supplied metadata and its
producer. Actual APPS/BPPS rules, board timing/resources, persistence, watchdog,
CAN/inverter response and HIL still need separate team evidence. This increment
has no firmware, target startup, CAN transport, motor enable, vehicle action,
measured target performance or safety approval.
