# Native suspension study (E16)

This optional headless Windows study runs actual Chrono::Vehicle CPU physics.
It answers whether a native vehicle can settle, respond to bounded rear-drive
and steering requests, expose suspension/contact telemetry, and reproduce its
saved inputs. It does not estimate the team car's handling or lap time.

The profile `chrono10_synthetic_sedan_shafts_brakes_v1` derives from the upstream synthetic
Sedan fixture: passenger-car dimensions, approximately 1,671 kg with tires,
two double-wishbone axles, front steering, and a rear shaft differential.
Its four brake input references select the upstream shaft-clutch brakes instead
of `BrakeSimple`, which cannot model sticking brakes. This keeps the supplied
2,000 N m maximum capacity and adds the supplied 0.4 kg m² brake-shaft inertia
per corner. The torque-limited clutch supports stationary settling; no ideal
brake lock is enabled. This derived definition and all dependency hashes are
recorded, and its temporary input file is removed when the plant closes.
No Formula SAE geometry, fitted tire data, motor topology or team measurements
are implied. Verified team geometry remains a separate E16 dependency.

## Inspect a supplied result in the ordinary environment

Opening a saved result needs only the ordinary project Python environment:

```powershell
python -m lapsim.experiments.suspension_study --inspect work/native-drive.json
```

Inspection reads at most 8 MB and checks the record schema, receipt/content
hashes, scenario, execution-count consistency, finite channel shapes, command
and observation clocks, wheel order, and completed-interval command phase.
It prints the saved scenario, clocks, capabilities/topology, provenance, stored
metrics and historical execution receipt without dumping the sample arrays.
It does not import PyChrono, construct a plant, launch Git or another process,
or write a result; `--inspect` cannot be combined with `--replay` or `--output`.

The summary separates checks performed while opening from saved claims.
Current implementation-file matching uses the same three-file hash scope as
replay, without checking out a revision. A historical implementation mismatch
remains inspectable and is labeled explicitly. Missing current source files
produce an unavailable match status. Native model/asset identities, metrics and
timing are recorded claims: integrity hashes do not establish authenticity,
fresh numerical agreement, historical timing validity or vehicle calibration.
Use the native `--replay` workflow below for a new reproduction; it still
requires exact implementation hashes and compares the full fresh native payload.

The corresponding APIs are `read_study_record(path)` for a validated saved
record, `inspect_study_record(record)` for this summary, and
`validate_study_record(record)` for structural/integrity checks. They preserve
the supplied IDs and measurements. Earlier v1 records without explicit settling
sampling metadata remain readable, with that sampling scope marked unrecorded.
The [inspection verification receipt](research/evidence/chrono-saved-inspection-20261017.json)
records the focused checks and a guarded read of already-saved native telemetry;
it contains no new native simulation or calibration evidence.

## View saved telemetry on the desktop

Open **Four-wheel lab → Open native record…**, then choose a saved study JSON.
This opens a separate passive viewer in the ordinary desktop environment; it
does not start Chrono, replay physics, change the input file or evaluate the
planar model. The additional action row keeps the entry visible without adding
another button to the lab's existing header.
The visible model profile is the record's bounded, escaped claim; its full value remains in Details and does not identify a current engine.

The four panels show the recorded COM path and wheel-center points, COM height,
four spring lengths, and applied or computed vertical tire forces. The points
are not suspension hardpoints or wheel orientations; spring length is not wheel
travel. Force traces use their own stored source timestamps, with unknown
initial origins omitted. They are not contact-wrench arrows at current wheel
positions. The selected-sample text retains all state, force, slip and applied
geometry clocks separately.

Use the slider or **Previous/Next** to select an exact
exported sample. No intermediate states are simulated or interpolated. The
focused slider also supports Left/Right and Home/End, with a visible focus ring. The
displayed command is the request held during the completed interval; a command
event at the same time starts the next hold. **Record and sample details…**
opens the read-only inspection summary and the exact selected observation.
Historical source mismatches and unavailable source files remain labeled as
reported by the inspector, including in packaged environments.

Loading is bounded by the existing 8 MB reader, with one background worker and
no overlapping opens. Failed loads clear the previous result; closing discards
pending results and canvas callbacks. Plotting exported samples does not
revalidate dense settling acceptance, historical performance or calibration.
If finite saved values exceed the chart renderer's range, the viewer clears an
unrenderable record or labels an unavailable force panel. The force panel's
exact values remain in Details, and selecting a plottable channel recovers it;
the saved values and validator are unchanged.

