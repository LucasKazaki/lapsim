# E17 presentation: static tournament review

This additive page projects the accepted R11 snapshot at `4e1eeaf`; numerical
source remains `bee54e7`. It does not run a numerical campaign or change a controller.
Existing map URLs are retained. The pending new six-course campaign is explicitly
absent. The unpaired p5 immigrant is displayed but excluded from selection.

[Open the published review](https://lucaskazaki.github.io/lapsim/tournament/)
or [watch the saved video](https://lucaskazaki.github.io/lapsim/tournament/video.html).
This directory is the maintained source; the Pages artifact lives separately at
`gh-pages:tournament/`. To inspect a clean checkout locally, serve the repository
with `python -m http.server 8000` and open `/web/tournament-review/`.

## Refresh contract

From the repository root, run
`python scripts/build_tournament_review.py --review-root PATH` against the
completed review export directory. The directory must contain `review-index.json`
and the referenced `<case-id>.viewer.json` projections. The builder uses `cases`,
`final_selection.development.excluded` and the source evidence time. It groups
by both geometry SHA-256 and hardware SHA-256, keeps unmodified saved display
samples, and writes portable `data.js` plus inspectable `data.json`.

The static contract is `lapsim.static-tournament-review.v1`. Each group contains
course geometry, hardware identity, provenance, and runs. Each run contains
acceptance/status, explicit selection eligibility, controller structure/parameters,
time/energy, lap crossings, intervention metrics and fixed-order telemetry rows.
`columns` defines row fields. Course geometries or hardware strata never overlap.
New six-course results require a deliberate adapter to this contract; do not claim
coverage by copying a course map without completed matching results.

## Validation

`node scripts/test_tournament_review.cjs` checks saved coverage, heldout fastest
and energy extremes, excluded immigrant, legitimate ties, rejection of malformed
samples, endpoint interpolation, and separate hardware strata. The immigrant
assertion failed before its explicit selection exclusion was implemented.

This release displays bundled saved results only. It supports course/criterion/
strategy selection, synchronized replay, scrubbing, speed and reset. External
file loading is unavailable: both the file input and its handler are absent.
`node web/tournament-review/test-bundled.cjs` checks that absence and the bundled controls.

On Windows with Segoe UI installed, Pillow in the selected Python environment
and `ffmpeg` on PATH,
`python scripts/render_tournament_review.py` creates a 42-second H.264 MP4 from
three same-course chapters. It uses one encoder thread and enforces at least
8 GiB available commit on Windows. It does not infer or manufacture trajectories.
Source projected poses are linearly interpolated only for display.

For an independently reviewed Pages update, copy this directory to a new
`tournament/` directory in a branch based on current `gh-pages`; its map link
must use `../` rather than the source tree's `../../`. Preserve all existing
map files and publish through a normal PR. Do not copy another branch's source
tree over the Pages root or change Pages settings.
