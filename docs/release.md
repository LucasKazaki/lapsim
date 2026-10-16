# Windows public release and reproducible build

The public distribution is `LapSim-Windows-x64.zip`. Its main application is
`LapSim.exe`, a single-file Windows x64 PyInstaller build. The executable
contains the Python runtime, Tk/Tcl, Matplotlib resources, simulator modules,
analytic synthetic courses, the offline map, curated public documentation, and
a reviewed source subset. A recipient can launch the app without Python, a
virtual environment, Git, or the source checkout.

## Public-data boundary

The public build is deliberately **synthetic-data-only**. The packager uses an
explicit allowlist rather than copying the repository or all Markdown files.
It does not package:

- `analysis/`, `data/`, `tests/`, `work/`, `outputs/`, or `output/`;
- `docs/evidence/` or historical validation reports;
- the derived GNSS/IMU course CSV or JSON;
- tire/vendor parameter files;
- telemetry, calibrations, fitted parameters, vehicle-specific configurations,
  CAN material, firmware, CAD, sponsor material, or other team evidence; or
- another file excluded by `LICENSE_SCOPE.md`.

The reviewed documentation allowlist is declared as
`PUBLIC_DOCUMENTATION_FILES` in `scripts/build_windows.py`. The offline
simulator-flowchart directory is included as a separate reviewed subtree. A
path outside those lists does not enter the ZIP merely because it exists in the
public repository.

The source checkout may still refer to separately controlled team material.
Presence in the repository does not establish publication authority. Do not
restore excluded files to the public artifact unless the applicable rights
holder provides file-specific authorization and `LICENSE_SCOPE.md` is updated.

The public executable filters its built-in course catalog to analytic synthetic
courses before importing the desktop application. The frozen self-test fails
unless the selected release course is synthetic.

## Recipient workflow

1. Download the expected ZIP and compare its SHA-256 with the supplied release
   checksum when available.
2. Extract it to a writable local folder and double-click `LapSim.exe`.
3. Start with [the public demonstration](public_demo.md).
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

The source subset is **source-available, not open source**. Before viewing,
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
record, numerical replay, metadata, and curated offline links. A passing report
must include `"frozen": true` and `"course_synthetic": true`.

Self-test is software evidence. It does not establish real-car accuracy,
surveyed course boundaries, rules compliance, or permission to publish data.

## Rebuild from the full checkout

Use Windows x64 Python 3.12+ with Tkinter. Rebuild from the full repository
checkout, not from the curated source subset in the public ZIP. From the
repository root:

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
3. regenerates the flowchart source inventory;
4. stages only the reviewed public allowlist;
5. rejects every staged path under the public exclusion policy;
6. builds `LapSim.exe`;
7. runs the frozen synthetic-data-only self-test from an unrelated temporary
   directory; and
8. produces `LapSim-Windows-x64.zip`, `portable-self-test.json`, and
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
2. inspect `build-info.json` and confirm every staged project file belongs to
   the declared allowlist;
3. verify no excluded directory, course file, tire/vendor file, historical
   validation report, or team evidence appears in the archive;
4. run the exact final EXE from an unrelated current directory and clean user
   data location;
5. verify the report identifies a synthetic course;
6. verify an ordinary desktop launch, synthetic lap and replay, offline map,
   and curated source links; and
7. preserve hashes, runtime versions, source commit, dirty-worktree state,
   skipped-test reasons, and manual-check scope.

Never describe a source-only sweep as proof that a different executable passed.
Never infer data-publication authority from a successful software test.
