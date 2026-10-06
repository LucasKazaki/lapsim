# Versioned course bundles

The desktop **Import course…** button accepts a single UTF-8 JSON course bundle.
This is the path for selecting a team-prepared course revision without editing
Python. The ordinary **Centerline (default)** mode remains the default after an
import. An imported course is also available to car comparisons and the
optional experimental racing-line planner.

The converter produces v1 by default. Its optional v2 mode stores left and
right widths at the **source geometry's cell starts** with their own provenance.
The current AI planner still uses its separately declared uniform width
assumption: its path has a different reference frame, and the required
source-to-planner path-frame transformation has not been implemented.

The built-in **Synthetic FSAE-style · practice** option is a separate analytic
example and needs no import. Its 817.079633 m closed centerline repeats four
copies of 60 m straight, 30° left turn at 15 m radius, 45 m straight, 30° right
turn at 15 m radius, 60 m straight, and 90° left turn at 15 m radius. Four
quarter turns close the path without adjusting its plotted coordinates; all
source cells are at most 0.5 m. The design draws on [2027 Formula SAE Rules
v1.0, D.12.2.2](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38)
for its general scale and variety of turns. It is not an official event layout
or a claim of rule compliance: there is no surveyed centerline, cone boundary,
passing zone, or measured width. The desktop's starting ±3 m AI half-width is
an editable scenario assumption. Saved runs label its source as synthetic and
record the generator and source geometry hash.

## Prepare a source CSV

A bundle represents one closed lap as exact, piecewise constant-curvature
straight or circular arcs. The source CSV needs these four columns:

| Column | Meaning |
|---|---|
| `distance_m` | Cumulative station in metres, starting at zero and strictly increasing. |
| `x_m`, `y_m` | One local Cartesian point at each station; the final point repeats the start. |
| `curvature_per_m` | Signed curvature of the cell **starting** at this row; leave the final endpoint row blank. Positive is counterclockwise in the declared right-handed x/y frame. |

For example, this four-cell analytic circle has radius 10 m and travels
counterclockwise. It is a software example, not an event survey:

```csv
distance_m,x_m,y_m,curvature_per_m
0,0,0,0.1
15.707963267948966,10,10,0.1
31.41592653589793,0,20,0.1
47.12388980384689,-10,10,0.1
62.83185307179586,0,0,
```

Raw GNSS points, a plotted polygon, or a curvature trace do not automatically
satisfy this contract. In particular, the repository's shipped fused 989 m
recording fails the x/y-versus-curvature coherence check. The converter rejects
it; wrapping it in new metadata would not fix its numerical geometry.

## Create and import a bundle

With the project virtual environment active, run the converter from the
repository root. Treat a revision as immutable within the team: supply a
fresh revision whenever the geometry **or any manifest field** changes. The
desktop enforces this rule against the course revisions in its local catalog:

```powershell
.venv\Scripts\python.exe scripts\create_course_bundle.py .\course.csv .\course_r1.json --course-id analytic_practice --revision r1 --label "Analytic practice loop" --description "Synthetic closed solver example; no surveyed boundaries" --source-kind synthetic --source-name "Four quarter-circle arcs" --processing-method "Analytic circle geometry" --review-note "Software fixture only" --frame-origin "first point" --frame-x-axis east --frame-y-axis north --travel-direction counterclockwise
```

`--source-kind measured` is a **declared provenance claim**. The converter
automatically hashes the exact source CSV bytes but does not establish that a
survey occurred or that the map matches the physical event. Use `synthetic`
for analytic examples. The optional `--ai-half-width-m`,
`--ai-vehicle-width-m`, and `--ai-safety-margin-m` flags set *assumed* starting
values in the desktop. They never become measured boundaries, including in v2.

The converter checks the CSV and saves a bundle only if it passes. It checks
that the output path is free before saving; do not have another process write
to that path during conversion. In the desktop, press **Import course…** and
select the new JSON file. The chosen revision appears in **Course**. Lap
records freeze its identity and exact solver grid. The app keeps a local copy
at `%LOCALAPPDATA%\LapSim\courses\<bundle_sha256>.json` and reloads it into
the course menu on the next launch. A bad saved file is skipped with a warning.
The catalog accepts at most 64 JSON files so startup work stays bounded.

## Add source-cell widths with v2

Pass `--corridor-csv` to opt in to schema version 2. Its UTF-8 CSV has exactly
these columns and one row per validated source cell, in source order:

```csv
distance_m,left_width_m,right_width_m
0,2.5,2.7
15.707963267948966,2.4,2.6
31.41592653589793,2.3,2.5
47.12388980384689,2.4,2.6
```

This example pairs with the four-cell circle above. `distance_m` is the
starting station of a source cell, not the closure endpoint. Widths are
positive distances in metres toward the left and right normal of the source
path as traveled. They are attached to source cells, not surveyed x/y boundary
points or a tested vehicle envelope. Their only numeric width requirement is
that every value be finite and positive; a width may be narrower than the
configured vehicle or margin. The converter rejects extra, missing, duplicate,
nonfinite, or misaligned rows, and requires each station to match the
validated source cell start within **1e-9 m**. Both CSV inputs are limited to
4 MiB and are hashed from their exact bytes.

For the example's synthetic geometry, create an assumed-width v2 bundle:

