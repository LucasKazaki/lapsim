# Windows release and reproducible build

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

Self-test is software evidence. It does not establish real-car accuracy or
surveyed course boundaries. The complete repository tests and the packaged
smoke workflow are described in [verification](verification.md).

## Rebuild from this checkout

For the locked reproducible build, use **Windows x64 Python 3.12+** with
Tkinter; this release was tested with **Python 3.12.2**. The source project
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
`checksums.json`. The ZIP includes the available release verification logs and
third-party runtime license notices. The output directory can be changed with
`--output-dir`; `--skip-tests` is intended only after a separate complete check
of the same final checkout:

```powershell
.\build_lapsim.cmd --output-dir C:\path\to\release
```

Frozen read-only resources resolve through `lapsim.resources.repository_root()`
to the extraction root's `bundle` directory. Source runs resolve to the checkout.
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

Use the final package's report as the source of actual passing totals. Historical
test counts in the engineering handoff and earlier local logs describe earlier
runs. Rebuild when code, bundled data, documentation, or map changes, then
repeat checks affected by those changes. Never describe a source-only sweep as
proof that a different executable passed.
