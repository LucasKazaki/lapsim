# Windows release and reproducible build

16 October 2026: public release/site deployment are deferred by the owner.
The commands below build internal review artifacts. The current source startup
is [the one-command bootstrap](setup.md); wheels/sdists now contain the declared
resource/controller closure. The existing hosted site is a separate older build.

The team distribution is `LapSim-Windows-x64.zip`. Its main application is
`LapSim.exe`, a single-file Windows x64 PyInstaller build. The executable
contains the Python runtime, Tk/Tcl, Matplotlib resources, simulator modules,
the mandatory fused course, offline map/documentation, and a source snapshot
for source references and reproducibility. A recipient can launch the app
without Python, a virtual environment, Git, or the source checkout.

The ZIP adds conveniently browsable documentation, map, source snapshot, and
test evidence. Keep the ZIP as the reviewed team artifact even though the EXE
can run on its own. The optional external ENME408 source evidence and raw MF4
logs are not bundled. Their absence leaves the ordinary built-in profiles,
synthetic courses, and fused-course demonstrations available.

## Recipient workflow

1. Download the expected team ZIP and compare its SHA-256 with the supplied
   release checksum when available.
2. Extract it to a writable local folder. Double-click `LapSim.exe`.
3. Start with the [team guide](team_guide.md) and its synthetic-loop demo.
4. Click **Simulator map** to open the offline expandable model map. The app
   copies bundled map, documentation, and source references into a durable
   local cache, so closing the one-file process does not remove the open map.
5. Share saved run JSON files and linked AI trials alongside screenshots when
   presenting modeled results.

First startup can be slower while the one-file runtime is extracted into
Windows temporary storage. User profiles, imported courses, runs, and startup
logs are stored in `%LOCALAPPDATA%\LapSim`, independent of the extraction
folder. Replacing the app does not replace those user files.

The EXE is unsigned and has no established publisher reputation. A Windows or
organization security prompt can therefore occur. Verify artifact identity and
use the team's approved distribution process; an organization may require code
signing before deployment. The repository does not declare a project license.
This package is prepared for the requested internal team review; external
redistribution and source licensing remain repository-owner decisions.

## Frozen application options

From the folder containing `LapSim.exe`:

```powershell
.\LapSim.exe
.\LapSim.exe --flow-map
$checkProcess = Start-Process -FilePath .\LapSim.exe -ArgumentList '--self-test','report.json' -WindowStyle Hidden -Wait -PassThru
$checkProcess.ExitCode
Get-Content -Raw report.json | ConvertFrom-Json
```

`--flow-map` opens the durable offline simulator map. `--self-test` writes a
machine-readable report for the packaged runtime, checking the frozen resource
layout, TkAgg canvas, full desktop construction, bundled course, a synthetic
lap, saved record, numerical replay, metadata, and durable cached map/source/
documentation links. Run it with a usable Windows
display. Read the report and its exit status; absence of a startup window alone
is not evidence that the application passed. Because the executable uses the
Windows GUI subsystem, an ordinary interactive PowerShell invocation may return
before self-test finishes. `Start-Process -Wait -PassThru` above waits and exposes
the completed process's exit code.

`--self-test` also imports a public synthetic circular course at two requested cell sizes. It verifies the resulting 32-cell and 128-cell grids, saved inputs and replay through the desktop calculation path. These GUI checks use temporary course, profile and run storage. The report retains hashes and IDs; its scratch lap files are removed when the test finishes. The same self-test also selects the built-in synthetic-loop demo and checks its declared 392-cell grid, configured inputs and saved-record replay in the separately verified recipient contexts.

The self-test also selects the shipped fused course at 5 m (198 cells,
including its 4 m final cell) and 0.5 m (1,978 original source cells). Each
request saves and reloads the run and checks its model replay. Independent
source-channel checks reject refining an already averaged coarse grid into a
fine one. The course's unverified source claims and geometry limits remain.
Source, installed and frozen recipient checks record separate results.

