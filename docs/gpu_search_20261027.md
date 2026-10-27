# Reproducible GPU controller and regen search

This is a bounded simulation experiment on one **synthetic AWD** vehicle. It
does not identify a calibrated car controller, produce road-ready firmware, or
satisfy official endurance participation requirements. The powered plant runs
on the explicitly selected OpenCL FP64 GPU; the existing driver and controller
remain on the CPU. No CPU physics fallback is accepted.

## Frozen experiment

Seed `20261026` produces eighteen Latin-hypercube starts: each of `static`,
`slip`, `yaw`, `reserve`, `composed`, and conditional `adaptive` with each of
`off`, `two_stage`, and `proportional` regen. Four crossover/mutated children
and two independent random immigrants form the second population. Active
genomes are deduplicated; inactive genes do not count as diversity.

Every candidate runs one lap on each course, starting at the same 5 m/s,
70% SOC, grip 1.0, vehicle, driver and physical limits. The five public-map
reconstructions and existing fused-GNSS/IMU trajectory are approximations:

- `fsae_michigan_2019_image`
- `fsae_michigan_2022_image`
- `fsae_michigan_2023_image`
- `fsae_electric_2024_image`
- `fs_east_2017_image`
- `fused_gnss_imu_trajectory_approx`

Exact geometry, provenance, parameters, units, initial conditions, device,
package versions and source hashes freeze in `plan.json`. Parameters retain
full executed precision; rounded report values are for reading only. This
experiment keeps hardware fixed, so its rankings cannot compare RWD to AWD.

Up to four finalists reserve representatives for highest points, fastest and
lowest net energy before filling tie/Pareto slots; the fixed baseline is also
included. They run all six courses in each of two shared held-out grip/SOC
scenarios drawn before training. No held-out data select parents or retune
finalists. This is one bounded genetic generation, not a converged global
optimum or a universal controller ranking.

## Objective and evidence admission

Selection uses the versioned [275+100 simulated adaptation](simulated_tournament_scoring.md),
not a weighted sum of seconds and Wh. All eligible parents and children are
rescored against one common field. Final held-out scoring uses the same frozen
candidate pool across twelve matched cells. Fastest and least-net-energy
categories remain separate; one candidate may win several categories.

Missing, unfinished, invalid or unmeasurable runs cannot become a low-energy
success. Efficiency eligibility, component points, raw time, gross/net draw,
recovered energy and physical violations are retained. Net energy credits
regen once. The one-lap adaptation omits official endurance distance, driver
change, inspections, penalties and real metering; its results are not official
FSAE points. The internal fixed 1.6 m yaw-reference wheelbase matches this
synthetic fixture; variable-wheelbase studies require a separate versioned
controller correction before use.

Raw results are staged until a successful batch receipt verifies unchanged
source hashes. Ranking, breeding and finalist selection require that receipt.
Historical anchors require their original raw hashes and matching controller,
case, vehicle/actuation/driver fixture, geometry and initial conditions. The
audited importer supports a pre-selection continuation with unchanged numeric
and sampling sources; it preserves original execution hashes separately from
the new provenance verifier. A clean clone without those original raw records
evaluates fresh anchors instead of trusting a historical `all_passed` flag.

## Run and inspect

Use an already prepared project Python environment and installed FP64 OpenCL
GPU runtime. From the checkout root, create a new evidence directory:

```powershell
python scripts/run_gpu_search.py --directory work/my-gpu-search --prepare --device "NVIDIA GeForce RTX 5080"
./scripts/run_gpu_search_campaign.ps1 -Directory work/my-gpu-search -PythonExe /absolute/path/to/python.exe
```

The PowerShell launcher admits only one owned job at a time, requiring 10 GiB
commit headroom (8 GiB reserve plus 2 GiB allowance). Each job has a 180-second
outer guard and a 145-second numerical scheduler limit. The aggregate 4,800
guarded seconds include failures and carried-forward prior work. It stops on
admission failure, abort or an uncertain prior attempt. Do not weaken the
guards or relaunch a partial job blindly. Create `pause.requested` in the
evidence directory to stop before the next candidate without interrupting a
healthy active one.

Inspect `coverage.json`, each `batch-*.json`, raw `*.record.json`,
`generation-1.json`, and `heldout-pool.json`. A provisional ranking is not a
final winner. Mode occupancy, actual slip/yaw/reserve interventions and command
digests show whether a policy changed behavior. A nonbinding limit may produce
legitimate equality; different numbers alone do not establish physical fidelity.

After held-out coverage completes, the report command verifies receipts, raw
hashes, executed policies/scenarios/geometry and all raw metric summaries,
then recomputes canonical scores before writing local CSV, JSON, Markdown and
a time-energy plot:

```powershell
python scripts/report_gpu_search.py --directory work/my-gpu-search --output work/my-gpu-report
```

Reporting performs no deployment, hardware connection or public data upload.
Kernel/lap parity and measured end-to-end timings are recorded separately in
[the resident GPU evidence](resident_gpu_20261026.md); force-only timings must
not be described as lap-workflow acceleration.
