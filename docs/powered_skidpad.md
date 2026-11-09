# Powered skidpad development session

This candidate adds a restartable time-domain skidpad experiment. It uses the
existing synthetic RWD four-wheel plant, actuator/pack model and ordinary
`fixed`, `traction`, `yaw_pi` and `tire_reserve` allocators. These are four
implemented ordinary controllers, not aliases for the portable seven policies.
Team car profiles and native campaign workers are not accepted by this backend.
The existing cell-timed `lapsim-skidpad` command is unchanged.

The fresh powered state starts at the actual course entry, heading along +x.
Guidance uses the existing driver with open-path endpoint clamping, local
projection without lap copies and preview ending at the exit. It never copies
reference coordinates into the integrated plant state. Plant/allocation intervals
are 10 ms, the held driver updates every 50 ms, and RK work remains separately
bounded by the existing cumulative integrator counter. These are the ordinary
experiment clocks, not the portable worker's 1 ms plant clock.
Existing development corridor/sideslip/yaw/slip bounds are also screened at
the actual returned endpoint before chunk, budget or gate completion is accepted;
this pure check does not tick the driver or allocator. Nominal checkpoint
restoration repeats the endpoint validity screen. These sampled checks do not
establish continuous trajectory safety or official track-bound compliance.

The gate ledger observes accepted x/y positions. It requires ENTRY, clockwise
right untimed, clockwise right timed, counterclockwise left untimed,
counterclockwise left timed and EXIT in that order. Each circle needs a full
signed winding around its own centre. A finite central gate and a finite exit
gate use the nominal CG corridor half-width 1.5 m. The selected nominal route
uses radius 9.125 m; entry/exit lengths remain explicit scenario inputs.
Crossing time and pack energy are interpolated on the endpoint chord, with
the original accepted interval, both full bracketing states and their hashes
retained. Full plant states are never interpolated or reset at gates.
The final full-interval time/energy/state remain distinct from the gate's
interpolated boundary measurements; the last accepted interval is not trimmed.
The reused driver's wider assumed corridor is recorded in the fixture binding;
it is not a rulebook track-bound or cone-clearance enforcement mechanism.

This measures model CG gates. It does not prove annulus compliance, body or
cone clearance, official DNF adjudication, a measured driving line or calibrated
car performance. Timed averages appear only after all six gates; cone-corrected
time, official points and qualified tournament eligibility remain unavailable.
The rulebook/handbook cone-penalty discrepancy remains as documented in
[the existing event guide](fsae_skidpad_sequence.md).

## Bounded command

From this source candidate with the ordinary project dependencies available:

```sh
PYTHONPATH=src python -m lapsim.events.powered_skidpad \
  --entry-length-m 5 --exit-length-m 5 --controller yaw_pi \
  --maximum-ticks 10000 --maximum-work 200000 --chunk-ticks 100 \
  --output /absolute/new/external/powered-skidpad-chunk-1
```

An installation of this exact successor source can omit `PYTHONPATH`. Frozen
dev26 wheels/ZIPs do not contain this command. No native one-command tournament
setup/start is established by the development command.

Each invocation creates a new directory containing binding, checkpoint, raw
result and a byte-count/SHA256 file index. Existing output is refused. Creation
is local/create-only; power-loss durability and native output ownership are not
claimed. A running chunk returns exit 0 without claiming completion; completed
model gates also return 0. Failed/cancelled/exhausted sessions return 3; invalid
arguments, identities or output return 2. A 10000-tick event is capped at 100 s.
Cancellation is cooperative between model intervals, not an OS watchdog.

For another chunk use the same inputs and a new output directory, adding
`--resume-checkpoint /absolute/previous/checkpoint.json --resume-sha256 <pinned
hash>`. Limits are cumulative and cannot be enlarged at resume. Failed,
cancelled or exhausted attempts are retained but cannot restart. An interrupted
or rejected unreturned integrator state is unavailable; its attempted interval
is retained and the attempt terminates rather than retrying or refunding work.

Checkpoints retain all PoweredState fields/counters, held driver command,
controller integral, projection memory, clocks, interval energy accounting,
raw command stages, gate-pose trace and full gate-bracket states. Reconstruction
replays the gate ledger, validates state/pose/command/accounting linkage, and
requires the exact request, geometry, fixture, raw Python disk inventory and
limited Python/platform record. Schema changes, altered inputs, source/runtime
drift, missing gates and inconsistent records are rejected. The external hash
must be pinned independently of the checkpoint being read.

The disk inventory is not proof of loaded-code/native closure or authentication.
The limited runtime record is not portable environment-v2. Hashes and local
gate measurements provide no original admission, lease, owned execution,
authenticated terminal or cleanup authority. Existing portable/native provider
requirements remain unchanged. The stored gross/recovered pack fields are sums
of positive/negative **10 ms net deltas**, not continuous substep gross integrals.

## Validation scope