The existing desktop integration check always opens and closes an empty viewer.
To also exercise a supplied saved record in source, wheel or portable-executable
QA, use the optional input with the existing report option:

```powershell
python -m lapsim.desktop --self-test work/desktop-check.json --self-test-native-record work/supplied-native-study.json
# Portable package: LapSim.exe --self-test <report.json> --self-test-native-record <record.json>
```

The report must be separate from the input, including existing hardlinks. This
check selects the first, settling-boundary and final samples, checks both force
channels and their actual clocks, opens read-only Details, and retains the saved
IDs and input SHA256/mtime. The viewer's current-source availability status is
reported as observed, including unavailable source in a frozen runtime. Omitting
the input reports this saved-record scope as `not_requested`; an empty-viewer
check alone does not establish packaged saved-record acceptance. This QA option
does not run native physics or provide board timing evidence.

### Review a saved pair in the viewer

The viewer adds **Compare saved record…** after a primary record
has opened. It opens one modeless window with that record as **Left**. Choose
the explicit recorded difference, **Plant step** or **Logging period**, then
**Choose second record…** for **Right**. Closing the picker preserves an existing
comparison. The primary sample cursor and force selection remain usable while
the bounded background comparison finishes.

The summary uses the same comparison API below. Plant-step rows show final
world-X velocity, chassis COM height and four spring lengths with units and
**Right - Left** differences. It labels the saved-fixture endpoint criterion as
passed, failed or not applied. Logging-period summaries show exact shared and
unmatched export counts; agreement of shared observations is not equality of
unmatched exports. Incompatible recorded inputs show reasons without a numerical
result. No paired charts, interpolated observations or synchronized force
cursors are added. Each record's force and geometry clocks remain separate in
the complete report.

**Comparison details…** displays the full, read-only API report, including input
content/receipt IDs, calculation and comparison receipt IDs, observed recipe
readability and its limited source scope. Visible filenames and profile claims
are bounded and escaped; filenames provide display context. Missing local
sources do not borrow recorded hashes or establish a complete recipe. A saved
comparison does not establish a fresh replay, authenticity, timing performance
or vehicle calibration.

Choosing a different kind or second file clears the previous comparison and
its Details. A failed second-file load clears that comparison while retaining
the primary record. Opening another primary record closes the comparison view.
Closing the comparison, Escape or closing its parent discards late results;
the bounded worker retains ownership until it finishes, so parsing is not
force-cancelled and a second worker cannot overlap it. The comparison window
uses native keyboard controls; Escape returns to the primary viewer action.
The two kind choices also support widget-local arrows with wraparound; Tab,
Shift-Tab and Space retain their normal behavior, and slider keys are unchanged.

At `e211aa3`, 154 focused source checks passed on the owner's Windows PC,
including the real Tk workflow. An external direct-JSON oracle passed 13
genuine-record/error/ownership cases through normal widget commands and explicit
test-only file-picker responses. Four owned-window captures were reviewed at
normal/minimum sizes in both themes. The logging pair retained exactly 81 shared,
320 left-only and 80 right-only exports; the sparse record has no 6.02 s sample.
The [focused Tk and genuine-record receipt](research/evidence/chrono-pair-viewer-tk-20261017.json)
retains source IDs, counts, resource/clock scope, captures and the initial focus
and radio-keyboard failures. The [earlier pure receipt](research/evidence/chrono-pair-viewer-pure-20261017.json)
remains the historical pre-implementation/pure-only evidence.

These source checks do not establish an installed or frozen pair workflow.
Each distributed runtime needs its own normal-workflow verification; broader
acceptance belongs to the reviewed change and canonical issue. Existing desktop
self-test options retain their single-record scope; no pair QA flags are added.

## Compare two supplied saved studies

The ordinary environment also provides a read-only saved-pair API and CLI:

```powershell
python -m lapsim.experiments.suspension_compare work/drive.json work/drive-half-step.json --kind plant-step
python -m lapsim.experiments.suspension_compare work/drive.json work/drive-sparse-log.json --kind logging-period
```

