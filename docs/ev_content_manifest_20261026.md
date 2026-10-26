# EV source integration manifest, 26 October 2026

This is a curated content integration, not a merge of all local history.
PR #128 starts at public main b25774c and adds 75 relevant files/changes.
PR #132 adds explicit controller input/type contracts and the generated source
catalog; PR #136 repairs legacy pose radii and the expanded catalog test.
The next narrow update fixes the second decimal ternary identified by the
security parser. None of these PRs deploys the live presentation directly.
Main integration awaits exact-head checks, parent review and presentation-freeze
release if main's deployment workflow would affect the live site.

| Included requested capability | Source content |
|---|---|
| Five inspected public event-map approximations and existing fused trajectory | `configs/courses/`, deterministic converter, provenance/scale/hash records and geometry/plant-wiring tests |
| Validated course picker, replay and tournament inputs | `courses/library.py`, `web/course_library.js`, single-lap selector and bundle validation |
| Shared local controller/configurator workflow | `torque_configurator/`, validated synthetic profiles, standalone CLI and simulator adapter |
| Distinct hardware architectures | Existing legacy rear channels, one-motor open differential, one-motor spool, four independent AWD; shared torque/power/regen constraints and regression tests |
| Continuous simulated rounds and analysis | Lap ledger, tournament/sweep/server, signed policy/search modules, raw torque-stage telemetry/CSV and WebGL replay |
| Simulation source packages | Versioned bounded trace/configuration export; no road-ready firmware or physical validation claim |
| Existing source map | Generated inventory refreshed; curated flowchart presentation is preserved |

Intentionally excluded: private historical commits, ENGL/RSC2/chess work,
private team research and personal paths/contacts, raw reference images with
uncertain redistribution rights, local environment/tool installs, generated
work-directory logs and incomplete results presented as final. Existing public
main files/deletions were preserved. Repository and third-party license choices
are unchanged; AMZ FSSIM and Three.js notices accompany their reused content.

Later local commits remain separate: 09b6a08 records the course increment;
4866738 implements the frozen CPU campaign; 7602fbe adds the review-data adapter
and replay repairs. The running campaign's numeric inputs/source are frozen;
postprocessing can rescore raw outcomes without rerunning them. Those local
commit identities are not a claim that their entire private ancestry is public.

The CPU campaign stages output under `work/online-campaign-20261026/`:
`plan.json`, `coverage.json`, per-run raw records/results, `review-index.json`
and `<case-id>.viewer.json`. Thirty eligible family/pedal candidates across
AWD/open-RWD/spool strata require six courses each (180 rows); six existing
fixed/no-regen references are reused. Inactive yaw variants are not counted as
one-motor diversity. Configured signed-grammar long-course runs remain explicitly
unsupported by the existing 60-second configured one-lap contract.

New scoring is being staged separately in `experiments/tournament_scoring.py`
with regression tests and review-data fields. It adapts SAE 2027 V1 D12.13 and
D13.3–4 into simulated endurance (275 max) plus efficiency (100 max), averaged
equally across six courses only after full valid coverage. It is not official
event points: one lap substitutes endurance, completion credit is simulated,
and driver-change/inspection/event penalties are not modeled. Raw time, net
energy and failures remain available for independent rescoring. The earlier
seconds-plus-kWh proxy is retained only as a historical diagnostic.

Final curated results and scoring code need their own reviewed source/release
increment after validation. The presentation owner controls publication of
`/tournament/`; current staged six-course data must not overwrite the live prior
R11 presentation during its freeze. Do not label partial coverage a final winner.

Fidelity note: the legacy yaw reference uses a fixed 1.6 m wheelbase, bounded
integral and 25 N m differential cap as synthetic controller choices. The
current legacy hardware sweep does not expose wheelbase as a variable. General
vehicle-profile wheelbase support needs a versioned audit before claiming
arbitrary-vehicle controller calibration; frozen runs must not be silently
retuned. None of these tuning constants is a verified team hardware parameter.
