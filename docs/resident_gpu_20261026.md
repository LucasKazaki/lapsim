# Resident RTX 5080 simulator backend — 26 October 2026

The powered plant now runs numerically on the RTX 5080: tire forces, electrical
limits, actuator lag/slew, augmented RK4, brake-stop events and spool constraints.
The original CPU driver/controller and boundary diagnostics remain on the host.
This is not WebGL, STM32 firmware, physical validation or a completed GA campaign.

## Source and supported boundaries

`resident_powered_kernel.py` shares the planar algebra in `planar_opencl.py` and
ports the existing powered/actuation equations to OpenCL C FP64. The selected
device is mandatory. Relaxed math is not enabled. `ResidentPowered` owns persistent
device buffers: state uploads once on explicit session creation; held controls
update at boundaries; all stages/events of one interval execute in one launch.
Completed lanes freeze without resetting energy or actuator state.

Supported: existing synthetic independent-motor, single-motor open-differential
and spool topologies; uniform flat grip, uniform wind/drag, declared contact radii,
10 ms or shorter intervals. Road patches/domains and configured-source export
equivalence are explicitly unsupported. Failed intervals latch an error and do
not publish an accepted partial physical state. There is no CPU fallback.

The existing cumulative work limit remains. An additional 2,048-trial per-interval
GPU watchdog ceiling rejects pathological work before a long device launch; it
does not turn an unfinished/failed case into a valid lap. No energy/SOC clipping,
post-hoc wheel projection or weakened physical constraint is introduced.

`gpu_tournament.py` synchronizes bounded host lanes at the plant boundary, reusing
the existing `rollout`, allocator, pure-pursuit driver and record schema. Driver,
controller, logger and plant clocks stay separate. The default CPU path remains
available, and an explicit CPU-step seam is regression-tested as identical.
The focused integration also exposes the previously local proportional pedal
mode and accepted-10-ms gross/recovered energy counters. Exact executed parameters
remain unrounded. Net energy already credits regeneration once.

## Executed validation

Device: **NVIDIA GeForce RTX 5080**, driver **621.01**, FP64 OpenCL. Installed
driver/runtime only; no new package, CUDA toolkit, driver or security change.

The historical [first-slice receipt](gpu_backend_20261026.json) retains the honest
force-only/hybrid measurements, including the slower hybrid adapter. It is not
overwritten by this phase. The [resident receipt](resident_gpu_20261026.json)
contains the following measured evidence and source/record hashes.

- Eight resident tests passed: topologies, regen, empty/full packs, interval energy
  headroom/shared power limits, unequal radii, near-stop events, exact counter
  parity, continuous state, changed commands, frozen finished lanes, latched work
  failures, rejected unsupported inputs and explicit session repeats.
- Three scheduler tests passed: default versus explicit CPU seam, early input
  rejection, and matched multi-lane CPU/GPU records with unequal terminal times.
- Four complete representative stadium laps passed CPU comparison: fixed/no-regen
  AWD, yaw/regen AWD, traction open-RWD and proportional-regen spool RWD. Repeated
  GPU laps produced identical saved telemetry/metrics. Real generating samples
  and recovered energy were present in the regen cases.
- One complete fixed/no-regen AWD lap on **all six courses** passed against the
  preserved hashed CPU records: five image-derived approximations and the actual
  existing fused-GNSS/IMU trajectory approximation. Maximum observed position
  difference was below 9e-14 m; work counters matched. These are synthetic model
  parity checks, not surveyed-course or physical-car validation.

Full-lap tolerances were declared before execution: lap time 1e-5 s, net energy
1e-8 kWh, energy residual 1e-5 J, pose position 1e-5 m, velocities 1e-6 m/s,
wheel angular velocity 1e-5 rad/s and command channels 1e-4 Nm. Status/validity,
logging ticks and work counters must match. These tolerances never relax the
simulator's physical validity/energy limits. Exact observed errors are in the
receipt.

The first resident build failed on an OpenCL scalar conditional and was fixed;
19 upstream GPU checks had already passed. The first four-lap report writer
failed on a relative path after all raw records were saved. Their parity was
recovered; only GPU laps were repeated for timing/repeatability, reusing CPU
references. Both failed attempts remain in local evidence.

## Measured performance

Ten continuous plant intervals (three-trial CPU/GPU medians):

| Resident lanes | Warm speedup | Including setup/build/initial upload |
|---:|---:|---:|
| 1 | 1.23× | 0.19× |
| 32 | 9.40× | 5.66× |
| 128 | 25.53× | 17.70× |

This interval benchmark excludes driver/course scheduling. It retains the driver
compiler cache and includes control upload, boundary readback, reconstruction
and parity-check work. It is not an uncached compilation benchmark.

The four representative GPU laps took **6.03 s**, including context, scheduler,
control transfers and reads. The preserved fresh CPU sequence took **15.75 s**.
Their ratio is about **2.61×**; the GPU diagnostic repeat and CPU measurement
occurred in separate processes after the report repair.

The complete six-course GPU batch took **109.18 s** including setup/scheduling,
with 17.50 s profiled device execution. Earlier accepted CPU baselines recorded
**262.52 s** in total: about **2.40×** across those different measurement times.
This is not a fresh simultaneous benchmark. Single-lane/small jobs can be slower
after setup; the default CPU backend has not silently changed.

Every main-PC numerical job used the unchanged **10 GiB admission / 8 GiB reserve**,
2 GiB allowance, 180 s outer cap and one native CPU thread. The tournament also
has a bounded internal wall allocation. Only owned jobs/resources are released.

## Reproduction

Create the normal project environment in a clean checkout, then use unique
attempt names (existing evidence is never overwritten):

```powershell
scripts/run_gpu_validation_guarded.ps1 -Phase resident-tests -Attempt UNIQUE
scripts/run_gpu_validation_guarded.ps1 -Phase tournament-tests -Attempt UNIQUE
scripts/run_gpu_validation_guarded.ps1 -Phase resident-benchmark -Attempt UNIQUE
scripts/run_gpu_validation_guarded.ps1 -Phase representative-laps -Attempt UNIQUE
```

`-PythonExe` explicitly selects an already-installed project interpreter for an
isolated development worktree. It is not a hidden runtime dependency. The optional
six-course historical comparison requires `-Phase courses-laps -BaselineRoot PATH`
with the actual hashed local records. Fresh representative laps and generated
benchmarks work without another checkout or private data.

## Remaining acceptance

The diverse seeded six-course GA and final common-pool/held-out scoring have not
run. This phase establishes its numerical backend, not a winner. Next: freeze
active architecture-aware genomes, structural policies, comparable scenarios and
search budget; evaluate complete raw time/net-energy records; keep all failures;
then select fastest, highest canonical 275+100 adapted points and least net energy
within equal valid coverage. Preserve ties and Pareto alternatives. Exact rule
formulas do not make a one-lap synthetic adaptation official endurance results.

No public website/replay data was deployed by this source PR. No physical action,
new permissions, paid services, private inputs or raw reference images are included.