Each input uses the existing 8 MB validated reader. The selected scenario field
is the only permitted input difference: recorded model/assets, capabilities,
implementation hash scope/files, other scenario fields, full command schedule,
initial observation, frame, units, wheel order and controller description must
agree. Git commit/dirty claims are shown separately. Missing profile/engine/asset
claims or an unsupported source scope block numerical comparison. No engine,
replay, new run, input write or automatic fallback is involved.

`plant-step` reports signed right-minus-left final world-X velocity, COM height
and four spring-length differences. Each observation's actual accumulated time,
completed-interval command and computed/applied force values and source clocks
remain separate; these are not simultaneous force differences. Unrepresentable
subtraction of finite inputs is an explicit error.

The existing native test's **saved fixture endpoint criterion** is applied only
to the recorded default drive scenario at 0.0005/0.00025 s, the accepted synthetic
fixture's complete physical/input/initial-observation claim fingerprint, and a
current implementation-file match. The finer step is the velocity reference:
`abs(coarse - fine) <= max(0.01 * abs(fine), 1e-12)`. COM height and each spring
use only an absolute 0.001 m limit. This is a static calculation on saved claims;
a pass does not establish positive drive, full native acceptance, convergence,
physical accuracy or a fresh replay. Other compatible pairs retain their deltas
and an explicit reason the criterion was not applied, including unavailable
current source in a frozen environment. The fingerprint contains no Git identity,
local paths or historical execution measurements and does not authenticate data.

`logging-period` matches **exact stored state timestamps**, with no rounding,
index alignment, tolerance or interpolation. It lists shared and unmatched
counts/times, compares all shared recorded observations exactly, and reports
differing fields and up to five examples with their own force clocks. Time lists
are capped at 2,003 entries each with an explicit truncation flag; the existing
scenario budget bounds every supported input to this limit. A sparse record
without a 6.02 s observation does not acquire one from the denser record.
Null force origins remain null, and sparse exports do not revalidate dense
settling metrics. All inspection checks and historical timing/metric claims
remain distinguished; no performance winner is inferred.

The APIs are `compare_study_records(left, right, kind=...)` and
`compare_study_files(left_path, right_path, kind=...)`. Incompatible claims return
a report without numerical results; corrupt/oversized inputs or overflow raise
an error. The CLI writes only a JSON report to stdout: exit 0 means comparison
completed, even if its named numerical criterion failed; invalid/incompatible
inputs exit 1. Existing native record schema and replay source scope are unchanged.

New reports add schema `lapsim.native-suspension-comparison.v1`,
`comparison_recipe`, `report_id` and `receipt_id` without replacing the existing
fields. Earlier unversioned comparison outputs remain historical outputs; they
are not silently upgraded or assigned new identities.

The comparison recipe observes these seven package-relative source files:

| File | Included behavior |
| --- | --- |
| `experiments/suspension_compare.py` | Comparison, criterion and report identity |
| `experiments/suspension_study.py` | Scenario, validation, inspection and native-source matching |
| `dynamics/native_plant.py` | Saved command and observation contracts |
| `dynamics/chrono_vehicle.py` | Source bytes read for native-match eligibility; the backend is not imported |
| `experiments/dynamics_record.py` | Canonical JSON and content hashing |
| `experiments/record_io.py` | Bounded file reading |
| `experiments/basic_dynamics.py` | Strict JSON decoding |

Hashes normalize CRLF to LF only. Each file has an observed `readable`, `missing`
or `unreadable` status; missing/unreadable hashes are null. `recipe_id` hashes the
complete recipe descriptor except itself only when all seven files are
readable. Otherwise it is null and the recipe is explicitly incomplete.
This also applies in frozen or installed contexts: recorded input hashes are
never substituted for missing local files. Comparisons remain available, with
the existing criterion's source-availability restrictions intact.

This limited source scope is not a complete transitive environment fingerprint,
an executable attestation or a fresh native test. Python, third-party packages
and native binaries are outside it. The named native quality test is a reference,
not an executed dependency; the comparator contains the static criterion policy.

`report_id` hashes a canonical calculation projection: report schema and kind,
scope, ordered left/right input content IDs, the observed recipe descriptor,
comparison status, compatibility decision/selected field, and the full numerical
result including its clocks and criterion applicability. Compatibility reasons
are sorted only for this calculation projection; the displayed report is retained.
Input receipt IDs, historical execution/timing claims and other inspection
context are excluded. No ambient Git identity, paths, timestamps or runtime
measurements are collected for the calculation identity. A timing-only change
to an otherwise identical valid input receipt therefore preserves `report_id`.

