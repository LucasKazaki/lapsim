# Source setup and installed packages

With 64-bit Python 3.11+ and Tk, run this from the repository root:

```text
python scripts/bootstrap.py --launch
```

The script finds its own project when invoked by absolute path from another
directory. It creates a project-local `.venv`, installs the declared source
dependencies, executes synthetic bicycle/controller replay checks, verifies
Tk/display and launches the desktop. Initial installation may need internet.
No AI account, sibling Studio checkout, compiler, emulator or hardware is needed.
The current local qualification uses Windows CPython 3.13.15; Linux CI runs the
same source, installed-package and desktop checks with a virtual display.

After setup, repeat checks without installation or environment changes:

```text
python scripts/bootstrap.py --check
python scripts/bootstrap.py --check --desktop
```

The second command needs a usable desktop/display. A repeated launch uses the
verified environment; it does not reinstall unchanged dependencies. The package
verification workflow actually repeats the read-only check with unusable network
proxies and verifies that the ready marker's bytes and modification time remain
unchanged. Existing incomplete/incompatible environments are preserved and fail
with an actionable error. Select a separate project-local environment with
`--environment "work/my environment"`; source directories are protected.

Developers can add the small test dependencies and run the isolated full suite:

```text
python scripts/bootstrap.py --dev
.venv/Scripts/python.exe scripts/check_all.py
```

On Linux replace `.venv/Scripts/python.exe` with `.venv/bin/python`. The source
dependency ranges are flexible; they are distinct from the exact Windows build
lock. Do not install the Windows release lock into an unsupported Python version.
The retained `setup_lapsim.cmd` delegates to this Python setup without overriding
PowerShell execution policy. `launch_lapsim.cmd` remains available after setup.

For an executable-level source UI/replay check that exits automatically:

```text
python scripts/bootstrap.py --launch --desktop-self-test work/desktop-check.json
```

## Wheels and source distributions

Development packaging uses the normal Python build interface:

```text
python -m pip install build==1.3.0
python -m build
python -m pip install dist/python_lapsim-0.1.0-py3-none-any.whl
python -m lapsim.diagnostics --desktop
python -m lapsim.desktop
```

The wheel includes the declared read-only source/resource closure under
`lapsim/_resources`, with the actual 419-file original controller inventory,
reviewed relocation patches, required data/help/source files and captured build
identity. The sdist carries these build inputs and a source-identity capture;
a wheel built from it preserves the selected file hashes. Installed execution
uses the bundle, never an unrelated caller directory or ancestor Git repository.
Source snapshots without Git use their own capture and mark changed/missing
source bytes dirty. Old numerical receipts are preserved.

Windows extended paths are used for controlled long-file copies and byte reads;
library roots and browser links retain ordinary paths so existing `..` lookups
work. No global long-path registry setting is changed. The actual test machine
had long paths disabled; the original frozen documentation copy failure and
the installed extended-path incompatibility remain in local verification logs.

The verification entry point builds a wheel and sdist, installs both into new
environments in paths with spaces/non-ASCII characters, checks every captured
resource/module hash, runs all 538 imported reference tests in each, executes
installed desktop/replay self-tests, then bootstraps the extracted source
snapshot from an unrelated working directory:

```text
python quality/run_package_runtime.py --output-dir work/package-check-1 --desktop
```

Choose a new output directory to preserve earlier attempts. Full compiler/native
reference checks are development qualification, separate from ordinary startup.
Only synthetic results, checksums and logs are uploaded by CI; wheel/sdist/EXE
packages are not published by that workflow.

Public release remains deferred. Internal packages currently retain the existing
repository GNSS/TIR resources; their redistribution permissions and the project
license remain publication gates. The hosted site is a separate older build.
See [the release contract](team_release_contract.md) and
[runtime acceptance contract](package_runtime_contract.md).
