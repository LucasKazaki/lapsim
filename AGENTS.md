# ENME408 implementation-agent handoff

Start with [ENME408_IMPLEMENTATION_PLAN.md](ENME408_IMPLEMENTATION_PLAN.md) and [issue #19](https://github.com/LucasKazaki/lapsim/issues/19). The plan is an actionable remaining-work contract, not proof those features exist. Existing architecture and R01–R10 research remain relevant.

## Objective and source of truth

Make LucasKazaki/lapsim the self-contained team repository for the simulator, controller source, synthetic tests, docs and release. A clean clone or reviewed Windows package must run without Agent Studio, another checkout, API keys or private car evidence. The present task sequence is consolidation/reproducibility, bicycle baseline, constrained fixed-clock torque-control testing, then optional digital-target and isolated STM32 PIL.

No new team/Slack data are available as of 16 October 2026. Current 2026–27 car is RWD; 2027–28 AWD is provisional. Recorded MCU is STM32F405/custom PCB; exact board/interface/toolchain details are unresolved. Do not invent car values, motor count, CAN IDs, thresholds, target frequency, pins or clocks. Do not move to Teensy or make autonomous driving/game development a prerequisite.

## Before editing

- Read current main, open PR heads/ancestry, source, tests and relevant local instructions. Preserve uncommitted user work. Refresh the dated SHA table in the plan rather than resetting to it.
- E01's intended stack is #13 → #15 → #17 → #18. Exclude superseded/temporary branches. Preserve the two numerical repairs and their counterexamples.
- E02 imports only the relevant reviewed ENME408 subtree/dependencies from Studio, with licenses/provenance and actual tests. Do not merge the Studio application or substitute a viewer receipt for controller source.
- Select one bounded E-ID. Write/retain a failing regression or frozen behavior contract before a repair. Implement it; do not spend the run creating a duplicate roadmap.

## Engineering contracts

- Keep model family, vehicle profile, topology and controller backend distinct. New basic dynamics sessions use a synthetic bicycle once implemented; independent-wheel allocation requires the four-wheel plant. Preserve old saved model selections.
- Controller ticks, plant substeps, sensor arrivals, logging and UI frames are separate clocks. Do not step the controller inside RK4 force calls or once per distance cell.
- Use the same numerical controller core for host and target adapters. Record requested, proposed, guarded/limited and achieved output separately. Preserve rejected raw candidates and fault state.
- No hidden private-path/runtime dependency, post-hoc energy/SOC clipping, fabricated calibration, silent backend fallback, stale result display or tests weakened to force a pass.
- Keep the source map and docs consistent when code changes. Audit browser/desktop effective-grid parity, not only browser/native reuse of the same helper.
- Follow the detailed release, controller and STM32 contracts under docs/. Proposed filenames/commands in those documents are future interfaces until implemented and tested.

## Hardware boundary

Default execution is simulation-only. No automatic serial/CAN connection, firmware flash, option-byte change, inverter command or live vehicle action. Build/flash/connect/run are distinct actions. Hardware work requires explicit device/image selection and verified board information. Bench firmware returns data to the PC plant with no physical actuator connection. Emulation, native C and object compilation are not hardware/timing validation.

## Checks and completion

Use the current project's declared environment and isolated test runner where needed; existing entrypoints include `python scripts/check_all.py`, `python scripts/check_flowchart_site.py`, `python docs/simulator_flowchart/generate_inventory.py --check`, and `node scripts/check_flowchart_data.mjs`. Confirm prerequisites/paths against the checked-out revision. Run focused tests first, then relevant full/native/browser/frozen/quality gates. Do not claim Windows or hardware checks from a different OS/mock environment.

Record exact source/config/toolchain IDs, actual commands and exits, counts including failures/skips, and example run/receipt paths. Compare against a fixed diagnostic baseline; do not blanket-suppress type/lint debt or change branch protection. Merge only reviewed exact-head candidates through normal rules. Rebuild/redeploy separately and verify the artifact people will receive.

Update issue #19 using: E-ID; implemented scope; commit/PR; commands/environment; evidence; limitations; next dependency. Keep unchecked work open. A docs commit does not finish E01–E14. A test pass does not establish car calibration or safety approval. End each implementation tranche with inspectable code/tests/results, not an unsupported quality claim.
