# Public course expansion, 26 October 2026

Five distinct, inspected public event diagrams are now original approximate
centerline geometry. Source images are retained locally for inspection and are
not redistributed. All five are labeled **IMAGE-DERIVED APPROXIMATION**.

| Course | Source | Scale and limitations |
|---|---|---|
| Michigan 2019 | [Kansas State event description](https://www.k-state.edu/powercatmotorsports/competitions/description-of-events.html) | Assumed 0.61 m/pixel from the shared venue envelope; +/-25% dimensional uncertainty. |
| Michigan 2022 | [SAE map](https://www.fsaeonline.com/app/MapViewer.aspx?mapid=16ac972c-efbe-45b2-804c-6b2558087380) | Feet grid converted by 0.3048 m/ft; estimated 0.762 m/pixel, +/-10%. |
| Michigan 2023 | [SAE map](https://www.fsaeonline.com/app/MapViewer.aspx?mapid=eef9708f-405f-4190-b8f4-92192ce9ab04) | Feet grid converted; estimated 0.762 m/pixel, +/-10%. |
| Electric 2024 | [SAE map](https://www.fsaeonline.com/app/MapViewer.aspx?mapid=dc39d869-4e3a-454b-9be4-3e76cc46f9c6) | Small feet grid; estimated 0.762 m/pixel, +/-20%. |
| FS East 2017 preliminary | [Organizer source](https://fseast.eu/merry-christmas/) | Published 670–730 m range; centerline scaled to 700 m. Speed colors are not speed limits. |

Michigan years share pavement but have separately traced cone routes. Traces
retain major slaloms, braking approaches, changing-radius turns and hairpins;
individual cone placement and pit/driver-change spurs are omitted. All widths
are assumed uniform 6 m. Source arrows determine direction where shown, with
selected timing seams explicitly assumed. `online_image_traces.json` records
pixel vertices, exact image URLs, SHA-256s, scale and uncertainty. Tangent fillets
close analytically; no endpoint correction or surveyed accuracy is claimed.

The sixth campaign course uses the actual existing public fused GNSS/IMU XY
trajectory at pinned main `b25774c7c9a6ca749a0e2fa8cc11cf53392be83c`.
Every tenth fused XY sample is reconstructed as coherent tangent arcs. Its
original complementary IMU curvature is not reused, and the original 0.760 m
closure residual is recorded. This is a trajectory-derived approximation, not
a generic loop, a new sensor fusion result or physical validation.

Generate/check: `python scripts/build_online_courses.py [--check]`.
Focused tests: `python -m pytest tests/test_online_courses.py tests/test_course_library_web.py -q`.
Guarded single-lap validation: `pwsh -NoProfile -File scripts/run_online_courses_guarded.ps1 -Phase accept -Attempt UNIQUE -Candidate COURSE_ID`.
Results stay under `work/evidence/online-courses-*` with full records, summary,
stdout/stderr and resource receipts. Failed runs are retained and unranked.

The legacy 60 s diagnostic limit remains the default. Explicit validated-bundle
single-lap mode permits up to 300 simulated seconds with the existing maximum
200000 integration-work allocation. The unchanged resource guard admits at
10 GiB commit headroom, preserves 8 GiB, uses one native thread and a 180 s wall
limit. Configured source exports retain their existing explicit duration bounds;
long-course configured exports are not implemented by this change.

The numerical backend is CPU Python. Presence of an RTX 5080 or WebGL rendering
does not establish GPU physics. No CUDA array/JIT backend is installed in the
project environment. CPU execution was explicitly approved at 20:50 UTC and
is running sequentially with unchanged resource guards. Snapshot 2026-10-26T21:45:07.804325+00:00:
62/180 valid completed rows, 118 unrun. Live local coverage is in
`work/online-campaign-20261026/coverage.json`. GPU work is deferred. No final
all-strategy winner or official FSAE/real-car optimality claim is established.
The staged scoring adaptation uses separate 275/100 endurance/efficiency
components; see `ev_content_manifest_20261026.md` for content/release boundaries.

Open `http://127.0.0.1:8767/web/tournament.html` after starting
`python -m lapsim.torque_configurator serve --port 8767` from the selected checkout.
The shipped picker supplies the exact bundle to search and replay. Select one
lap for the new long courses. Earlier ten-lap fixtures remain available. This
branch includes the previously local shared controller, topology, tournament
and replay infrastructure required to run these courses, without importing
private historical commits or research. Publication does not update main or
deploy GitHub Pages. Hardware actuation and firmware flashing are excluded.