`receipt_id` hashes the complete emitted report except itself, binding
`report_id`, both input receipts and every displayed claim. Timing-only changes
alter this full receipt identity. Incomplete recipes still have calculation and
receipt identities for the report actually produced; they do not acquire a
complete recipe identity. These hashes establish content identity, not
authenticity, calibration or new numerical validation. The native study schema
and its separate three-file replay identity remain unchanged.

The [local verification receipt](research/evidence/chrono-comparison-provenance-20261017.json)
records the retained pre-implementation failure, independent pure-fixture
contracts and measured resource scope. Broader integration checks remain
separate from this comparison calculation.

## Install separately from ordinary startup

Use official micromamba 2.5.0-2 on Windows; its flat package cache avoids the
long URL-based cache paths introduced in later versions. The executable's
SHA256 is `baf6d56a31a63a75f0c77bdce27fefea57b1bdc8aa25b50a1be45696c0e737e7`.
Use short project-specific paths, without changing Windows settings. From the
repository root, replacing the executable path with your downloaded copy:

```powershell
$mm = 'C:\path\to\micromamba.exe'
$nativeEnv = 'C:\path\to\short\chrono312'
$nativeCache = 'C:\path\to\short\chrono-cache'
$env:MAMBA_ROOT_PREFIX = $nativeCache
& $mm create -y -r $nativeCache -p $nativeEnv -f environments/chrono-win64.lock.txt
& $mm run -p $nativeEnv python -m pip install -r environments/chrono-pip.lock.txt
& $mm run -p $nativeEnv python -m pip install --no-deps -e .
```

Set `MAMBA_ROOT_PREFIX` in the current shell before the first invocation, and
retain it for the run commands below. The local reproduction found that a
populated default directory could make micromamba fail during startup, before
it read `-r`. Selecting the isolated project cache through the environment
resolved this without changing or deleting the default directory.

The explicit conda lock identifies all native package builds and checksums;
the pip lock pins the Python dependencies. The supported engine is the official
release-label `pychrono=10.0.0=py312h418371c_0` with Python 3.12. The initial
resolved native download was about 1.8 GiB. This distribution installs CUDA
libraries even though this study uses CPU physics. It does not install a
driver, create a CUDA physics path, or change the baseline environment.

Ordinary `scripts/bootstrap.py`, desktop, browser, and fast-model commands do
not import or install PyChrono. Native libraries cannot run inside Pyodide.
This increment has a local command-line workflow, without a browser service.

## Run, stop, and reproduce

```powershell
& $mm run -p $nativeEnv python -m lapsim.experiments.suspension_study --scenario drive --output work/native-drive.json
& $mm run -p $nativeEnv python -m lapsim.experiments.suspension_study --replay work/native-drive.json
& $mm run -p $nativeEnv python -m lapsim.experiments.suspension_study --scenario steer --output work/native-steer.json
& $mm run -p $nativeEnv python -m lapsim.experiments.suspension_study --scenario settle --output work/native-settle.json
& $mm run -p $nativeEnv python -m pytest quality/test_chrono_native.py -q --junitxml=work/chrono-native.xml
```

Use `--plant-step 0.00025` for a half-step comparison. The Python API accepts a
validated `SuspensionScenario` for other bounded settings. Six seconds under
gravity precede a two-second maneuver by default. At every plant-tick boundary
in the final 0.5 s of settling, cached applied vertical tire reaction must remain
within 1% of total weight,
left/right axle-load difference within 1% of half the weight, and vertical
chassis speed within 0.01 m/s. A failed settling gate stops before actuation.
The gate observes independently of the logging cadence and retains streaming
maxima, so an excursion between exported samples cannot be hidden by sparse
logging. `metrics.settle_samples` counts these acceptance observations;
`metrics.settle_sampling` records their clock, period, first/last actual sample
times and force channel. A window edge between plant ticks is not interpolated.
Exported `samples` remain on the logging grid plus the explicit settling/final
samples. These are discrete numerical fixture criteria, not continuous-time
guarantees or calibration tolerances.