```powershell
.venv\Scripts\python.exe scripts\create_course_bundle.py .\course.csv .\course_with_widths_r1.json --course-id analytic_practice --revision widths-r1 --label "Analytic practice loop" --description "Synthetic circle with declared source-cell widths" --source-kind synthetic --source-name "Four quarter-circle arcs" --processing-method "Analytic circle geometry" --review-note "Software fixture only" --frame-origin "first point" --frame-x-axis east --frame-y-axis north --travel-direction counterclockwise --corridor-csv .\widths.csv --corridor-status assumed --corridor-source-name "Scenario width table r1" --corridor-processing-method "Per-cell assumed normal distances" --corridor-review-note "Illustrative source-relative widths; no field survey"
```

`--corridor-status` is `assumed` or `measured`. `measured` is accepted only
when `--source-kind measured`; both labels remain self-declared provenance.
The four corridor flags for status, source name, processing method, and review
note are required with `--corridor-csv`. Omit all five flags to produce v1.
Use a fresh revision if the width CSV or its provenance changes.

V2 keeps the v1 top-level fields and adds `corridor`. Its exact fields are:

| Field | Requirement |
|---|---|
| `model` | `left_right_normal_offsets_from_source_geometry`. |
| `reference_geometry_sha256` | Must equal the validated source `geometry_sha256`. |
| `status` | `assumed` or declared `measured`; determines top-level `boundary_status` as `source_normal_offsets_assumed` or `source_normal_offsets_measured`. |
| `left_width_m`, `right_width_m` | One finite, positive number for each source cell, excluding the closure endpoint. |
| `provenance` | `source_name`, exact corridor CSV byte `source_sha256`, `processing_method`, `review_note`. |
| `corridor_sha256` | SHA-256 of the normalized corridor object excluding `corridor_sha256`, serialized as UTF-8 JSON with sorted keys and compact separators. |

The canonical `bundle_sha256` covers the whole normalized v2 manifest,
including the corridor and its hash. The loader checks both hashes on import.
The corridor fields record a source-relative width claim. A planner path can
shift or smooth the source path; applying these widths to that new path needs
a checked path-frame transformation. Until that exists, the AI uses
`ai_defaults.width_source: assumed_uniform` and does not use the v2 widths.

## Exact v1 contract and hashes

The JSON manifest has exactly these top-level fields:

| Field | Requirement |
|---|---|
| `schema_version` | Integer `1`. |
| `course_id`, `revision` | Path-free identifiers; together identify one revision. The desktop rejects conflicting content for a pair already in its local catalog. Team data management must preserve that immutability across computers. |
| `label`, `description` | User-facing name and scope. |
| `source_kind` | `synthetic` or declared `measured`. |
| `provenance` | `source_name`, `source_sha256`, `processing_method`, `review_note`. A measured claim requires a source SHA-256. |
| `coordinate_frame` | Type `local_cartesian_right_handed_xy`, units `m`, plus explicit origin and positive x/y axis descriptions. |
| `travel_direction` | `clockwise` or `counterclockwise`, checked against the lap's signed turn. |
| `boundary_status` | `absent` in v1. The format cannot carry surveyed boundaries yet. |
| `ai_defaults` | `width_source: assumed_uniform` and positive half width, vehicle width, and nonnegative side margin, leaving usable width. |
| `geometry` | `model: piecewise_constant_curvature_arcs`, `closed: true`, `distance_m`, `x_m`, `y_m`, and `curvature_per_m` arrays. |
| `geometry_sha256` | SHA-256 of normalized solver geometry, checked on load. |

The loader accepts 4–5,000 source cells and at most 4 MiB of JSON. Frame
handedness, origin, and axis descriptions are **declared metadata**; this
format cannot independently verify their relationship to a survey. It rejects
duplicate keys, nonfinite numbers, mismatched arrays or hash, inconsistent
arc endpoints, an open position or heading seam, and a signed lap turn other
than the declared ±2π direction. The default arc/closure position tolerance
is **1e-6 m** and heading tolerance is **1e-6 rad**; total signed turn must
agree with the declared direction within **1e-6 rad**. A requested centerline step may only retain
or analytically subdivide validated source arcs; the desktop checks the
resulting 5,000-cell cap before running. A coarser step does not merge arcs.
These checks establish **internal numerical coherence**, not lane, cone,
width, elevation, grip, or vehicle-tracking validity.

Each saved run has `settings.track.geometry_sha256` for the **actual solver
grid** and `settings.track.source_course` for the selected source. For an
import, the latter includes its course ID/revision, source geometry hash,
canonical manifest `bundle_sha256`, declared raw-source hash, and
`loaded_bundle_file_sha256`. The final field hashes the exact JSON bytes that
this app launch loaded. It can change when the same manifest is serialized as
a local copy; the canonical `bundle_sha256` stays stable. Built-in legacy and
synthetic courses have source artifact/generator identity but no bundle hash.

For a team engineering decision, retain the source CSV, any corridor CSV, the
bundle, the saved run JSON, and the processing/review notes together. V2 can
carry declared measured source-normal widths but no world-frame surveyed
boundary points or surveyed car pose. AI clearance remains an explicitly
assumed scenario, and a modeled time is not a measured lap or a certified
Formula SAE course result.
