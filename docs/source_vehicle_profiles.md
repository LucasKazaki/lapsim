# Source-aware vehicle profiles

LapSim has four named vehicle choices. `repository_baseline` constructs the
current `Vehicle()` defaults. `prius_2026_le` uses the desktop app's simplified
Prius benchmark. The two TREV5 choices are opt-in partial working scenarios:
`trev5_working_geometry` and `trev5_working_geometry_aero`. They appear when a
local ENME408 evidence bundle is available. A TREV designation in that bundle
does not establish a released model year or complete car configuration.

The bundle remains external to this repository. By default, the loader looks
in the current user's `Downloads/ENME408_LapSim_Data_Integration/ENME408_LapSim_Data_Integration`
folder. Set `LAPSIM_DATA_BUNDLE` to use a different private location. No source
record is applied merely because the bundle is present.

## Python API

```python
from lapsim.profiles import (
    browse_records, build_vehicle, list_profiles, preview_profile,
)

choices = list_profiles()
vehicle, manifest = build_vehicle("trev5_working_geometry")
source_rows = browse_records(profile_id="trev5_working_geometry", subsystem="Vehicle")
coverage = preview_profile("trev5_working_geometry").to_dict()
```

`build_vehicle()` validates all selected bindings, then constructs a fresh
model. It returns a `ResolvedManifest` with source IDs, evidence labels,
conversions, model-use classifications, inherited defaults, an exact snapshot
of model constructor settings, source hashes, code commit, and dirty-checkout
state. Store run inputs with `manifest.with_run_context(...)` and call
`manifest.save(path)` to export JSON. Saved manifests do not follow later
edits to the active vehicle.

`browse_records()` returns the original value and unit, evidence status,
source locator, caveat, and a use status for each indexed parameter. Filters
include `subsystem`, `configuration`, `source_id`, `model_use`, and `query`.
Unknown values remain null; a known zero remains numeric zero. Source records
with no current model binding stay browseable. The importer retains unknown
JSON fields for later revisions.

## Headless commands

Run from the repository folder after installing the project into `.venv`:

```powershell
.venv\Scripts\python.exe -m lapsim.profiles profiles
.venv\Scripts\python.exe -m lapsim.profiles validate $env:LAPSIM_DATA_BUNDLE
.venv\Scripts\python.exe -m lapsim.profiles records --profile trev5_working_geometry --subsystem Vehicle
.venv\Scripts\python.exe -m lapsim.profiles preview trev5_working_geometry
.venv\Scripts\python.exe -m lapsim.profiles smoke repository_baseline trev5_working_geometry --distance-m 20
```

`import BUNDLE PRIVATE_STORE` makes a verified byte-preserving copy under an
external private directory. Repeating the same import is idempotent; a changed
manifest receives another revision directory. The original workbooks and raw
cell extracts remain evidence. The optional `--output` flag on `preview` and
`smoke` writes a local JSON file; keep files containing source selections out
of the Git repository.

## Interpretation

The adapter has an allowlist of current public vehicle fields. It checks source
identity, units, finite values, and declared conversions before applying any
selection. The source reference area, drag coefficient, and signed lift
coefficient are one atomic aero selection. Axle heights are represented in
telemetry but do not currently affect suspension forces. Geometry and aero
choices retain the current model's tire fit, motor/pack limits, brake model,
roll-dependent aero behavior, and other unselected defaults. The manifest
names these inherited model settings. The Prius uses an equivalent power
source and several explicit engineering estimates.

The short straight smoke scenario checks that the adapter and current event
solver can execute with finite outputs. Its time differences show sensitivity
to the selected inputs; they do not validate real-car performance, controller
behavior, or future AWD hardware. Calibration still needs verified vehicle
identity and mass condition, tire force data, powertrain limits, and measured
track or event data.
