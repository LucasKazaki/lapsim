# Windows setup and unattended lite tournament readiness

Inspected source baseline: `main` at
`07ccb4b84138aedcc5b9cb85c2e81d283d6c132e` on 4 November 2026.
This guide distinguishes source inspection, software tests and actual completed
runs. **The requested unattended lite tournament is not ready to launch from a
clean public clone.** No overnight completion time or result is promised.

## 1. Which simulator will open?

| Route | What exists | Launch status for this request |
| --- | --- | --- |
| Ordinary Python desktop | `scripts/bootstrap.py`, `lapsim.desktop`, existing synthetic studies and saved-run UI | Existing startup route; no fresh acceptance run in this task; separate from lite |
| Public lite archive | `research/light/awd-standing-v15`, five kernels, manifest and registry | Source only; seven regen-OFF policies remain unqualified and ineligible |
| Portable-core PR #166 | Separate scientific package candidate and licensed FSI inputs | Open/unmerged at inspection; no driver/tournament launcher; not a runnable app |
| `lapsim.experiments.controller_tournament` | Earlier resumable synthetic search CLI | Different plant/driver/policy experiment; lacks the required activity/game/resource/lease supervisor; not an unattended lite substitute |
| Hosted tournament review/video | Bundled historical R11 replays | Displays saved history; does not launch a new tournament |

The lite target has four independent synthetic AWD torque channels and front
steering. Its seven candidates are equal torque, load allocation, slip target,
steering feedforward, yaw PI, yaw plus slip, and energy-neutral allocation. Regen
remains OFF. These are not confirmed real-car parameters. The historical
9-second development segment completed zero laps and is not a tournament result.

## 2. Clone without disturbing the existing EV work

