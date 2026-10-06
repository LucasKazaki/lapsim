# Versioned course bundles

The desktop **Import course…** button accepts a single UTF-8 JSON course bundle.
This is the path for selecting a team-prepared course revision without editing
Python. The ordinary **Centerline (default)** mode remains the default after an
import. An imported course is also available to car comparisons and the
optional experimental racing-line planner.

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

A v1 bundle represents one closed lap as exact, piecewise constant-curvature
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
values in the desktop. They never become measured boundaries.

The converter checks the CSV and saves a bundle only if it passes. It checks
that the output path is free before saving; do not have another process write
to that path during conversion. In the desktop, press **Import course…** and
select the new JSON file. The chosen revision appears in **Course**. Lap
records freeze its identity and exact solver grid. The app keeps a local copy
at `%LOCALAPPDATA%\LapSim\courses\<bundle_sha256>.json` and reloads it into
the course menu on the next launch. A bad saved file is skipped with a warning.
The catalog accepts at most 64 JSON files so startup work stays bounded.

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

For a team engineering decision, retain the source CSV, the bundle, the saved
run JSON, and the processing/review notes together. The imported file does
not yet include measured left/right boundaries or a surveyed car pose. AI
clearance remains an explicitly assumed scenario, and a modeled time is not
a measured lap or a certified Formula SAE course result.