Self-test is software evidence. It does not establish real-car accuracy or
surveyed course boundaries. The complete repository tests and the packaged
smoke workflow are described in [verification](verification.md).

## Rebuild from this checkout

For the locked reproducible build, use **Windows x64 Python 3.12+** with
Tkinter. **Python 3.12.2** identifies the earlier build; current local internal
qualification uses **Python 3.13.15**, and each new report records its actual
interpreter/dependency/source identities. The source project
supports Python 3.11+, but pinned NumPy 2.5.3 and SciPy 1.18.1 in the build lock
require Python 3.12+. If an existing `.venv` uses 3.11, preserve/rename it and
create the build environment with 3.12+ before installing the lock.

From the repository root, run source setup and the checked-in build entry point:

```powershell
.\setup_lapsim.cmd
.\build_lapsim.cmd
```

The Python build implementation is `scripts/build_windows.py`; the PyInstaller
specification is `packaging/LapSim.spec`, and the controlled build dependency
snapshot is `requirements-build.lock`. The build uses PyInstaller **6.22.0**.
Keep those files with the source and release manifest. Use the documented output
path printed by the builder rather than uploading a prior EXE left elsewhere.

By default, the builder runs `scripts/check_all.py`, refreshes the
map's generated source inventory, builds `dist/LapSim.exe`, and runs that
executable's self-test from a temporary unrelated directory with Python/Git
removed from `PATH`, isolated user data, and optional external evidence absent.
It then produces `dist/LapSim-Windows-x64.zip`, `portable-self-test.json`, and
`checksums.json`. The ZIP includes verification produced by this build invocation
and third-party runtime license notices. The output directory can be changed with
`--output-dir`; `--skip-tests` is intended only after a separate complete check
of the same final checkout:

```powershell
.\build_lapsim.cmd --output-dir C:\path\to\release
```

`--output-dir` must resolve outside the repository's `build/assets` tree,
including every descendant. Both full and `--skip-tests` builds reject overlap
with exit 2 before output/evidence creation, tests, inventory generation or staging.

Each invocation keeps a fresh `verification-*` directory beneath its output,
including on a failed or missing full-suite report. Its local
`full-suite-invocation.json` records the literal test command before execution
and its outcome. The ZIP's `verification/build-verification.json` instead uses
a sanitized logical command and identifies the packaged source context.
When full tests pass, only that invocation's exact aggregate is included as
`verification/test-results.xml`, with its SHA256. Ambient `work` reports/logs
and earlier output reports are excluded. With `--skip-tests`, the receipt says
`skipped` and includes no full-suite report; separately retained acceptance
evidence is not attached automatically. The fresh portable self-test remains
a distinct frozen smoke check. When enabled, full repository tests precede inventory
generation, so the packaged snapshot identity is separate from that test phase;
this receipt does not attest that both snapshots are identical.

The full-suite XML is retained byte-for-byte and can include the runner's
hostname or local diagnostic paths. A sanitized JSON receipt does not
establish that the ZIP/report is free of machine metadata; these internal QA
artifacts carry no publication or release claim.

Actual full and skipped build artifacts retain source `cb3720b`. Test-only
successors passed the same 18 focused contracts, most recently at `7ead724`;
the actual final four-file gate reports no new type/broad findings against
main `1153e7c`, with existing debt retained. These checks do not rebuild those
artifacts. See the [local build evidence](research/evidence/portable-build-verification-20261017.json)
for the retained failed gate and coverage limits.

