# Browser simulator

The web app runs the repository's Python vehicle model in the viewer's browser.
It uses the same `PathConstraintSolver`, `EnduranceSimulator`, components,
course loader, solver-grid resampling, profile manifests, and schema-v2 run
records as the desktop calculation. JavaScript draws the controls and charts;
it does not substitute an approximate physics engine.

## Use and share

Open the hosted simulator in a current Chrome, Edge, Firefox, or Safari browser.
The first launch downloads a pinned Python scientific runtime and may take
longer than later visits. A Python installation is unnecessary. The page needs
access to the Pyodide CDN; this build is not a guaranteed offline web app.
The desktop executable remains the offline distribution.

Start with **Prius LE benchmark**, **Synthetic loop**, 80% torque request,
100% assumed grip, 300 psi maximum brake pressure, and 2 m maximum cell length.
Leaving the starting speed automatic uses the same cyclic braking ceiling as
the ordinary desktop lap. An explicit zero starts from rest. Changing cell
length changes numerical resolution and can change lap estimates.

Style presets select a torque request. They retain the same automatic,
predictive longitudinal braking controller and do not implement a measured
human driver, late braking, interactive steering, or a separately tuned racing
policy. Brake pressure is a **ceiling**, not an instruction to hold the brakes
at that pressure throughout the lap. Regen permission uses the selected
pack/drivetrain capacity; both initial built-in profiles have zero configured
charge-power capacity, so enabling permission does not recover energy.

Completed runs show model-estimated time, energy, SOC, and accepted-cell
telemetry. Failed runs retain a termination reason and their last accepted
prefix; attempted elapsed time must not be ranked as a completed lap time.
Download the standard run-record JSON to preserve the exact vehicle,
source/course hashes, grid, settings, software/runtime versions, and traces.
Use the desktop Python replay API described in the [team guide](team_guide.md)
to check numerical agreement; a different runtime may produce provenance
warnings even when the replay agrees.

The [simulator map](simulator_flowchart/index.html) explains the architecture,
variables, equations, and source. A host must retain its original
`docs/simulator_flowchart/` hierarchy and referenced source/docs for local links
to resolve. The main app's map is station-based playback of a reference course,
not an independently integrated vehicle pose or a swept-body clearance check.
See [simulator research](simulator_research.md) for model/control context.

## Inputs and limits

| Input | Accepted browser values | Meaning |
|---|---|---|
| Vehicle | `prius_2026_le`, `repository_baseline` | Built-in estimated profiles; no external team evidence bundle |
| Course | `synthetic_rounded_rectangle_v1`, `synthetic_fsae_endurance_style_v1`, `team_endurance_fused_gnss_imu` | Explicit source selection; synthetic courses are calculation examples |
| Grip multiplier | 0.2-1.5 | Uniform assumed tire-capacity sensitivity |
| Torque fraction | 0-1 | Requested fraction of available drive torque; controller can reduce it |
| Brake ceiling | 10-500 psi | Maximum line pressure used by path limits and controller |
| Regen permission | Boolean | Permit regeneration below SOC 1 only where hardware/pack allow it |
| Maximum cell length | 0.5-10 m | Exact same desktop resampler; requested grid must have at most 1,200 cells |
| Starting speed | Automatic (`null`) or 0-40 m/s | Selected run initial condition; excessive path-entry speed can fail |

Every numeric input must be finite and numeric. Unknown fields, Boolean
numbers, strings used as numbers, malformed/duplicate/nonfinite JSON, and
oversized requests fail before physics. The browser uses one lap, a 600 s
modeled-time limit, and the desktop's bounded 120-pass path solver settings.
Cancel terminates the worker immediately and creates a fresh worker. It does
not require cross-origin isolation or a shared interrupt buffer. A message
queued to a busy worker alone cannot interrupt synchronous Python.

## Architecture and source identity