Ctrl+C cancels a run. With `--stop-file work/detailed-study/STOP`, creating that
file also cancels at a plant-tick boundary. No completed record is returned or
published after cancellation, and the native owner is closed. Existing output
is preserved until a complete replacement is ready. Replay output cannot alias
the input. JSON reads and scenario work are bounded. The CLI reports coarse
progress; the API accepts progress and cancellation callbacks.

## Physical state, clocks, and signs

`ChronoVehiclePlant` alone owns the chassis, joints, wheels, shafts, tire forces,
contact and gravity. The distance-domain and planar models contribute no forces.
The runner owns an integer clock: default plant step 0.5 ms, driver-request update
10 ms, and logging 20 ms, with explicit settling and final samples. There is no
rendering clock. Changing logging does not synchronize or advance the plant.

The controller baseline is a 0.5 s ramp to 40 N m at the driveshaft, with zero
order hold; steering ramps to a normalized 0.06 in the steering case. The
rear differential transmits torque to its two wheels. There is no independent
left/right request, motor/inverter/battery model, regeneration, traction control,
or electrical limiting in this fixture. Requested driveshaft torque and reported
driveline wheel torque are different quantities; gearing and shaft inertia mean
they need not match. Reported wheel torque excludes tire and brake torque.
Settling uses normalized braking 0.2 (400 N m capacity per wheel); the request
is released for the maneuver. `settle_braking=0` explicitly selects a free-rolling
diagnostic, which may retain motion because the tire has no rolling resistance.
The chosen public brake API reports requested capacity, not actual sticking
reaction, so this study does not export a fabricated achieved brake torque.

All quantities use SI, a right-handed world frame (initial X forward, Y left,
Z up), and wheel order FL, FR, RL, RR. Chassis position/velocity describe its
center of mass. Positive wheel-local +Y speed and driveline wheel torque imply
propulsion. Native axle-shaft speed has the opposite sign and is retained
separately. The steering value is a normalized request, not a wheel angle.
Orientation uses explicitly named Cardan XYZ angles. The separate heading is
the direction of the chassis forward axis projected into the world XY plane;
it is not inferred from an ambiguous Euler-angle convention.

The standard Chrono update is explicitly coupled. For interval `[t,t+dt]`,
`Synchronize(t)` samples contact geometry and slip, and accumulates the previous
local tire-force cache using the current contact frame. `Advance(dt)` computes
the new tire force from inputs at `t`, then advances the chassis to `t+dt`.
Samples therefore contain separate computed/applied forces, force-source time,
applied-force geometry time, and tire-kinematics time. The reported command
belongs to the completed interval; the command event list records future holds.
The complete native `TerrainForce` wrench is not presented as a simultaneous
measurement because its reported application point uses a later wheel state.

## Fidelity and evidence boundaries

The selected Pac02 implementation calculates combined longitudinal/lateral
handling force from instantaneous slip; it has no normal-speed slip-relaxation
states. It also has two low-speed Dahl bristle states, fully active below
1 m/s and blended out by 3 m/s. Their configured internal step must equal the
actual plant step; `Advance(step)` alone does not update that internal clock.
The adapter sets it on every advance. Leaving it at 1 ms while halving or
quartering the plant step was reproduced as a failed numerical experiment;
those results are not convergence evidence. Camber is limited to 3 degrees by
the upstream default. This fixture's
TIR uses linear vertical stiffness/damping and lacks tire bottoming, rolling
resistance, inflation-pressure sensitivity, and overturning coefficients. Native
warnings remain in the run log. Loading a TIR does not imply that every field or
physical effect is supported. Chassis and links are rigid; there is no aero,
flexibility, thermal model, surveyed road or real-car validation.

The record binds scenario, implementation hashes, native module hashes, exact
engine build, JSON/TIR asset hashes and the derived vehicle-definition hash,
numerical settings, commands and samples.
`content_id` identifies deterministic payload; `receipt_id` also covers the
historical execution measurements. These hashes provide integrity, not a
signature or proof that an edited report was physically measured. Replay checks
native inputs and numerical outputs with relative tolerance 1e-7 and absolute
tolerance 1e-8 in each channel's SI units; it does not verify historical wall time.
Use the recorded source revision if implementation hashes differ. Line endings
are normalized in implementation identities.

