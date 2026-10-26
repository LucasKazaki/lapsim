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
`python scripts/build_tournament_review.py --review-root PATH --acceptance-commit COMMIT --numerical-checkpoint COMMIT` against the
completed review export directory. The directory must contain `review-index.json`
and the referenced `<case-id>.viewer.json` projections. The builder uses `cases`,
`final_selection.development.excluded` and the source evidence time. It groups
by both geometry SHA-256 and hardware SHA-256, keeps unmodified saved display
samples, and writes portable `data.js` plus inspectable `data.json`.
An indexed missing viewer stops the export before any output is written.
Coverage counts come from the indexed records. Source identities must be supplied
explicitly; the renderer validates and displays those identities and the recorded
evidence timestamp instead of using fixed historical labels.

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

## Simulated points and parameter display

This source candidate defaults to endurance plus efficiency, up to 275 + 100
points, separately for each geometry/hardware/equal-lap field. It is an explicitly
FSAE-inspired simulated adaptation of SAE 2027 V1 D12.13 and D13.3-4, not official
event points. The R11 snapshot has no real driver change, inspection or event
penalty model. No six-course aggregate is inferred. Fastest, lowest net energy
and the historical engineering proxy remain explicit alternative criteria.
The unchanged MP4 still highlights fastest and is labeled accordingly.
An always-visible three-winner comparison shows fastest, highest simulated
points and lowest net energy with raw time/energy and component points from the
same completed accepted selection pool. Its highlight buttons use the same
synchronized saved ghosts, and legitimate co-winners are retained.

`scoring.js` projects the canonical `tournament_scoring.py` field contract. The
frozen fixtures record the exact canonical commit and source SHA-256 from PR #145 (canonical scorer repair).
`node scripts/test_tournament_scoring.cjs` compares 17 canonical fixtures,
including all five saved strata, ties, changed ranking, failed runs, invalid
references, penalties, eligibility caps and nonfinite intermediate guards.
The Node production-control suite verifies the actual default, reset, component
table, missing telemetry labels and all selection/replay controls.

For this earlier snapshot the required raw time, net energy, course length and
equal lap count are available. References use the recorded selection pool;
unpaired p5 is excluded. Net energy already credits regeneration. Recovered Wh
is unavailable here, and penalties are labeled not modeled. If a future adapter
supplies `run.fsae_inspired_points`, the display consumes the versioned canonical
row including `field_available` and optional `recovered_wh_10ms`. Partial or
unknown canonical fields make the combined field unrankable instead of silently
recomputing it. A future adapter must preserve matched strata and coverage.

Parameter cards use short values with units and percentages. Exact executed
parameters and identities remain in details and in the downloadable JSON. Origin
labels derive from recorded profile IDs, heldout ancestry and generation
`parents_used`; the elite pool is not misrepresented as actual parents. Seeded
continuous samples and mutations explain non-round executed values. Formatting
does not change any executed value or rerun a controller.

Source integration does not publish these changes. The public presentation may
still show the earlier version until a separately reviewed Pages release.

On Windows with Segoe UI installed, Pillow in the selected Python environment
and `ffmpeg` on PATH,
`python scripts/render_tournament_review.py` creates a 42-second H.264 MP4 from
three same-course chapters. It uses one encoder thread and enforces at least
8 GiB available commit on Windows. It does not infer or manufacture trajectories.
Source projected poses are linearly interpolated only for display.
The renderer marks failed and excluded outcomes explicitly. A chapter with no
eligible completed run stays visible and unranked while other chapters render.
`python -m unittest discover -s tests -p test_tournament_render_frames.py -v`
exercises the production frame functions for these cases without an encoder.

For an independently reviewed Pages update, copy this directory to a new
`tournament/` directory in a branch based on current `gh-pages`; its map link
must use `../` rather than the source tree's `../../`. Preserve all existing
map files and publish through a normal PR. Do not copy another branch's source
tree over the Pages root or change Pages settings.
