# E17 presentation: static tournament review

This additive page projects the accepted R11 snapshot at `4e1eeaf`; numerical
source remains `bee54e7`. It does not run a numerical campaign or change a controller.
Existing map URLs are retained. The pending new six-course campaign is explicitly
absent. The unpaired p5 immigrant is displayed but excluded from selection.

## Refresh contract

Run `python scripts/build_tournament_review.py --review-root PATH` against the
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

The page supports course/criterion/strategy selection, synchronized saved replay,
scrubbing, speed, reset, and validated local review loading. Invalid loads retain
the current valid review and display an error. No upload is sent to a server.

`python scripts/render_tournament_review.py` creates a 42-second H.264 MP4 from
three same-course chapters. It uses one encoder thread and enforces at least
8 GiB available commit on Windows. It does not infer or manufacture trajectories.
Source projected poses are linearly interpolated only for display.