Source status excludes only the build's fresh verification leaf, preserving
other source dirtiness. At `6ed6153`, actual full and separate skipped builds
passed with clean packaged identities, each completing 20 original and 21
copied checks plus supported-record/alias/frame/units exits 0/2/1/1. The full
receipt binds its exact 98-report aggregate (2,467 reported / 1,457 raw cases,
zero failures/errors, one expected Windows POSIX-only skip); skipped verification
has null suite command/report and no XML or totals. The [build evidence](research/evidence/portable-build-verification-20261017.json)
retains distinct EXE/ZIP hashes, 30 focused contracts (12 real-Git cases), the PR #110
finding and failed style gate, plus passed quality gates and their remaining
debt/warning limits. Native records were viewed passively; standard fast-model
replays ran. PyInstaller's existing hidden-import warning is separate from the
full suite's zero warning-summary blocks. Final map passed, and normal
[PR #111](https://github.com/LucasKazaki/lapsim/pull/111) merged at `13076f6`
after 14 exact-head checks, with its full tree equal to accepted `9bb6338`.
Thirty post-merge contracts and all three source-map entrypoints passed.
The separate local packaging acceptance record contains absolute paths; it is
not a sanitized public deliverable. These artifacts keep source `6ed6153`,
with raw-JUnit privacy and internal-only publication limits unchanged.

At `5466c65`, four retained overlap RED cases became 34 passing focused
contracts with the original 30 unchanged. Targeted four-file quality introduced
no type/broad findings against fixed main `1153e7c`; critical, checker format
and mapped security passed, with whole-file format debt retained. The actual
normal build completed 99 fresh reports (2,491 reported / 1,481 raw cases,
zero failures/errors, one expected POSIX-only skip on Windows). Full and separate
skipped builds each completed 20 original and 21 copied checks and command exits
0/2/1/1. Full and skipped-build independent preservation reviews passed.
The skipped receipt has null suite command/report and
attaches no XML or totals, while preserving all 1,748 full-build copies.
The [dated evidence](research/evidence/portable-output-assets-20261018.json)
binds the distinct artifacts, guard measurements and unchanged global-scope
reuse. Normal integration and post-merge verification are tracked separately in
[issue #19](https://github.com/LucasKazaki/lapsim/issues/19). Raw-JUnit privacy,
PyInstaller warning and historical Tcl limits remain; no release or fresh native
solver claim.

The [comparison claim receipt](research/evidence/chrono-native-comparison-claims-20261018.json)
separately binds wheel/source-distribution acceptance at `a582eda`, including
five saved-record comparison CLI routes per format. Those archives are not
published and do not replace the earlier `6ed6153` executable checks.
[PR #112](https://github.com/LucasKazaki/lapsim/pull/112) merged normally at
`cb91a82` after 16 exact-head checks, with its tree equal to accepted `944d19e`.
Merged-main 96 focused checks, five genuine CLI routes and three map entrypoints
passed; their separate local acceptance record is not a sanitized public artifact.
The installed archives keep `a582eda`, with no fresh native solver claim.

Frozen read-only resources resolve through `lapsim.resources.repository_root()`
to the extraction root's `bundle` directory. Source runs resolve to the checkout.
Installed wheels resolve to `lapsim/_resources` and use captured identity;
unversioned source snapshots never inherit an unrelated ancestor Git identity.
The durable help copy supports long retained evidence names without changing
global Windows settings.
The mandatory course remains `analysis/data/track/gnss_imu_endurance_track.csv`
inside that resource tree, with its bundled JSON metadata. Per-user writable
data resolves independently. Do not save user records into `_MEIPASS` or rely
on the current working directory for bundled files.

## Release acceptance

Run a complete software sweep after source changes and build the final artifact.
Then test that exact EXE from an unrelated current directory and a clean test
user-data location. Verify the frozen self-test report, an ordinary desktop
launch, a synthetic lap and replay, the offline map and source links, and the
other required flows in the verification guide. Preserve skipped-test reasons,
manual-check scope, hashes, runtime versions, source commit, and dirty-worktree
state in the release evidence.

Use an included full-suite XML for passing totals only when the final package's
verification receipt says `passed`. A skipped build has no included full-suite
totals; `portable-self-test.json` describes the separate frozen smoke workflow.
Keep separately run suite evidence with its own source and hash bindings. Historical
test counts in the engineering handoff and earlier local logs describe earlier
runs. Rebuild when code, bundled data, documentation, or map changes, then
repeat checks affected by those changes. Never describe a source-only sweep as
proof that a different executable passed.
