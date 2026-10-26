# RTX 5080 numerical backend checkpoint — 26 October 2026

Actual GPU numerical execution is implemented and tested for planar force batches
and hybrid powered plant intervals. **The full tournament/GA is not GPU-enabled.**
No GPU full lap, search generation or new winner is claimed at this checkpoint.
The earlier CPU screening remains paused at 118 valid / 180 planned runs.

## Implemented interfaces

- `src/lapsim/backends/opencl_runtime.py`: explicit GPU selection, installed
  system OpenCL loader, FP64 requirement, bounded buffers, checked return codes,
  program build, kernel event profiling and owned resource release. No install,
  global context or CPU fallback.
- `src/lapsim/dynamics/planar_opencl.py`: one GPU work item per independent state;
  all 89 SI outputs of `evaluate_planar_dynamics`, including tire force limits,
  steering-frame slip, wind/aero, friction braking and mechanical energy balance.
  Nonuniform road lookup uses the original road object on the host. Uniform-road
  packing has an exact fast path. Typed output reconstruction is regression-tested.
- `src/lapsim/dynamics/powered_opencl.py`: cooperative batches of 1–256 held-command
  intervals. Planar forces run on the selected GPU. Electrical limits, actuator
  slew, adaptive RK/event decisions and the original spool reaction helper run
  on the CPU. The original CPU plant/controller sources remain unchanged.

These are synthetic simulation interfaces, not portable STM32 firmware or
physical validation. A requested unavailable device raises an error. Reverse
states in the planar algebra tests are qualitative model checks; the powered
domain continues rejecting reverse wheels. Invalid road-domain stages are
explicitly rejected by the hybrid backend.

## Measured acceptance

Device: NVIDIA GeForce RTX 5080, driver 621.01, OpenCL 3.0 CUDA / OpenCL C 1.2,
FP64 supported. This is OpenCL numerical computation, not WebGL rendering.

Final actual-device command:

```powershell
scripts/run_gpu_validation_guarded.ps1 -Phase tests -Attempt typed-output-final
```

**42 passed, zero skipped**, including existing planar/powered CPU regressions,
all-field CPU/GPU parity, deterministic repeats/reordered lanes, parameter wiring,
zero contact/grip, road boundaries/patches, wind, unequal radii, AWD/open-RWD/spool,
regen, empty/full packs, brake stops, state carry and invalid-input/work rejection.
The initial combined run had 39 passes and one incorrect test expectation: a
valid one-trial allocation was expected to fail. The corrected test consumes that
allocation first and independently verifies rejection by both backends. That
failed record is retained, not relabeled as a solver defect or deleted.

Three-trial medians, including host packing, allocation, transfers, readback and
resource release (higher speedup is better):

| Force rows | CPU median | GPU end-to-end median | Speedup |
|---:|---:|---:|---:|
| 1 | 0.0478 ms | 0.5036 ms | 0.095× |
| 32 | 0.9317 ms | 0.6769 ms | 1.38× |
| 512 | 13.968 ms | 4.462 ms | 3.13× |
| 8192 | 224.983 ms | 65.256 ms | 3.45× |

New-context/program-build initialization took 101.8 ms; the existing driver
compilation cache was retained. This is not an uncached compiler benchmark.
Including that initialization once, rather than ignoring it, is recorded in
each benchmark's `new_context_one_batch_speedup`.

All 89 fields passed `abs_error <= 1e-8 + 1e-10*abs(reference)` across the seeded
varied-state batches. This allows FP64 transcendental/reduction roundoff, not a
relaxed physical constraint. Re-evaluating 512 saved states from each of six
hashed baseline records (3,072 total) passed; maximum error was 3.64e-12 in the
mixed-unit output table. These are instantaneous checks, not six new GPU laps.

Complete 10 ms powered intervals did **not** show a speedup:

| Lanes | CPU median | Hybrid speedup |
|---:|---:|---:|
| 1 | 1.529 ms | 0.118× |
| 32 | 84.803 ms | 0.872× |
| 128 | 358.614 ms | 0.967× |

All state/energy components matched within the same numeric tolerance; maximum
observed difference was 8.88e-16 and event/work counters matched exactly in
these probes. A 128-lane interval used 25 launches and about 0.833 ms of profiled
device execution, versus about 0.37 s wall time. Host-side limits/events,
serialization, object conversion and repeated stage transfers dominate this
adapter. The force-kernel speedup must not be advertised as a lap speedup.

The unchanged guards admitted each job with about 12.8–13.3 GiB commit headroom,
retaining 8 GiB reserve plus 2 GiB job allowance, 180 s cap and one native CPU
thread. All validation jobs exited and released their owned GPU contexts.

## Reproduction and evidence

The compact [receipt](gpu_backend_20261026.json) retains measured trials, parity,
source/record hashes, explicit scope and guard outcomes. Raw local evidence is
under `work/gpu-readiness-20261026/`; earlier failed/slower attempts are retained.
Generated fixtures are self-contained in a clean source checkout; saved-course
sampling requires the explicitly requested local baseline records and fails if
they are missing or their hashes differ.

```powershell
scripts/run_gpu_validation_guarded.ps1 -Phase benchmark -Attempt NEW-UNIQUE-NAME
scripts/run_gpu_validation_guarded.ps1 -Phase powered-benchmark -Attempt NEW-UNIQUE-NAME
```

For an independently guarded external workflow, `benchmark_planar_gpu.py`
supports `--device "NVIDIA GeForce RTX 5080" --output NEW.json`; its optional
`--saved-course-samples` enables the local hashed-record check. The provided
PowerShell wrapper always requests that evidence in this workspace.

## Next integration dependency

A useful GPU GA needs batched controller/course scheduling and long-lived device
state, then migration of the powered stage/constraint/event work to reduce the
measured host bottleneck. It must preserve pack bounds, brake-stop dissipation,
shared-motor limits, spool equal-angular-speed reactions and independent clocks.
No simpler tire model or post-hoc state clipping may substitute for those rules.
The current adapter is available as a correctness reference for that work.

Before a GPU-labelled search: compare complete representative laps and failure
cases with CPU, benchmark complete batches, freeze a diverse architecture-aware
population/seed and fixed scoring references, and reserve untouched scenarios.
Then apply the canonical versioned 275+100 scorer to common valid six-course
coverage, retaining separate fastest/highest-points/least-net-energy views and
ties. No such generation or final held-out evaluation has run here.

The current lack of end-to-end acceleration is an implementation gap, not a
permission, credential, hardware-driver or missing-team-data blocker. No new
runtime was installed. Official scoring prerequisites and physical calibration
remain separate from the synthetic one-lap scoring adaptation.

The flowchart inventory commands named in the older implementation plan are
absent from this local implementation branch; attempted checks could not run.
Regenerate the public inventory in its owning integration worktree when this
slice is transplanted, rather than claiming those checks passed here.

OpenCL API/arithmetic reference: [Khronos OpenCL C specification](https://registry.khronos.org/OpenCL/specs/unified/pdf/OpenCL_C.pdf).
