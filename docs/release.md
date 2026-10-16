# Windows public release and reproducible build

The public distribution is `LapSim-Windows-x64.zip`. Its main application is
`LapSim.exe`, a single-file Windows x64 PyInstaller build. The executable
contains the Python runtime, Tk/Tcl, Matplotlib resources, simulator modules,
analytic synthetic courses, the offline map, curated documentation, and a
curated source snapshot. A recipient can launch the app without Python, a
virtual environment, Git, or the source checkout.

## Public-data boundary

The public build is deliberately **synthetic-data-only**. It does not package:

- `analysis/data/`;
- `outputs/` or `output/`;
- logs;
- the derived GNSS/IMU course CSV or JSON;
- telemetry, calibrations, fitted parameters, or vehicle-specific team data; or
- another file excluded by `LICENSE_SCOPE.md`.

The source checkout may still refer to separately controlled team material.
Presence in the public repository does not establish publication authority.
Do not restore excluded files to the public archive unless the applicable
rights holder provides file-specific authorization and `LICENSE_SCOPE.md` is
updated accordingly.

The public executable filters the built-in course catalog to analytic synthetic
courses before the desktop application is imported. The frozen self-test fails
unless the selected release course is synthetic.

## Recipient workflow

1. Download the expected ZIP and compare its SHA-256 with the supplied release
   checksum when available.
2. Extract it to a writable local folder and double-click `LapSim.exe`.
3. Start with the synthetic-loop demonstration in
   [the team guide](team_guide.md).
4. Click **Simulator map** to open the offline expandable model map.
5. Keep saved run JSON files and linked AI trials with screenshots when
   presenting modeled results.

First startup can be slower while the one-file runtime is extracted into
Windows temporary storage. User profiles, imported courses, runs, and startup
logs are stored in `%LOCALAPPDATA%\LapSim`, independent of the extraction
folder.

The EXE is unsigned and has no established publisher reputation. A Windows or
organization security prompt can therefore occur. Verify artifact identity and
use an approved distribution process.

The source snapshot is **source-available, not open source**. Before viewing,
copying, running, modifying, or sharing it, read the root `LICENSE`,
`LICENSE_SCOPE.md`, and `NOTICE`, plus [the licensing guide](licensing.md).
The competition-use restriction and redistribution limits apply only to
material actually covered by the stated license. Upstream, contributor-owned,
third-party, and engineering-data material may have different or unresolved
rights.

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
machine-readable report checking the frozen resource layout, TkAgg canvas,
desktop construction, synthetic bundled course, one synthetic lap, saved
record, numerical replay, metadata, and durable cached map/source/documentation
links. A passing report must include `"frozen": true` and
`"course_synthetic": true`.

Self-test is software evidence. It does not establish real-car accuracy,
surveyed course boundaries, rules compliance, or permission to publish data.

## Rebuild from this checkout

Use Windows x64 Python 3.12+ with Tkinter. The source project supports Python
3.11+, but the pinned build dependencies may require a newer interpreter.

From the repository root:

```powershell
.\setup_lapsim.cmd
.\build_lapsim.cmd
```

The build implementation is `scripts/build_windows.py`; the PyInstaller
specification is `packaging/LapSim.spec`; and the controlled dependency snapshot
is `requirements-build.lock`.

The builder:

1. runs `scripts/check_license_policy.py`;
2. runs the complete repository checks unless `--skip-tests` is supplied after
   an equivalent check of the same checkout;
3. stages only the curated public file set;
4. rejects any staged path under the public exclusion policy;
5. builds `LapSim.exe`;
6. runs the frozen synthetic-data-only self-test from an unrelated temporary
   directory; and
7. produces `LapSim-Windows-x64.zip`, `portable-self-test.json`, and
   `checksums.json`.

The output directory can be changed with:

```powershell
.\build_lapsim.cmd --output-dir C:\path\to\release
```

Frozen read-only resources resolve through
`lapsim.resources.repository_root()` to the extraction root's `bundle`
directory. Source runs resolve to the checkout. Per-user writable data resolves
independently. Do not save user records into `_MEIPASS` or rely on the current
working directory for bundled files.

## Release acceptance

Before distributing a public build:

1. verify `LICENSE`, `LICENSE_SCOPE.md`, `NOTICE`, `CONTRIBUTING.md`, and
   `docs/licensing.md` are present;
2. verify no path under `analysis/data/`, `outputs/`, `output/`, or `logs/`
   appears in the archive;
3. verify the fused GNSS/IMU CSV and JSON are absent;
4. run the exact final EXE from an unrelated current directory and clean user
   data location;
5. verify the report identifies a synthetic course;
6. verify an ordinary desktop launch, synthetic lap and replay, offline map,
   and source links; and
7. preserve hashes, runtime versions, source commit, dirty-worktree state,
   skipped-test reasons, and manual-check scope.

Never describe a source-only sweep as proof that a different executable passed.
Never infer data-publication authority from a successful software test.