Focused regressions cover open/closed guidance behavior, synthetic full ordered
gate traces and invalid traces, real short powered steps across all four
controller selections and ENTRY, exact split/resume parity between driver
updates, strict checkpoint mismatch rejection, cumulative limits, cancellation,
failure retention and CLI create-only/hash readback. Geometric circuit fixtures
are separate from the real numerical acceptance below.

### Completed numerical acceptance, 2026-11-08

The frozen runtime commit `fc8a6d48121bdd707e20f05213fbc6dbc2a365b3`, ordinary
wheel version `0.1.0+light20261108.3`, completed one real powered skidpad with
`yaw_pi`, 5 m entry/exit, the existing synthetic RWD fixture, 10000 maximum
ticks and 200000 maximum cumulative numerical work. No model, driver or
allocator was replaced by a test double in these acceptance runs.

| Check | Wall limit | Measured wall time | Outcome |
| --- | ---: | ---: | --- |
| Checkout, 100-tick chunks | 60 s | 25.872 s | All six gates; 4150 accepted steps |
| Actual continuation from tick 2100 | 45 s | 14.881 s | Another 2050 steps; final checkpoint byte-identical |
| Frozen wheel, full-event CLI | 45 s | 23.948 s | All six gates; complete numerical/controller/gate records match checkout |

All three ran on Linux/CPython 3.12.14. The full interval duration was 41.5 s;
the interpolated EXIT crossing was 41.494669342 s. The two timed circles averaged
9.957966243 s, with 20750 integration trials, zero wheel-stop events and a final
energy residual of approximately 0.0000135 J. Net pack draw was 23685.463 J;
recovered energy was zero, so this event does not validate regen operation.

The installed run used the frozen wheel with SHA256
`c867bb83da997dcbb703d1fd70a17903778a1f30a28131bc41f4c8a6ff793129`, from outside
the checkout in a clean environment without system site packages:

```sh
<installed-python> -I -B -m lapsim.events.powered_skidpad \
  --entry-length-m 5 --exit-length-m 5 --controller yaw_pi \
  --maximum-ticks 10000 --maximum-work 200000 --chunk-ticks 10000 \
  --output <new-absolute-external-directory>
```

Raw disk inventories differ between an installation and a source checkout;
their whole checkpoint hashes therefore differ. The separately pinned source
continuation is byte-identical to its source baseline. Installed/source equality
was checked for every remaining checkpoint field, rather than weakening or
merging their distinct binding identities. Source/config/runtime hash checks
were left intact.

The other three implemented controllers subsequently completed this same frozen
`.3` synthetic fixture in one bounded attempt each. Their source, course, vehicle,
driver, budgets and complete initial state matched the `yaw_pi` input except
for controller selection. `traction` and `tire_reserve` produced identical raw
trajectories here; this input does not demonstrate an additional reserve-limiter
effect. No winner or qualification follows from these development results.

The new [four-controller field command](powered_skidpad_field.md) composes these
actual session APIs with explicit shared limits and preserves separate outcomes.
Measured team cars, official skidpad eligibility, Windows execution, GUI
acceptance, seven-policy skidpad admission and native campaign/one-command
qualification remain unverified. Frozen dev26
and dev27-r02 packages retain their original bytes; this validation addendum
does not install, transfer, register or admit a native worker.

The [machine-readable numerical evidence](evidence/powered-skidpad-numerical-20261108.json)
pins the input/final checkpoint hashes and the exact source/installed comparison.

### Broader driver timeout investigation and resolution

The unchanged `tests/test_pose_driver.py` collected 48 cases. Two separately
timed processes completed 44 unique cases with no completed assertion failures;
four recovery/lookahead cases remained unfinished. Both processes were stopped
and reaped at their 115 s and 75 s limits. The nonfatal diagnostic stack sampled
planar RK4 replay; that sampled test subsequently passed after 28.815 s. The
measurements support cumulative rollout/replay cost exceeding a short whole-file
deadline, rather than a confirmed hang or numerical defect.

The [per-case timing and coverage evidence](evidence/pose-driver-budget-20261108.json)
names the four unfinished cases. No assertions, physics settings or model work
bounds were reduced. This is not a full driver-suite pass. Further execution of
those four cases needs another explicit finite test allocation. The reported
254.726 s sum combines measured driver-process times and numerical helper times;
the evidence notes the limited import/startup overhead excluded by two helpers.
It is not native allocation, CPU/resource accounting or admission evidence.

The four remaining cases subsequently all passed in separately bounded
processes: 17.132, 19.782, 19.674 and 28.019 s, totaling 84.608 s within their
210 s allocation. The [reviewed completion evidence](evidence/pose-driver-completed-20261108.json)
verifies the union with the prior passes: **48/48 unique driver-file cases**,
zero completed failures, errors, skips or unfinished cases. This is sharded
coverage, not a completed uninterrupted whole-file run or whole-repository
acceptance. Assertions, numerical settings and driver source were unchanged.