`web/worker.js` is a **module Web Worker**. It loads pinned Pyodide **314.0.7**,
then that release's NumPy, SciPy, and Matplotlib packages. Matplotlib is loaded
for the unchanged run-record dependency metadata; no Tk or plotting GUI is
imported by the bridge. Pyodide's official documentation describes its module
worker requirement and package-loading API.
([Worker documentation](https://pyodide.org/en/stable/usage/webworker.html),
[built-in packages](https://pyodide.org/en/stable/usage/packages-in-pyodide.html))

The source archive also bundles the actual pure-Python **openpyxl 3.1.5** and
**et_xmlfile 2.0.0** distributions, including their original metadata and
licenses, from `requirements-build.lock`. The shared course module eagerly
imports its spreadsheet parser even for CSV/synthetic courses. These vendored
packages avoid a runtime PyPI request; source core imports remain unchanged.
The build environment must contain those exact versions.

The worker verifies the source ZIP's size and SHA-256 against the release
manifest, extracts it into a private virtual filesystem, and imports
`web/bridge.py` with the captured source/build identity. The exact source bytes
and mandatory shipped course data are packaged; external source evidence and
the user's files are not read. `sys.frozen` and `_MEIPASS` identify this
read-only source snapshot to the existing resource helpers, preserving the
normal profile provenance without attempting unsupported browser Git calls.

The worker accepts `init` and `run` requests. A run has a unique `requestId`
and a `settings` object using the names in `bridge.DEFAULTS`. It emits status,
ready capabilities, phase/pass-aware progress, a result, or an error. Lap
progress describes accepted cells. Constraint work is reported within its
current phase and pass; the maximum pass bound is not a percentage estimate.
Results use camelCase UI fields and preserve the standard snake_case schema
inside `runRecord`. Downloads must use `runRecordJson` verbatim: it retains
the original Python JSON number spelling and the record's content hash.
Serializing `runRecord` again in JavaScript changes some integer-looking
floats and makes the standard record fail its integrity check. The course arrays contain cell boundaries (`n+1`), while
curvature has one value per cell (`n`) and telemetry has accepted cell exits.

## Build and verify

From the source checkout after [source setup](team_guide.md):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs tests\test_web_bridge.py --junitxml=work\web-bridge-tests.xml
.\.venv\Scripts\python.exe scripts\build_web.py --output-dir dist\web
pwsh -NoProfile -File scripts\stage_team_site.ps1 -OutputDirectory dist\web
.\.venv\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory dist\web
```

Open `http://127.0.0.1:8000/`. Direct `file:` launch is unsupported because
module workers and runtime downloads need an HTTP origin. Hosting the staged
folder over HTTPS needs no Python application server. Keep all four frontend
files and `assets/` together. This helper builds frontend/runtime files;
distribution staging also includes the map, documentation, and original source
hierarchy. Hosting/publishing is a separate authorized step.

The staging command requires **PowerShell 7** (`pwsh`), including its Markdown
renderer. It adds the complete expandable map, repository-relative source
links, and rendered simulator research. The locked build environment supplies
the vendored spreadsheet dependencies; Node.js runs the JavaScript record
roundtrip regression. That one regression reports a skip if Node.js is absent.

`assets/runtime-manifest.json` records the runtime version, archive hash/size,
source commit/dirty state, source snapshot hash, and each source file hash.
Build from the exact final source after refreshing documentation/map content;
retain the manifest and test evidence with every shared revision.

Native bridge regressions verify both built-in profiles against the desktop
lap and every telemetry channel, actual brake/regen/grip settings, saved-record
replay, input and cell-count boundaries, failed prefixes, observed progress,
JavaScript roundtrip/download integrity, and source-archive execution without Tk/Git. Native tests alone cannot validate
browser package loading or WebAssembly execution. Release QA must also cold
start the actual browser worker, obtain a complete standard run record, retain
runtime versions, compare numerical metrics with CPython, and exercise
cancellation, input changes, record download, responsive layouts, and map links.

The physical assumptions and validation limits remain those in the
[team guide](team_guide.md) and [verification guide](verification.md).
The shipped fused course's x/y and curvature disagree; no browser result
repairs its geometry or establishes real-car lap accuracy.

## Measured browser verification

On 2026-10-10, actual Chrome 154 on Windows initialized the module worker and
completed both built-in profiles on the 98-cell synthetic loop. The browser
runtime was Pyodide 314.0.7, CPython 3.14.2 on WebAssembly, NumPy 2.4.6,
SciPy 1.18.0, and Matplotlib 3.10.8. It produced schema-v2 records with finite
numeric telemetry and no worker protocol errors. The two actual downloaded
Python JSON records passed `RunRecord.load` content-hash validation and the
native Windows CPython replay's model-agreement check.

| Profile | Browser time (s) | Browser pack energy (kWh) | Accepted samples | Telemetry channels compared |
|---|---:|---:|---:|---:|
| Prius LE benchmark | 17.070675616015084 | 0.0452509787836399 | 98 | 198 |
| Repository baseline | 12.20598872766873 | 0.05718866387959974 | 98 | 202 |

Time, distance, energy, and final SOC matched the native bridge exactly at
the recorded floating-point precision. Across each profile's individual
telemetry channels, the largest absolute numerical differences were
`8.881784197001252e-16` and `1.3322676295501878e-15`, respectively; each
channel's units and error are retained in the measured report. This establishes
agreement for these two model cases, not empirical vehicle accuracy.

The evidence is `work/browser-worker-validation.json`, with team deliverables
named `LapSim_Browser_Physics_QA.json`, `Browser_Run_Prius_Exact.json`, and
`Browser_Run_Baseline_Exact.json`. The bridge regression module passed all
29 cases, including the Node roundtrip and standard record replay. The final
combined bridge/map sweep passed all 33 cases in 21.68 s, with no failures or
skips (`work/web-release-tests.xml`). The complete map contains 13,151 nodes
and catalogs 80 Python modules, including the browser bridge. Actual Chrome
also expanded the whole map and collapsed it to one root, preserving direct
node URL fragments and individual input units.

The browser evidence retains two repaired integration failures: the course
module's eager `openpyxl` import initially prevented readiness, and JavaScript
number reserialization initially invalidated record downloads. Vendoring the
actual spreadsheet packages and preserving `runRecordJson` resolved them.
This measured development snapshot had uncommitted source changes; the final
shared runtime manifest records the release identity. Worker initialization
was measured after earlier CDN access, so its timing is not a cold-network
download benchmark.