Use PowerShell, Git and 64-bit Python 3.11+ with Tk. Obtain missing prerequisites
from the official [Git](https://git-scm.com/downloads/win) and
[Python](https://www.python.org/downloads/windows/) sites. No administrator shell,
PowerShell execution-policy change, global Git setting, AI account or hardware
connection is part of the commands below.

```powershell
git --version
py -3 --version
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents\Code" | Out-Null
Set-Location "$env:USERPROFILE\Documents\Code"
if (Test-Path -LiteralPath .\lapsim) { throw "lapsim already exists; preserve it and choose a new directory." }
git clone --branch main --single-branch https://github.com/LucasKazaki/lapsim.git lapsim
if ($LASTEXITCODE -ne 0) { throw "Clone failed." }
Set-Location .\lapsim
git remote -v
git status --short --branch
git rev-parse HEAD
```

The origin must be `https://github.com/LucasKazaki/lapsim.git`. Record the actual
HEAD; later `main` may differ from this guide's inspected baseline. Do not reset,
clean, pull over local edits or switch the active EV owner's checkout. If
`lapsim` already exists, inspect it separately or choose another new directory.

The new `.gitattributes` rule preserves `research/light/**` byte-for-byte on
Windows. An ordinary Windows checkout of the inspected baseline converted 15
of 16 manifest entries to CRLF, breaking their byte hashes. The fix preserves
the existing Git blobs and manifest; it does not normalize scientific files or
change their source identities. An old clone needs the reviewed attributes and
a separate fresh checkout; do not repair it by discarding uncommitted work.

## 3. Check the lite archive and save the answer

This command performs only bounded file/JSON/hash inspection with the Python
standard library. It does not import the simulator, enumerate processes, sample
activity/memory/GPU state, install dependencies, acquire a lease or run physics.

```powershell
$auditReport = "work\lite-source-$(Get-Date -Format 'yyyyMMdd-HHmmss-fff').json"
py -3 -I -B scripts\check_lite_readiness.py --output $auditReport
$auditExit = $LASTEXITCODE
if ($auditExit -eq 1) { throw "Source audit failed; review the error." }
if ($auditExit -ne 2) { throw "Unexpected source-audit status; stop and review." }
Get-Content -LiteralPath $auditReport -Raw
```

Expected: exit **2**, `status` **blocked**, `archive_integrity` **passed** and
`files_matched` / `files_checked` **16 / 16**. A mismatch is a stop condition;
do not edit the manifest to bless different bytes. Exit **1** means the audit or
report write failed, including an existing destination file. The report lists
the declared policy eligibility, exact hashes and missing gates. It cannot
promote qualification, resolve a review denial or authenticate a line producer.
Even changing all local eligibility flags cannot produce a ready result.

This task's audit-regression checks use only temporary source files; their
results are separate from the unrun lite/native/UI/physics tests. No audit
report is a lap result. `work/` is ignored by Git; keep local reports and private
run evidence out of commits, issues and public uploads.

## 4. Start the existing ordinary desktop

The following is the implemented ordinary desktop route, after execution is
permitted and the existing owner/resource work has been reconciled. It is not
lite setup or permission to bypass the retained EV runtime restriction:

```powershell
py -3 scripts\bootstrap.py --launch
if ($LASTEXITCODE -ne 0) { throw "Desktop setup or launch failed; read the error." }
```

Initial setup may use the internet. The script creates a checkout-local `.venv`,
installs the declared project dependencies and runs its existing synthetic
bicycle/controller replay and Tk checks before opening the desktop. Close the
window to return to PowerShell. The ordinary environment is not the lite
candidate's frozen environment. No lite package installation command is claimed.

After successful setup, repeat the ordinary checks without reinstalling:

```powershell
py -3 scripts\bootstrap.py --check --desktop
if ($LASTEXITCODE -ne 0) { throw "Desktop checks failed." }
```

Use the same `--dev` / `--environment` options if you originally selected them;
the setup marker deliberately rejects a different environment choice. For the
ordinary basic-dynamics UI, after setup:

```powershell
.\.venv\Scripts\python.exe -I -m lapsim.ui.basic_dynamics
```

Use that UI's JSON save action for a chosen local destination. An ordinary
headless example with a fresh output filename is described in the
[bicycle contract](dynamic_bicycle_contract.md); it is a separate simulation,
not an AWD tournament. Desktop startup errors are logged at
`%LOCALAPPDATA%\LapSim\logs\desktop_startup.log`. See [setup](setup.md) and
[the team guide](team_guide.md) for ordinary saved-run/replay controls. This task
has not executed these desktop commands or installed their dependencies.

## 5. Why there is no overnight launch command yet

The archive's `line_binding.py` needs an excluded `producer_receipts` dependency,
an admitted producer bundle and reviewed consumer pins. Its scientific imports
refer to a different source snapshot; adding the archive to `PYTHONPATH` or
copying it into `src` does not establish a runnable dependency closure.
[PR #166](https://github.com/LucasKazaki/lapsim/pull/166) provides only a separate
source package candidate. A clean public clone has no supported lite Run or
tournament CLI. The current native owner is repairing the original guarded
path in separate local snapshots; those snapshots are not shipped by this PR.

Automatic review previously denied live process/command-line ownership
observation and a prelaunch write before execution, citing a retained
source-only/runtime-probe restriction. That denial is unresolved. The separate
denial of merging PR #166 is also unresolved. This guide retries neither action
and introduces no alternate dispatcher, lease, observer or scheduler. Broad
authorization and successful source checks do not clear either exact action.
Use the original chat's supported exact-action review control if available;
otherwise the original chat/platform must resolve the retained restriction.

Do not turn the older tournament's soft wall budget into an overnight loop.
Its `--wall-seconds` accepts 1–900 seconds and is checked **between** rollouts,
so a rollout can exceed that wall budget. It has no required idle/game/RAM/VRAM
or original exclusive-lease supervision. Its source exposes `--resume`,
`--population`, `--generations`, `--seed`, `--profile`, `--course`, `--laps` and
`--output`, but those options do not make it the new lite tournament or supply
missing guards. No new overnight launch syntax is invented here.

## 6. Release contract for a future overnight command

These are acceptance requirements, **not implemented command-line flags or a
new resource allocation**. The final exact command must come from the reviewed,
actually qualified launcher at its published commit.

1. Resolve the original action-specific restriction and reconcile the current
   owner and owned processes. Preserve the original nonblocking exclusive
   resource lease and idle/session/game, physical/commit RAM and VRAM checks.
   Unknown/stale/failed observations must prevent launch or stop owned work.
2. Pin the source/dependency/environment identities, car/topology, course and
   authenticated line, driver, controller/plant/log clocks, start state, seven
   exact policy IDs, eligibility and failure rules. Run the complete guarded
   dependency tests, original native failure/cleanup qualifiers and smallest
   standing-start pilot first. Establish Run/progress/Stop/Close/replay/export
   behavior on the actual app; source syntax is not that evidence.
3. Freeze a finite **first development screen**: one admitted course, at most
   one complete standing-start lap per qualified regen-OFF policy (up to seven
   cells), one worker and no automatic retry, course expansion or tuning. All
   policies receive identical line/car/driver/initial conditions. Unqualified
   policies stay explicitly unrun. Hold-out courses/scenarios stay unopened.
4. Before launch, the original owner must issue a fresh finite allocation with
   numeric per-attempt/whole-session wall, simulation-time, step and output-byte
   bounds, plus an absolute UTC cutoff. Choose those from measured pilot
   throughput and the original guards; no safe numeric overnight allowance can
   be inferred from zero full laps. The original cutoff/return/game condition
   takes precedence. Do not reuse retired reservations or silently extend a
   limit. A hard watchdog must contain a stuck rollout, reader or cleanup path.
5. Save the immutable manifest/config, append-only attempt/progress journal and
   raw record for each finished, failed or partial cell. Write checkpoints at
   declared boundaries with crash-consistent replacement and verified hashes;
   reserve output space for failure/terminal/cleanup records. A terminal summary
   must distinguish completed, paused-budget, stopped-by-guard, cancelled,
   failed and unrun cells. Export exact JSON and projected CSV plus a verified
   replay/plot when supported. Never substitute a historical replay for a run.
6. Stop on user return/use, game, cancellation, guard/lease loss, stale observer,
   memory/output limit, deadline, numerical/domain failure or uncertain owned
   cleanup. Cleanup may terminate only verified owned children. A failed reader
   join/handle closure must retain the original blocked/fatal state until
   explicit reconciliation; exit alone does not establish safe cleanup.
7. Resume only through that same guarded entry point, with an admitted fresh
   allocation and matching source/config/environment/line/checkpoint identity.
   Preserve earlier raw evidence, debit failed attempts and do not repeat
   completed cells or redraw random candidates. Freeze development selection
   before held-out evaluation; no winner until required eligible coverage and
   independent results verification complete. Schedule support is separate
   from a working launcher and never guarantees continuous compute.

No sleep/power/security/network/ACL change, app termination, new background
job or additional scheduler is needed for the source audit. A sleeping,
restarted or powered-off PC cannot be promised to finish a simulation.

## 7. Where results are saved, and what to check in the morning

| Artifact | Actual current location / meaning |
| --- | --- |
| Source audit | The exact `$auditReport` path under this checkout's `work/`; blocked readiness evidence only |
| Ordinary UI JSON | The filename chosen in that study's Save dialog; verify reopening/replay in the same study |
| Older synthetic tournament checkpoint | Its `--output` directory / `checkpoint.json`; embedded raw runs, config/source fingerprint and status; not a lite result |
| Older synthetic tournament replay | Same directory / `replay.json` and `replay-data.js`, written at export boundaries; can lag a checkpoint after a crash |
| New guarded lite campaign | **No public supported run/output directory yet.** The reviewed launcher must print and persist its exact absolute output path before admission |

To read a particular **older** saved checkpoint without importing or restarting
the simulator, use its actual path:

```powershell
$savedCheckpoint = 'work\tournament-4082025\checkpoint.json'
if (-not (Test-Path -LiteralPath $savedCheckpoint)) { throw "No saved checkpoint at that path." }
$savedState = Get-Content -LiteralPath $savedCheckpoint -Raw | ConvertFrom-Json
$savedState | Select-Object schema,status,fingerprint,best_so_far
```

That default path comes from the older CLI and may be absent. `completed` means
that search exhausted its planned cases; it does not prove all runs were eligible
or that the newer lite work completed. Inspect failures, coverage, held-out
selection and raw hashes. `paused_budget` requires a separately permitted,
matching resume; `no_eligible_parent` is not success. Do not overwrite a saved
directory with another seed/config or upload its raw private evidence.

For a future lite run, the morning procedure is to open the printed output
directory, read the terminal status and cleanup receipt, check per-policy
coverage/failures and saved raw hashes, and replay the accepted records. If the
terminal/cleanup record is absent, treat the outcome as interrupted/uncertain
and retain the evidence. There are presently no new lite results or winners to
retrieve from this documentation task.
