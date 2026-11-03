# Light simulator: reviewed research source snapshot

Status: **archival source for review, not an executable release**. This directory
preserves the seven-policy standing-start AWD candidate and five coupled-plant
kernels without changing the repository's active package or any accepted run.
No import, unit test, solver, simulation, browser or desktop acceptance was run
for this publication. These files must not be advertised as a working app.

Start with the [technical master](../../docs/EV_SIMULATOR_MASTER.md),
[source manifest](SOURCE_MANIFEST.json) and [development status](STATUS.json).
The detailed mechanics/CFD work has its own
[full-simulator namespace](../../docs/full-simulator/integration-plan.md).

## Contents and limits

- `awd-standing-v15/` contains byte-preserved candidate policy, synthetic AWD
  configuration, gate, bridge and geometry/line-generator source.
- `kernels/` contains the coupled DRS, common thermal, force, powered and combined
  plant modules from the scientific source snapshot. Their relative imports
  refer to that snapshot's `lapsim.dynamics` package; this folder does not
  replace that package or establish dependency equivalence with public main.
- The snapshot uses Python. The geometric proposal code calls SciPy/SLSQP only
  when explicitly invoked by a separate producer. It is not an implementation
  of TUM's IQP, and a screened or nonconverged candidate is not an optimal line.
- Tests depending on external track checkouts or historical checkpoints are
  excluded. No passing tests are claimed for this public archive.

The original bridge needs separately reviewed physics/course modules and an
externally authenticated line-producer bundle. Those dependencies are deliberately
not replaced with stubs or silent centerline fallback. `line_binding.py` therefore
has unresolved receipt-module/data prerequisites in this public archive. Its
source is included to make that trust boundary inspectable; it is not a launch
entry point. Do not add this archive to an execution path and infer qualification.

The original maintained checkout contains other module versions than current
public main. Copying these files into `src/` would change scientific identity
and require dependency closure, fresh source review and affected qualification.
The preserved source hashes in the manifest are archival identifiers; they do
not confer runtime approval or recreate the original environment.

## Seven candidate techniques

All entries use the same synthetic **four independently commanded AWD motors**,
front steering, common driver/brake authority and regen OFF. Source support is
not verified team hardware or completed coverage. Four refers to motor channels;
the registry contains seven policy candidates.

| Candidate | Source intent | Standing-start completed laps in current lineage |
| --- | --- | ---: |
| Equal torque | Equal shares of the common total request | 0 |
| Load distribution | Allocate with estimated normal loads | 0 |
| Slip target | Limit modeled wheel slip toward a target, not literal zero slip | 0 |
| Steering feedforward | Steering-dependent yaw allocation | 0 |
| Yaw PI | Yaw-error feedback allocation | 0 |
| Yaw plus slip | Combine yaw layer and slip limits | 0 |
| Energy-neutral allocation | Provisional convex motor-loss surrogate, not proven lap efficiency | 0 |

The latest audited equal/OFF development segment is 9.000 s simulated,
43.917 m source-track progress and 3.168 Wh net depletion. It is partial,
low-cruise development evidence, not a competitive lap, calibrated prediction,
comparison, official score or winner. The old producer's missing exact initial
guard sample and unproved startup-environment equivalence remain open. Current
source registry qualification flags remain UNRUN/not campaign-eligible.

Regen variants remain excluded pending the low-speed lag/cutoff, charge-acceptance
and friction-authority questions. Historical RWD campaigns and flying-start laps
remain separate. No held-out data were used for this publication. Official
endurance/efficiency points are pending applicable distance, eligibility,
penalties, rules and a frozen reference field; no linear 275:100 score is invented.

## Excluded material and next gate

Machine-specific supervisors, process inventories, resource/lease receipts,
tool transcripts, credentials, private images/team telemetry, private TTC data,
third-party tire calibration files with unverified redistribution rights and
line artifacts carrying local provenance paths are excluded. No upstream
optimizer, numerical package or course dataset is vendored here. A later course
data publication must preserve its original license and provenance.

The latest qualification attempt stopped before process creation at an automatic
review denial of its process-ownership observation. No test or new lease followed.
This publication does not clear that restriction. A supported action-specific
approval, a fresh finite allocation and valid pins/certificates, followed by the
original actual activity/session/game/memory/lease guards and owned cleanup,
remain necessary before execution. Retired ledgers cannot be reused.

After that gate is resolved: qualify the complete dependency/receipt path,
complete one matched standing-start lap per eligible technique on the same
admitted line/course, then assess convergence and time/energy/scoring coverage.
Run/progress/active Stop/Close/replay need their own actual app acceptance;
headless HTTP checks do not establish browser or desktop-button behavior.
