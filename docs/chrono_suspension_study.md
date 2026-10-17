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
gravity precede a two-second maneuver by default. Over the final 0.5 s of
settling, vertical tire reaction must remain within 1% of total weight,
left/right axle-load difference within 1% of half the weight, and vertical
chassis speed within 0.01 m/s. A failed settling gate stops before actuation.
These are numerical fixture criteria, not calibration tolerances.

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

Sources and license: [Chrono evidence register](research/chrono_backend.md).
No upstream meshes, tire files, binaries or vehicle definitions are vendored;
the installed dependency supplies them. The project's licensing work is unchanged.
