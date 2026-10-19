# ENME408 implementation and team-delivery plan

Updated: **18 October 2026**. Tracking: [issue #19](https://github.com/LucasKazaki/lapsim/issues/19).

**Status, 16 October implementation:** the consolidated main baseline includes
the controller source closure, source/resource repairs and the real dynamic
bicycle. The constrained control/native C/virtual STM32 and installed-package
tranche merged through PR #51 at `efc9095cecab5e812423fe781439e4a3b91715f7`
and was reproduced from merged main. E15 adds the standalone
component study described in [its guide](docs/component_study.md). Check the live
PR/issue state before treating a candidate as merged. Public release and site
deployment are deferred by the owner; physical PIL remains unavailable. The
contracts below retain the acceptance work and staged future scope.

## Active local native-backend cycle (16–18 October 2026)

The owner's new continuous engineering request supersedes the completed window
below. The old coordinator released its lease and its scheduler remains paused;
no new scheduler is required for the active chat. Current main was refreshed at
`139a02fca52aaf6b0fb7ad9d8963e5dc74177d8a` before branching. Existing licensing
PRs are separate work and are not incorporated by this feature.

The record-I/O repair (#84) and source-inventory performance repair (#85) are
now merged through `c3008c2`. Their combined native-candidate tree passed all
88 Windows test modules (2,165 reported cases, zero failures/errors, one
POSIX-only skip); that compiler regression passed separately on local WSL.
E16's 11 actual native checks and the local static/security gate also passed.
Installed wheel/sdist/source-bootstrap, actual portable executable, and browser
accessibility gates passed at `135f6ed`. The fresh native setup/export/replay
path was reproduced after selecting the project cache through
`MAMBA_ROOT_PREFIX`.

A subsequent counterexample showed that decimated logging could hide a one-tick
settling excursion. The repaired gate measures every plant boundary in the
final half-second, with unchanged thresholds and exported telemetry. At clean
`5c59265`, 66 focused checks and all 11 actual native checks passed; all six
native scenarios retained identical commands and saved samples, and a fresh
export replayed in a separate process. Tracked evidence manifests are linked
from [the native guide](docs/chrono_suspension_study.md). The bounded headless
E16 increment merged through [PR #87](https://github.com/LucasKazaki/lapsim/pull/87)
at `4cd6c7552d640c9af23a956dce8d90f097c3eaee`; team geometry, calibration and
compliance remain open. The separate
[CLI follow-up #92](https://github.com/LucasKazaki/lapsim/pull/92) merged normally
as `2ac6d4dfd519d63bc1913551d83e678c33c79116`; the
[saved-record inspector #93](https://github.com/LucasKazaki/lapsim/pull/93) merged
normally as `6e7a215debfc38533241e98dea144b95a78687d1`. These follow-ups remain
outside #87's numerical acceptance scope.
The separately reviewed replay-cancellation repair passed all 88 Windows
modules and local WSL static/POSIX gates at `8e60ba1`, then merged through
[PR #86](https://github.com/LucasKazaki/lapsim/pull/86) at `a68eaa1` after the
acceptance update in [PR #89](https://github.com/LucasKazaki/lapsim/pull/89).
Those cancellation checks remain distinct from E16's numerical claims.

The E16 desktop viewer opens validated saved native records through the
Four-wheel lab. It selects exact exported samples,
plots recorded COM/wheel-center points, spring lengths and force channels with
their own source clocks, and preserves the inspector's historical-source and
stored-claim distinctions. Its focused desktop checks are separate from native
physics and portable-package acceptance; it introduces no new vehicle model,
record schema, native dependency or physical-device connection. The existing
desktop self-test now checks an empty viewer and optionally a supplied external
record, keeping absent saved-record scope explicit. The source window and
copied package require separate workflow checks.

The viewer and CSV projection share an exact saved frame/unit claim check before
using fixed world-frame and SI labels. Rejection clears plotted and selected
telemetry, identity and result actions while keeping Open available. Supported
historical source mismatches and unavailable source files remain viewable; the
reader, inspector, native replay scope and numerical code stay unchanged.
Acceptance covers independently resealed unsupported claims, bounded feedback,
input preservation and supported reload, with actual installed and copied
runtime checks kept separate from source-window tests.

Local acceptance at clean `caa51fa` is recorded in the
[viewer frame/unit receipt](docs/research/evidence/chrono-native-viewer-claims-20261017.json):
86 focused checks and a fresh 98-module Windows sequence passed (2,445 reported
JUnit cases, 1,435 raw testcase elements, one expected POSIX-only skip). That
compiler case passed separately on local WSL. One evidenced pre-existing Tcl
lifetime warning remains unresolved. The failed earlier GUI-fixture run is
retained; only its world/SI claims and independently derived IDs changed for the
successful fresh run. Installed, browser, source-map and copied-executable
checks have their own recorded scope. The ZIP's older bundled full-suite report
is outside that source acceptance; the separate build-owned verification
follow-up below records its repair and later normal integration.

PR #108's first hosted native shard later failed an unchanged initial-load wait.
The test-only follow-up at `829df7d` removes the fault-injection fixture's
instance-bound method cycle while preserving assertions and waits. A fresh
86-case focused run and 98-module Windows sequence passed with the same full
counts and expected skip; the comparison viewer's Tcl warning remains open.
The [follow-up receipt](docs/research/evidence/chrono-native-viewer-fixture-20261017.json)
retains the failure and independent local checks without attributing its cause.
Runtime code and the earlier installed/browser/frozen acceptance scope remain
unchanged. The follow-up merged normally through
[PR #109](https://github.com/LucasKazaki/lapsim/pull/109) at `1153e7c` after all
16 exact-head hosted checks passed; #108 is closed as superseded. On merged
main, all 21 source desktop self-test checks and the genuine/alias/frame/units
process exits 0/2/1/1 passed, with the original record and source preserved.
This adds no fresh native solver or calibration claim.

E04 builds retain persistent build-owned suite reports and sanitized logical
verification receipts. Actual normal full and skipped builds passed at
`cb3720b`; the full build produced 98 reports, 2,455 reported / 1,445 raw cases,
zero failures/errors and one expected POSIX-only skip on Windows. Each build
passed 20 original and 21 copied smoke checks plus the valid-record, alias
and two unsupported-claim commands (exits 0/2/1/1). Test-only successor
`7ead724` passed all 18 focused contracts; final four-file quality against
main `1153e7c` introduced no type/broad diagnostics, with critical, checker
formatting and mapped security checks passed. Existing debt and coverage
limits remain. The [compact build evidence](docs/research/evidence/portable-build-verification-20261017.json)
binds actual source identities and preserved failures; those focused checks
do not rebuild the `cb3720b` artifacts. Tests precede inventory generation,
so tested and packaged identities remain separate. The prior stale attachment
and historical Tcl warning retain their original scope; sanitized JSON does
not sanitize exact JUnit or its ZIP, and no release claim is made.

Build-owned verification excludes only its fresh leaf from source status,
preserving other tracked/untracked dirtiness. At measured runtime `6ed6153`,
actual full and separate skipped builds passed, each with 20 original and 21
copied checks plus supported-record/alias/frame/units exits 0/2/1/1. The full
build produced 98 reports, 2,467 reported / 1,457 raw cases, zero failures/errors
and one expected Windows POSIX-only skip; the skipped build attaches no suite
XML or totals. Thirty focused contracts include 12 real-Git cases retaining
the genuine-dirty controls.
The [build receipt](docs/research/evidence/portable-build-verification-20261017.json)
preserves the [PR #110 finding](https://github.com/LucasKazaki/lapsim/pull/110#discussion_r4303845080),
four red failures and failed style gate alongside passed targeted/global
quality, existing debt and security warnings. Full pytest had no warning-summary
blocks; PyInstaller's existing hidden-import warning is separate and the
historical Tcl cause remains unresolved. The normal successor
[PR #111](https://github.com/LucasKazaki/lapsim/pull/111) merged at `13076f6`
after 14 exact-head checks, with the complete tree equal to accepted `9bb6338`.
Thirty post-merge contracts and all three source-map entrypoints passed; the
separate local packaging acceptance record binds those checks. Artifacts retain
`6ed6153`, separate from later documentation heads; raw JUnit privacy and
release limits remain.

A separate E04 follow-up at `5466c65` rejects output equal to or below
resolved `ROOT/build/assets`, for full and skipped builds, with exit 2 before
output/evidence creation or test/generator/staging work. Four retained RED cases
became 34 passing focused contracts with the old 30 unchanged. Targeted four-file
quality has zero new type/broad findings against fixed `1153e7c`; critical,
checker format and mapped security passed, with existing debt retained. The
normal build completed 99 fresh reports (2,491 reported / 1,481 raw cases,
zero failures/errors, one expected POSIX-only skip on Windows). Full and separate
skipped builds each passed 20 original and 21 copied checks and command exits
0/2/1/1; skipped verification attaches no XML or suite totals. Full
and skipped-build independent preservation reviews passed.
All three map entrypoints passed. The [dated receipt](docs/research/evidence/portable-output-assets-20261018.json)
keeps the artifacts and limits distinct; original `a582eda` global/POSIX evidence
is reused only for unchanged scope. Artifacts retain `5466c65`; no new native
physics. Normal integration and post-merge verification are tracked separately
in [issue #19](https://github.com/LucasKazaki/lapsim/issues/19).

The engine-free saved-pair API/CLI merged normally through
[PR #99](https://github.com/LucasKazaki/lapsim/pull/99) at `591728b` for declared
plant-step or logging-period comparisons. It checks recorded physical/source
compatibility, keeps exact observation and force clocks, and reports endpoint
differences or shared/unmatched exports. A named saved-fixture endpoint criterion
is a calculation on recorded claims, separate from native acceptance, replay,
historical timing or vehicle calibration. The existing native record schema and
three implementation-file replay hashes remain unchanged.

The separate provenance follow-up merged normally through
[PR #100](https://github.com/LucasKazaki/lapsim/pull/100) at `0f6cff9`, adding
comparison-specific recipe, calculation and complete-receipt identities.
Its seven-file source scope is
explicitly limited; missing files remain unavailable. Historical timing stays
outside the calculation identity and inside the full receipt. This follow-up
changes neither native replay identity nor the physical/criterion calculations;
its pure saved-fixture checks are separate from native and package acceptance.

Plant-step endpoint reporting requires the exact recorded world/SI claims used
by the passive viewer and CSV exporter before doing endpoint arithmetic.
Matching unsupported labels produce role-labeled incompatibility reasons and
no numerical result; equal opaque labels remain supported for logging's raw
timestamp/equality comparison. The current recipe retains those original seven
source files and adds the shared exporter guard as an eighth, changing new
recipe/calculation/receipt identities without rewriting historical reports or
the seven saved native records. Native-three replay identity, physical-claim
fingerprint and numerical criterion limits remain unchanged.

The [claim-eligibility receipt](docs/research/evidence/chrono-native-comparison-claims-20261018.json)
separates the isolated 71-case red/green contracts from combined candidate
`a582eda`: 96 focused checks, a fresh 99-module sequence (2,487 reported / 1,477
raw cases, one expected Windows POSIX-only skip), targeted five-file quality
and the original global/inventory gates passed. The compiler case passed on
local WSL; existing debt and structured security warnings remain in the receipt.
Five ordinary saved-pair CLI routes also passed with their expected exits.
The earlier `ecca1b3` attempt retains seven opaque plant-step presentation-fixture
failures; their setup-only correction preserves assertions and opaque logging
controls. At the same source, both installed wheel and source-distribution
formats passed 538 reference cases, 13 saved-pair cases, three saved-record CSV
conversions and all five comparison CLI routes with expected exits. The earlier
`6ed6153` executable checks remain a separate scope. Normal
[PR #112](https://github.com/LucasKazaki/lapsim/pull/112) merged at `cb91a82`
after 16 exact-head checks, with the complete tree equal to accepted `944d19e`.
On merged main, 96 focused checks, five genuine CLI routes and all three map
entrypoints passed; their separate local API acceptance record binds those results.
Installed archives retain `a582eda`; this adds no fresh native solver claim.

A further E16 follow-up exposes the saved-pair API from the existing native
record viewer: one explicit-kind/second-file review window, read-only
summary/details and unchanged primary sample/force inspection. At `86ba320`,
154 focused source checks and 13 independent genuine-record/error/ownership
cases passed, with four actual Tk layouts reviewed. Initial focus and missing
radio-arrow failures remain retained in the earlier focused receipt. A later
source audit at `12136d3` retained one new optional-JSON type diagnostic; the
explicit non-None capture/guard repair passed the same source checks at
`86ba320`, without changing tests or the genuine-record helper. Normal PR #101
is merged at `6312e8b`; its complete tree equals accepted `c816018`. The local
copied-EXE saved-pair workflow and postmerge CLI/identity checks passed.
Installed/frozen and broader gates retain their separately recorded scopes in
the reviewed change and canonical issue. No native run/replay path, paired
cursor, model or QA flag is added.

The E16 native acceptance suite now includes a seventh scenario and a
twelfth check for settling/final exports between controller and logging ticks.
The actual noncoincident-clock experiment and separate normal CLI replay passed
at `6312e8b`. The maintained suite subsequently passed at clean source
`6a4b7da625b8cffc62c55a6fe764b2926286e53e` in the pinned native environment:

```powershell
python -m pytest quality/test_chrono_native.py -q --junitxml=work/detailed-study/chrono-native-6a4b7da.xml
```

All 12 checks passed, with zero failures, errors or skips: 71.82 s pytest time
and 72.69 s outer guarded-command time. The XML is
`work/detailed-study/chrono-native-6a4b7da.xml`, SHA-256
`bf8b8cadef71a9dcefdff01c2c542693e7996a7f8fb925e864da26a850cacea3`.
The [durable verification manifest](docs/research/evidence/chrono-noncoincident-clocks-20261017.json)
retains measured cases, identities, commands and raw-file hashes. The ignored
`work/detailed-study/native-full-6a4b7da-independent-proof.json` remains a local
raw-evidence binding.
Normal PR #103 subsequently merged as `8802edf`, with the accepted manifest
and its historical suite/observer scopes retained.

The bounded CLI extension exposes all nine existing scenario settings in
the normal command, with seven additional flags and no new input schema. It
counts every regular and forced settling/final export against the unchanged
2,001-sample limit before native initialization. Explicit fresh-study flags are
rejected in replay/inspection modes; defaults and saved-scenario authority remain
unchanged. The retained regression baseline at `eb52ef2` reproduced 33 expected
failures with 103 passing cases. Unchanged assertions then passed 136 checks at
`bc504d5`, which also passed the 12 native checks and configured CLI/replay. At
the inventory-only `1129238` candidate, all 97 ordinary module processes, the
WSL audit/POSIX case, installed wheel/sdist workflows, browser checks and frozen
single-record/alias checks passed within their recorded scopes. The normal
main-ancestry merge `4bccac1` preserved all `1129238` runtime/test/catalog bytes;
fresh normal comparisons there reproduced the installed wheel/sdist IDs. The
[CLI evidence manifest](docs/research/evidence/chrono-native-cli-20261017.json)
retains counts, commands, source identities, hashes and coverage limits.
[PR #106](https://github.com/LucasKazaki/lapsim/pull/106) merged normally as
`9e4468c` after all 16 hosted checks passed. Separately guarded postmerge native
CLI/replay and saved-pair checks passed in 17.14 s and 2.59 s, respectively;
these elapsed times describe verification jobs, not performance benchmarks. Editing
the existing study module changes its strict three-file replay identity; old
over-budget scenarios may fail current validation, and historical fixture/criterion
evidence must not be relabeled.

The passive native CSV handoff accepts an explicitly supplied validated saved
record and an output path. Its fixed 100-column table groups metadata, samples
and controller events in their stored order, preserving distinct state/force
origin clocks, null origins, completed-interval commands and new event requests.
Recorded model/source/execution claims and supplied inspection statuses remain
read-only context, not attestation, replay, calibration or physical validation.
Unsupported frame/unit claims are rejected before atomic destination replacement.
The tests-only baseline at `2a6069c` retained 41 missing-module setup errors.
The pre-repair `8796e1a` run passed those 41 cases and failed only the two new
path-resolution contracts; the repair at `3823d37` passed all 43 focused cases
with zero failures, errors or skips. At `7eaf99f`, genuine seven-record conversions
passed an independent 100-column oracle across 7,831 data rows (783,100 cells).
The full 98-module observed run passed: 2,439 reported JUnit cases, 1,429 raw
case elements, no failures/errors and one expected POSIX-only skip on Windows; the
separate WSL POSIX compiler case passed. The unchanged type budget, critical
lint, security, inventory and all three static-map entrypoints passed with
existing broad debt, two advisory test-style findings and scan limitations retained.
Browser checks covered four
layouts, 12 accessibility states and 10 focused cases; 36 incomplete accessibility
entries still require manual review. Both installed formats passed three CSV
conversions and two alias rejections each, with CSV bytes matching source exports.
The first package attempt stopped at the unchanged commit-headroom guard; the
complete fresh second attempt passed. Existing copied-executable single-record
and alias checks also passed; there is no CSV UI or frozen CSV command. The
[CSV verification receipt](docs/research/evidence/chrono-native-csv-20261017.json)
binds these distinct scopes and the stopped attempt. Normal integration and
post-merge verification are tracked separately in
[issue #19](https://github.com/LucasKazaki/lapsim/issues/19). Historical native/CLI
evidence is linked without claiming new physics.

E16's smallest increment is a headless, explicitly synthetic native suspension
and rear-driveshaft study. The engineering user needs reproducible gravity
settling, handling signs, suspension/contact telemetry and timestep comparisons.
Inputs come from the pinned official PyChrono 10.0.0 synthetic Sedan, with an
explicit upstream shaft-brake variant; they are not Formula SAE measurements.
Chrono alone owns physical state, while an integer-tick runner holds driver
requests and logs cached tire-force timings. The existing fast models remain
available. Native physics runs on the verified local Windows PC CPU; no GPU
physics is inferred from installed CUDA dependencies.

Acceptance requires actual native equilibrium/symmetry, torque/steering signs,
adjacent-step sensitivity, logging invariance, reset, cancellation and checked
replay; plus the applicable stable-tree repository checks and independent review.
Failed short-settling, Simple-brake and mismatched tire-clock attempts remain
local evidence. Do not widen tolerances or call this physically validated.
The [native guide](docs/chrono_suspension_study.md) and
[source register](docs/research/chrono_backend.md) explain the model boundaries.
Restart state and bounded local evidence are in ignored
`work/detailed-study/checkpoint.json`. Check `work/detailed-study/STOP` before
each job. Public release, site deployment and physical hardware remain outside
this cycle. Team geometry/correlation, full powertrain limits and presentation
expansion follow the accepted headless increment.

## Completed overnight implementation window (16 October 2026)

Start: **2026-10-16 00:56:04 America/New_York**. Fixed cutoff:
**2026-10-16 09:00:00 America/New_York**. Resumes retain this cutoff.
Issue #19 remains the coordinator. Local restart state is kept in the ignored
`work/overnight/checkpoint.json`; an OS file lock prevents overlapping writers.
Check its live owner before reclaiming it. The hourly chat continuation is an
implementation worker in the same local checkout, conditional on the app and
computer remaining available. Its first scheduled execution must be observed
before claiming that the scheduled worker actually ran.

The expanded team scope uses the next unused IDs, after E01–E14:

| ID | Bounded deliverable | Prerequisite / acceptance |
|---|---|---|
| E15 | Material/geometry cards and an analytic beam/shaft study | After integrated bicycle/controller baseline; SI units, provenance, uncertainty, boundary conditions, hand calculations, mass/inertia; keep stiffness separate from lap predictions |
| E16 | Native synthetic suspension/control slice, then team geometry/compliance | Accept one reproducible native fixture first; verified team geometry remains a separate requirement for team-car studies |
| E17 | Imported aero-map validity slice | Declared axes/reference area/interpolation domain and source permissions; no invented CFD |
| E18 | Battery/thermal derating slice | Reuse existing power/energy ownership; version thermal assumptions and verify balances; no invented temperature correlation |
| E19 | Shared subteam examples and technical case study | Shared configuration IDs, solver/source revisions, runnable commands, actual evidence and unavailable-capability labels; held-out correlation follows authorized data |

Evaluate optional Chrono, CalculiX and FMI/OpenModelica routes only against a
specific ready benchmark, license, Windows/headless support and installation
burden. Keep heavy tools outside basic startup. Composite studies require
layup/orientation/core data; an isotropic material selector is insufficient.

## 1. Project decisions and boundaries

Lucas's requested deliverable is one team-facing repository containing the simulator, portable controller source, synthetic test cases, build instructions, tests, documentation and release assets. A teammate must not need Lucas's desktop, Agent Studio, another project checkout, API keys, an AI subscription, or private team data to run the baseline demonstration.

Recorded project facts supplied by Lucas:

- The current **2026–27 car is RWD**. The **2027–28 AWD car is a future configuration**, not the current validated plant.
- The recorded controller platform is an **STM32F405 on the team's custom PCB**. Keep that direction; do not migrate to Teensy.
- **No new information has arrived from the team/Slack as of this update.** Exact MCU suffix, PCB revision, clock configuration, pinout, firmware, signal definitions, independent actuator count and final vehicle parameters remain unresolved.
- The immediate goal is electronic differential/torque-control research: understand driver demand, achievable total force/torque, allocation and vehicle response. Autonomous driving, full game-like driver simulation and new CFD/chassis-flex work are not prerequisites.
- Synthetic assumptions may support software experiments now. They must be named, versioned and distinguishable from measured or approved car data. Unknown values remain unknown; zero must not stand in for missing information.

The public repository and the private evidence store are different things. Keep authorized source and synthetic fixtures self-contained here. Do not publish restricted tire data, internal SharePoint documents, raw private logs, credentials or personal paths merely to make a demo run.

## 2. Read the right document

| Need | Document |
|---|---|
| Work order, integration and dependencies | This file |
| EXE, one-command startup, packaging and reproducibility acceptance | [Team release contract](docs/team_release_contract.md) |
| Bicycle plant, driver request, allocation, four-wheel dynamics and fixed-clock testing | [Controller test contract](docs/controller_testing_contract.md) |
| Host C, digital target, real STM32 connection and isolated bench gates | [STM32 development path](docs/stm32_development_path.md) |
| What the team should review and supply | [Team review/data request](docs/team_review_and_data_request.md) |
| Instructions for the next implementation agent | [AGENTS.md](AGENTS.md) |
| Existing code architecture and evidence boundaries | [Engineering handoff](docs/engineering_handoff.md), [four-wheel guide](docs/four_wheel_dynamics.md), [source profiles](docs/source_vehicle_profiles.md) |
| Existing research work packages | [R01–R10 roadmap](docs/research/professional_racing/lapsim_development_roadmap.md), [original backlog](docs/research/professional_racing/backlog.json) |

This plan refines delivery priorities; it does not erase or relabel the earlier research backlog as implemented. Use E-IDs in commits/issue updates and cross-reference their R-IDs.

## 3. Starting inventory and exact references

Refresh these against live GitHub before making changes. A dated SHA is an audit anchor, not an instruction to overwrite later work.

| Surface | Reviewed identity | Meaning |
|---|---|---|
| LapSim main at the original October 14 handoff | `466f612f88bcaf9fe88f61e1e1ccfafed540245d` | Historical integrated application |
| LapSim main refreshed October 17 for packaging acceptance | `1153e7cfddd0ddc2467236b1403cc23b61f11a6e` | Viewer follow-up integrated normally through [#109](https://github.com/LucasKazaki/lapsim/pull/109), with actual local post-merge desktop checks |
| LapSim main refreshed October 18 after API claim eligibility | `cb91a82b4cce4266581439963cac30d778a0c877` | PR #112 merged normally, tree equal to accepted `944d19e`; actual merged-main 96 focused, five genuine CLI and three map checks passed |
| E04 output/staging overlap local candidate, October 18 | `5466c657bfaa4e06db8ed5f72ef572a5b597bc62` | Focused34, targeted4, map3 and actual full99/separate skip passed; full and skip peers clear; integration tracked separately |
| Viewer frame/unit local acceptance source, October 17 | `caa51fa62c00dd180548071e3b986fd58d471345` | Tested source; PR integration and post-merge verification tracked separately |
| Viewer renderer test-fixture follow-up, October 17 | `829df7d8ea12ad42c85f4bc05f2cca180f2f4e79` | Fresh focused86/full98; runtime unchanged, prior hosted failure and Tcl warning retained; Normally integrated through PR #109; original PR #108 closed as superseded |
| [LapSim #13](https://github.com/LucasKazaki/lapsim/pull/13) | `24698ed5e590f2d2e0d6bfa51a78c5446e436928` | Torque-replay viewer, based on main |
| [LapSim #15](https://github.com/LucasKazaki/lapsim/pull/15) | `41eb82d9513b9dc23256fb9a441f6a6b6bfb8ae2` | Timestep convergence repair, based on #13 |
| [LapSim #17](https://github.com/LucasKazaki/lapsim/pull/17) | `30ae5f0de261b82f61fe405b470038761de96ca5` | Battery interval-charge/preflight repair, based on #15 |
| [LapSim #18](https://github.com/LucasKazaki/lapsim/pull/18) | `a301c670dccfac0e2ae849b91db012dfdb91eac9` | Supplied/native receipt export, based on #17; still an open draft when refreshed October 16 |
| `feature/bicycle-model-baseline` at review | Same SHA as pre-handoff main | A branch name, not additional bicycle implementation |
| [Studio #77](https://github.com/LucasKazaki/lucas-agent-studio/pull/77) | `17715fc698a4bc7b3a7807d0d6f869045fdab5a4` | Five-component compiled C host replay |
| [Studio #78](https://github.com/LucasKazaki/lucas-agent-studio/pull/78) | `73cc2e2bbbf3fdae4a4fed1cc6e7b3df8bbb110e` | Successor with additional unlinked Cortex-M4 allocator evidence; open draft at refresh |

### Implementation inventory refreshed 16 October 2026, 02:48 Eastern

The table above preserves the starting lineage. The following are the current
integration audit anchors. Always refresh live refs; none is permission to reset
a checkout. At this refresh, live main remains
`466f612f88bcaf9fe88f61e1e1ccfafed540245d`. The combined candidate is
`33b8dcceb1c8ea33f50dc5802df346b7cbfac7e6` in
[PR #21](https://github.com/LucasKazaki/lapsim/pull/21), awaiting its final
combined review/checks and main merge.

| Package | Tested source / integrated PR | Current scope and evidence |
|---|---|---|
| E01 intended ancestry and handoff | #13 -> #15 -> #17 -> #18, plus #20 at `0c2444ab4f0cd82a68bf1bb566aad8b8b104355c` | Preserved by merge ancestry in #21; superseded #14/#16 excluded; original numerical counterexamples retained |
| E01 browser staging | #30 at `6bca36f05dfc44b1ee79f21b4fd50b05d92407db` | Immutable complete replay allowlist, actual PowerShell boundary tests; merged to integration |
| E02 self-contained controller | #46 at `bee9c929bee0456e07ba1405cae0305f59be4bea` | 419 original blobs verified; two separately hashed relocation patches retain originals and historical receipts; 538 tests and actual five-owner C replay pass in a fresh direct-temp clone; merged to integration |
| E04 dynamic bicycle | #36 at `de684edfd101ab2fa45421385a0597a826ee5a93` | Six-state synthetic plant, desktop/browser sessions, JSON replay and CSV; real browser and Windows frozen self-test pass; merged to integration |
| E05 effective grids and historical reports | #24 at `c8dcce0fb7821e58b4c4354646b732c080925dfc` | Real desktop/browser grid parity and legacy embedded-geometry replay; stale validation commands corrected; merged to integration |

The Studio source identity remains `73cc2e2...`; its #78 object evidence is
historical and unlinked. Fresh LapSim host evidence is distinct. E03 sensor
contracts, E06/E07 constrained control, E10 target execution and E15+ subsystem
studies are follow-on packages outside this integration snapshot. Installed
wheel/resource and full recipient-route acceptance remain E05/E09 work.
Public release is deferred by the user; no release asset or deployment follows
from these source merges. Keep issues #12/#19 open for the remaining gates.

LapSim already contains a modular distance-domain/event solver, desktop UI, browser Python runtime, source-aware profiles, saved/replayable results, a separate ten-state planar four-wheel lab, map/anatomy views, build scripts and quality gates. Preserve them. The lap plant, transient plant and receipt viewer are not yet one closed-loop controller experiment.

The overnight numerical work should not be discarded. PR15 records a fallback for a four-case motor-cutoff timestep oscillation; PR17 records rejection of 104 interval-charge overruns in a 2,160-case synthetic sweep. Preserve their failure cases, original accepted results and rollback checks. They establish bounded numerical behavior, not real-car validation. PR17 does not yet implement adaptive subdivision, torque retuning or a complete event-level battery-exhaustion policy.

The native controller work is also not merely a graphic. Its recorded source includes allocation, base guard, pedal reconciliation, normalized clock and final recovery/inhibit components. The viewer displays their recorded outputs; it does not execute firmware. Studio #78 explicitly reports unlinked objects, not target execution, a complete firmware image, memory fit or timing evidence.

## 4. Work packages

### E01 / P0: integrate the existing reviewed functional stack

Dependencies: fresh repository inventory. Related: quality issue #12.

1. Fetch all current refs and inspect PR metadata, diffs, comments, check runs and ancestry. Record main and each actual head. Preserve unrelated local changes.
2. Make an integration branch from **current main**, including this handoff. Integrate #13 → #15 → #17 → #18 with source ancestry retained, or propose the equivalent reviewed combined candidate. Do not reset main to the old baseline.
3. Do not merge superseded #14/#16, obsolete preparation #6/#7/#9, or every branch just because it exists. Classify each remaining branch as incorporated, superseded or genuinely outstanding.
4. Rerun the final candidate's native suite, generated numerical contracts, critical static/security checks, browser interactions, actual browser physics/replay, Windows frozen verification and source-map checks. Inspect failures and skips, not only aggregate green badges.
5. Use normal PR/branch rules. Never disable checks, change protection or force-push to make an integration pass. Use expected-head checks on merge. Re-run if the tested source changes.
6. After merge, record the resulting SHA and contained PRs. Retarget/close predecessor PRs accurately. Rebuild release/site artifacts from the final intended source; a merge does not redeploy a separately hosted site.

Done when: current main contains the intended functional ancestry, all required exact-head checks pass, the unresolved-quality list remains visible, and the published state is identified separately from branch state.

### E02 / P0: make controller development self-contained here

Dependencies: E01 inventory; can prepare the import in parallel. Related: R04/R09.

The source of interest is `projects/enme408-torque-control/` in the reviewed Studio lineage above. Do not merge the entire Studio repository or copy only the viewer JSON and call the result self-contained.

Perform a bounded dependency audit of that subtree: Python imports, C headers/translation units, build wrappers, test fixtures, contracts, reference/golden vectors, CI steps, licenses/notices and evidence-file references. Check for imports into unrelated Studio infrastructure and absolute workspace paths. Review publication rights before copying any nonpublic material.

Recommended migration: first vendor the reviewed, required ENME408 subtree under `controller/` while preserving its internal relative paths. Write `controller/UPSTREAM.md` with original repository, full commit, original/new path map, file hashes, license status and the import diff. Include the dependencies needed to run its focused tests and synthetic native replay. Later refactors can establish a cleaner package; do not simultaneously rewrite controller logic and relocate it.

Preserve immutable historical source/run receipts as historical evidence. Their original hashes remain original; relocation or wrapper changes require a new manifest and fresh test run, not rewriting the old receipt. Large optional audit archives can be named release assets with hashes; all source, compact synthetic fixtures and build inputs required for the baseline must be in an ordinary clone or its reviewed release package. Expiring CI artifacts and a sibling checkout cannot be mandatory dependencies.

Move the useful CI recipes into LapSim and select one canonical controller owner. Host, emulator and target builds must use the same core source, not hand-maintained numerical copies. The core must not import GUI code, network clients, LLM libraries or personal automation infrastructure.

Done when: clone only LapSim into a fresh directory, make the Studio checkout unavailable, build the native core, execute the imported synthetic reference/replay tests and open the resulting receipt locally. Record any supported-platform exceptions explicitly.

### E03 / P0: establish the common experiment/data contract

Dependencies: none for design, E02 for imported runtime. Related: R01.

Implement the versioned scenario, clock, input, output and run-manifest contracts in [the controller specification](docs/controller_testing_contract.md). Reuse the existing record/profile machinery where compatible; do not create an unrelated recorder without documenting why.

Define vehicle/model/topology IDs separately; record all initial state, units, axes, sources, seeds, integration settings, controller period and parameter provenance. Separate plant truth from simulated sensor measurements. Do not silently give an estimated-state controller access to noiseless truth.

Done when: a small synthetic fixture round-trips through decoding, execution, recording and replay; unknowns/invalid values are distinguishable from physical zeros; malformed/stale/out-of-order inputs have tested policies.

### E04 / P0: finish the actual bicycle baseline

Dependencies: E03. Related: R04, basic model verification.

Add a named dynamic single-track plant with its equations, state, low-speed policy and analytic tests. A kinematic bicycle may be a preliminary mode, but cannot stand in for lateral/yaw dynamics. A Prius parameter set is not a model family. A bicycle cannot resolve independent left/right wheel slip merely because the UI draws four wheels.

Fresh basic dynamics sessions should start with the **synthetic bicycle**. Keep the prescribed-path lap model accessible and honestly labeled; do not silently reroute existing saved laps to a different model. Keep the four-wheel model as the explicit independent-wheel torque-control mode. Save model choice in records and show it prominently in desktop/browser interfaces.

Done when: straight-line, coast, small-angle constant-turn, zero-steer symmetry, left/right mirrored response, invalid-parameter and low-speed tests pass; refinement changes are measured; startup defaults select the intended basic mode; restored historical records retain their original model.

Implementation candidate, 16 October 2026: the six-state `dynamic_bicycle_v1`
plant and versioned recorded-run route are implemented with the frozen
[bicycle contract](docs/dynamic_bicycle_contract.md). Actual Tk and
Chromium/Pyodide sessions select the synthetic bicycle, execute it, and export
records that replay in Python. The portable self-test also exercises this UI
route and replay. This remains a prescribed-contact-force baseline; E03 sensor
freshness and E06/E07 constrained closed-loop work are separate gates. Source
and browser checks do not establish a passing frozen build; the exact candidate
must also pass Windows CI before integration.

### E05 / P0: fix reproducibility and historical-document drift

Dependencies: E01. Related: R01/R03.

A bounded E05 repair makes `SpatialTrack.from_cells` keep one declared cell per supplied length/curvature pair, while retaining `from_track` ceil subdivision and embedded historical grids during replay. Use the dated [declared-cell receipt](docs/research/evidence/declared-cell-grid-20261018.json) for this repair's source-specific checks and limitations. E05 remains open for complete matched source, installed-package and frozen recipient-route reproduction.

The imported-course recipient self-test now exercises the real import and synchronous calculation worker, then saves, loads and replays the public 32-arc circle at 5 m and 0.5 m requests (32/128 cells). Geometry and complete configured settings/vehicle/profile inputs are checked, with resolved starting speed recorded separately. Temporary GUI storage isolates courses, profiles and runs; scratch hashes/IDs describe observed round trips rather than retained payloads. Atomic saves handle otherwise addressable Windows destinations whose UUID temporary paths exceed the ordinary path limit. Local source, wheel, sdist, bootstrap and original/copied Windows EXE checks passed for this bounded route; see the [recipient receipt](docs/research/evidence/recipient-imported-grid-20261018.json) for source identities, commands, counts and limitations. E05 remains open for matched built-in/fused recipient routes, ordinary file-picker and asynchronous Run acceptance.

The built-in synthetic-loop recipient check selects the shipped catalog entry through the real desktop app, then uses its synchronous worker to save, load and replay the declared 392-cell grid. Source/effective geometry and complete configured inputs match across source, wheel, sdist, bootstrap and original/copied EXE contexts; run IDs and numerical traces are not equated across recipients. Temporary GUI storage preserves ordinary user files. See the [catalog recipient receipt](docs/research/evidence/recipient-catalog-grid-20261018.json) for the tested source, actual commands/counts, retained failures and limitations. This is a bounded extension of the earlier imported 32/128-cell route. E05 remains open for other built-in/fused recipient routes, ordinary file-picker and asynchronous Run acceptance; no calibration, hardware or publication claim follows.

The coarse fused-course recipient check selects the shipped course at 5 m (198 cells, final cell 4 m), freezes complete configured inputs, then saves, loads and replays the actual worker result. A same-value scalar-class defect appeared when live NumPy brake-pressure commands crossed JSON; validated Controls now normalize six request fields to Python floats before the unchanged final range checks. Source, wheel/sdist/bootstrap, original/copied Windows EXE and separate Pyodide checks passed at the stated runtime source. See the [fused recipient receipt](docs/research/evidence/recipient-fused-grid-20261018.json) for actual versions, counts, retained failures and geometry/privacy limits. Ordinary picker and asynchronous Run acceptance remain open.

The fused recipient check also exercises the original 0.5 m, 1,978-cell grid through source, wheel, sdist, extracted-source bootstrap and original/copied EXEs. Independent CSV/Fraction checks cover every geometry channel and complete configured inputs; refining the coarse grid cannot satisfy acceptance. The [fine fused recipient receipt](docs/research/evidence/recipient-fused-fine-grid-20261018.json) records the runtime source, commands, local results and limits. Ordinary picker and asynchronous Run acceptance remain open. The installed-package and extracted-source bootstrap desktop self-test child bounds are 300 s; numerical and replay thresholds are unchanged.

The ordinary Run source regression now uses an isolated child with a 60 s parent process bound while preserving the real public button, worker, Tk polling and all 63 original probe assertions. It checks the analytic imported 128-cell circle, complete configured inputs and 17 unchanged replay tolerances. A deliberately blocked-worker control returned its expected test failure after a scaled 6 s child timeout, before the 12 s outer guard. Focused, differential quality and the ordinary 100-module suite passed locally. See the [bounded Run receipt](docs/research/evidence/ordinary-async-bounded-run-20261018.json); the [earlier receipt](docs/research/evidence/ordinary-async-run-20261018.json) remains historical after the valid PR123 deadline finding. E05 remains open for picker, cancellation/failure races, installed/frozen/browser asynchronous Run and visual acceptance. That test-only increment left production behavior unchanged; the Tcl warning remains unresolved.

The ordinary Run handler now routes a worker-launch `RuntimeError` through the existing scheduled error path in Centerline and AI modes. Controlled failures before `Thread.start` delegation check that Run availability recovers and progress stops without launching a model calculation. Natural failure rates, partially started custom threads, cancellation races and installed/frozen/browser Run acceptance remain outside this check.

The original interface-grid and documentation findings have source repairs retained from #24:

- `web/bridge.py` now calls `solver_track_for_course`, and `src/lapsim/ui/course_catalog.py` delegates that route to the shared `resolve_solver_grid`. `tests/test_adapter_grid_parity.py` exercises the real desktop worker and browser adapter with synthetic, public imported and fused fixtures at coarse/fine requests, and retains legacy browser-record replay against embedded geometry. These source regressions address the original adapter-comparison gap; they do not establish current installed-package or frozen recipient-route acceptance.
- `docs/first_endurance_lap_validation.md` now points to `analysis/endurance/analyze_endurance.py`, identifies the former `scripts/validate_first_endurance_lap.py` as absent, and labels the earlier SOC report as historical. Its former brake-free model description does not describe the current pressure-to-brake-torque implementation. This documentation repair does not establish new measured-data correlation.

Remaining recipient-route acceptance: run the same matched fixture from clean source, installed-package and frozen-resource contexts. Cover synthetic courses, a public imported coherent bundle, coarse/fine cell requests and the fused course's documented exception. Compare source and effective geometry hashes, stations, cell lengths, curvature, model/profile, limits and initial state before outputs; exercise the actual adapters, exported records and replay in each declared context.

Keep the current correlation entrypoint tied to source/input/parameter IDs and authorized recorded lap, control, IMU and track inputs. Missing private evidence must be an explicit optional skip, never fabricated data. Preserve older reports as historical; synthetic results do not replace historical measured results under the same title. No new correlation analysis is asserted by this status correction.

Done when: the retained interface-grid regressions and current documented commands are reproduced through the declared source/installed/frozen recipient routes, with unsupported/private-only reproduction requirements labeled.

### E06 / P0: constrain four-wheel actuation and battery boundaries

Dependencies: E03. Related: R02/R06/R07.

Add feasible motor/inverter/pack/drivetrain evaluation around the transient plant, using shared component contracts where valid. Static axle loads and unrestricted torques remain an explicitly idealized reference, not the default evidence for realizable controller gains.

Declare actuator topology rather than assuming four motors: single-actuator RWD with a differential is distinct from independent-rear RWD and four-actuator AWD. Implement only declared synthetic topologies until the team confirms hardware. Include torque-speed capability, direction-dependent losses, generating limits, shared pack power/current/voltage limits, SOC interval feasibility, and declared delay/slew behavior. Unavailable thermal models remain unavailable, not calibrated derating.

Handle PR17-style interval rejection at event/runner level: choose and test explicit early termination, consistent event-boundary subdivision or re-solved feasible demand. Preserve physics and state atomicity. Never clip recorded SOC, current, force or energy after solving and describe the result as energy-consistent. Preserve the existing accepted-case invariants.

Done when: excessive demand becomes visible unmet demand, achieved outputs obey the declared constraints, all power/torque frames are tested, and mirrored/equal-command cases retain symmetry. See the controller contract for wheel inertia and power accounting.

### E07 / P0: close the fixed-clock loop

Dependencies: E02/E03/E06; E04 supplies the simpler reference. Related: R04.

Implement one plant runner with replaceable Python-reference, native-C and later target backends. Controller calls occur at declared time ticks, not once per distance cell, RK4 evaluation or GUI frame. Hold actuator commands across plant substeps; sensor schedules and injected latency are explicit.

Start with a short deterministic scenario. Compare controller-off/equal-split and a candidate on identical conditions. Keep the distance-domain lap solver separate. Real-car correlation is not required to prove synthetic loop mechanics, but calibrated gains remain blocked on data.

Done when: repeat runs reproduce their declared traces; changing UI/logging frequency does not change decisions; changing plant step is separately testable from changing controller period; native/reference differences have recorded tolerances and fault-state agreement.

### E08 / P1: useful torque-control experiments and displays

Dependencies: E07. Related: R04/R10.

Use the scenario matrix and metrics in the controller contract. Start with bounded pedal demand and equal split, then traction limiting. Add yaw targets/allocation only with an explicit feasibility and state-estimation policy. Do not introduce a general optimizer before the bounded baseline is auditable.

Extend the existing lab/viewer with driver request, aggregate demand, proposed allocation, guarded/limited command, actual actuator torque, contact force, unmet force/yaw demand, slip, yaw reference/response, energy and inhibition reason. Label Python/C/emulator/physical target and synthetic/measured evidence. Animate the recorded plant, not a decorative trajectory unrelated to integration.

Done when: a team member can reproduce one useful A/B maneuver, inspect the limiting reason and export its full record without reading raw JSON or requiring another repository.

### E09 / P0: deliver one-repo startup and release

Dependencies: E01/E02/E04/E05 for the integrated baseline; E07/E08 before labeling a release a closed-loop torque lab.

Implement [the release contract](docs/team_release_contract.md). The nondeveloper Windows path is a tested ZIP with `LapSim.exe`, required runtime/native libraries, public fixtures, documentation and source identity. The developer path is one documented idempotent bootstrap command after cloning, with explicit platform prerequisites. Neither path flashes hardware by default.

Do not require a host compiler just to run a prebuilt demonstration. Optional C development, emulator and board tooling can require extra installation, but their absence must not prevent the ordinary synthetic UI from working. Publish GitHub Releases and the static site from identified source, not a personal machine's unversioned output directory.

Done when: clean-machine source and EXE acceptance passes and the intended artifact actually exists at its advertised release location.

### E10 / P1: linked bench firmware and bounded digital target

Dependencies: E02/E03; E07 for plant connection. Related: R09.

Follow [the STM32 path](docs/stm32_development_path.md). First preserve host behavior and establish a reproducible linked bench image for an explicitly documented target configuration. Existing Cortex-M4 objects are not enough. Next test a minimal MCU/emulator adapter with the same core, using a pinned supported board model and a peripheral coverage table.

This can proceed without a team PCB as a clearly labeled emulated/generic target. Exact team-board startup, pins and firmware integration stay blocked. Do not invent a custom-board USB device, CAN mapping or clock setup.

### E11 / P1: explicit-device processor-in-the-loop

Dependencies: E07/E10 plus verified board/connection information. Related: R09.

Build the PC-to-board adapter and bench firmware with the framing, handshake, reset/timeout and opt-in rules in the STM32 path. Real board computes only controller outputs; the PC applies them to the simulated plant. No motor inverter is needed. Use lockstep first; record wall time separately from simulated time.

Done when: the same scenario runs against the board with matched logical input sequence, output/fault-state comparison, reset/dropout tests and a retained identity/timing receipt. Physical testing is blocked until an actual board and verified wiring are available, not satisfied by a mocked serial test.

### E12 / P2: timing and isolated CAN/HIL

Dependencies: E11 and team-defined timing/interfaces. Related: R09.

Characterize target execution distribution, interrupt/communication load, missed deadlines, reset/watchdog behavior, memory and whole-call-stack needs. Loopback checks and host serial latency are not CAN-bus validation or a proof of worst-case execution time. Design a separate isolated bench before considering any live inverter/vehicle integration. Obtain team safety review and test procedures; normal simulator operation must never enable that path.

### E13 / P1: team review and data intake

Dependencies: none for requests. Related: R01/R03/R05/R06.

Use [the focused request](docs/team_review_and_data_request.md). Ask the team to approve/supersede existing evidence rather than re-enter known records. Store source, unit, configuration/revision, measurement/design/estimate status and owner. Start correlation with one complete test, then reserve independent conditions for evaluation. Do not hold all software progress hostage to unavailable data.

### E14 / P1: close quality and maintenance gaps

Related: [issue #12](https://github.com/LucasKazaki/lapsim/issues/12) and all packages.

The October 14 issue records 241 Pyright errors/48 warnings; a later PR17 environment records 267/49. These are different recorded scopes/environments, not evidence of a clean repository or automatically proof of a regression. Freeze interpreter, packages, tool version and baseline to reconcile changes. Keep a no-new-diagnostic gate while triaging real contracts; do not erase the baseline or blanket-ignore findings.

Separate formatting-only changes from behavior changes. Maintain source-map freshness, docs links, dependency/secret scans, license/redistribution review, keyboard/large-text/manual device checks and honest skip reporting. Add new controller directories to the relevant lint/test/security and distribution inventories without scanning private logs into public reports.

The path-solver count boundary requires positive, nonboolean `numbers.Integral`
settings before execution and retains accepted integer objects without coercion.
The pass loop obtains a Python integer through `operator.index` before adding
one for its exclusive bound, avoiding scalar promotion and fixed-width overflow
without changing solver equations or configured iteration limits. The historical
[count-validation manifest](docs/research/evidence/path-iteration-count-validation-20261018.json)
retains the tests-first, full-suite and diagnostic record for `b27b280`; the
separate [integer-execution manifest](docs/research/evidence/path-iteration-integer-execution-20261018.json)
records the follow-up runtime-specific execution evidence. Neither establishes
a complete supported-version matrix or physical accuracy. One Tcl cleanup
warning and the existing diagnostic debt remain open; E14 is not complete.

## 5. Delivery gates, not arbitrary deadlines

| Gate | Required evidence | Work that can proceed without team data |
|---|---|---|
| G0: reviewed foundation | E01 merged and source-identified; intended stack preserved | Entire gate |
| G1: one-repo basic demonstration | E02/E03/E04/E05 and basic E09 acceptance | Entire gate with synthetic fixtures |
| G2: constrained closed-loop torque lab | E06/E07/E08; source/native comparison and scenario evidence | Synthetic experiments; no real-car gain claim |
| G3: digital target | E10 linked image and actual emulator/core results with omissions | Supported generic/emulated target |
| G4: isolated STM32 PIL | E11 real-device evidence and verified bench setup | Host adapter/mock tests only until hardware is available |
| G5: physical model/controller validation | E12/E13 measured interfaces, timing and independent correlation | Planning only for unavailable measurements |

Within G1–G2, prefer E03/E05 tests early, then bicycle and actuator work in parallel. Do not turn the table into a waterfall that prevents independent tests. A team-release candidate can be labeled basic/synthetic before all later gates complete, provided its capability matrix is accurate.

## 6. Required completion update

For each E-ID, post to issue #19: scope and affected paths; before/after SHA; actual commands/environment; passes/failures/skips; saved fixture/run and source hashes; review decision; remaining blockers. Mark implementation, release publication, target execution and physical validation separately. Keep original failed evidence where it explains a repair; do not drown the baseline clone in duplicate generated logs.

The first next-agent action is implementation of a bounded package with tests, not another research sweep or duplicate roadmap.