Runtime receipts separate initialization from stepping/recording and identify
their measurement scope. Peak working set is the process-lifetime high-water
mark, not an isolated allocation measurement. Fresh-command timing must also
include interpreter/import startup and export; do not infer deadline, jitter or
real-time performance from a simulation/wall-time ratio. This backend explicitly
selects CPU `ChSystemNSC` and `ChSolverBB` (150 iterations, tolerance 1e-10,
one thread). The RTX 5080 performs no physics or rendering in this headless run.

## Local verification example, 17 October 2026

At `0514215`, all 11 actual native checks passed on Windows 11 with a Ryzen
7950X3D and 32 GB RAM. The gravity-window maximum reaction imbalance was
0.0434% of weight; halving the drive step from 0.5 to 0.25 ms changed final
forward speed by 0.0019%. These quantify this synthetic fixture's numerical
behavior, not team-car accuracy.

The corrected setup was reproduced from both locks in a fresh prefix at
`5db439d`, followed by separate export and replay processes. An earlier saved
native-test record also replayed in that prefix. The 8 s drive used 16,000
plant steps, 800 driver updates and 401 samples. Its receipt measured 8.07 s
inside the study, 7.98 s process CPU and a 134.4 MiB lifetime peak working set;
the outer command took 16.09 s including launcher, imports and export. A
separate correctness suite was running on another CPU thread during this
measurement. The implementation hashes are unchanged between these revisions.

The tracked [historical Windows evidence manifest](research/evidence/chrono-win64-20261017.json)
retains the full scenario, command arguments and exit statuses, timing receipts,
source and engine identities, result content/receipt IDs, and SHA256 hashes of
the original output and test-report bytes. Local installation paths are replaced
by documented role bindings. These measurements precede the repair that moved
settling acceptance from exported samples to every plant boundary; the recorded
settling maxima describe the earlier sampling scope and do not verify a later
revision. The manifest preserves measurement evidence without vendoring engine
assets or large telemetry logs.

Sources and license: [Chrono evidence register](research/chrono_backend.md).
No upstream meshes, tire files, binaries or vehicle definitions are vendored;
the installed dependency supplies them. The project's licensing work is unchanged.

## Settling-clock repair checks — 17 October 2026

At source `135f6ed`, a synthetic clock fixture with a one-plant-tick excursion
at 0.751 s passed a one-second settling gate at both 10 ms and 25 ms logging.
The four retained baseline failures cover vertical speed 0.02 m/s and vertical
reaction 2% above weight; the old gate read only exported logging samples.
The repaired gate checks the plant clock without changing command or export
clocks. Four frozen before/after fixture traces, including off-grid window,
settling and final boundaries, had byte-identical commands and exported samples.
Their complete trace SHA-256 values are retained as frozen regression contracts
in `tests/test_suspension_study.py`.

On the owner's native Windows project environment, CPython 3.13.15,
`python -m pytest tests/test_suspension_study.py tests/test_simulator_flowchart.py -q`
completed with **66 passed, no skips or failures, in 5.47 s**. These lightweight
tests include all three settling limits, window endpoints, unlogged clock/NaN
rejection, dense acceptance counts and sparse export invariance. They use an
instrumented clock fixture, not surrogate vehicle physics.

At clean source `5c592654448e067d0f7ca2584f50d91a341a7e25`, all 11 actual
PyChrono checks passed with no skips or failures in 75.48 s (76.66 s outer
command). The default settling gate measured 1,001 plant boundaries; the
half-step run measured 2,001. Dense and sparse logging produced identical
settling summaries, and all six native scenarios retained exactly the earlier
commands and saved sample values. The dense maximum vertical-force error was
0.04349% of weight, within the unchanged 1% criterion.

A fresh drive command and separate-process replay also passed at that source.
The drive measured 8.32 s inside the study, 8.22 s process CPU and a 134.6 MiB
lifetime peak working set; the outer command took 9.71 s. A local WSL static
audit was active, and these timings do not establish an isolated performance
improvement or a deadline. The [plant-clock evidence manifest](research/evidence/chrono-settling-plant-clock-20261017.json)
retains exact source/configuration identities, commands and exits, receipts,
result IDs/hashes, all six comparison summaries, and the native test-report
hash. It records this source revision rather than inferring acceptance of later
implementation changes.
