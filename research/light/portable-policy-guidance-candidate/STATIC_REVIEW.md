# Static source review record

Date: 5 November 2026. Scope: this source candidate only, based on main
`07ccb4b84138aedcc5b9cb85c2e81d283d6c132e` and portable-core origin
`eda45185a4debeae7239dce906b72cfdf3909da9`.

**No candidate imports, syntax checks, executable tests, builds, simulations,
benchmarks, resource probes or numerical jobs were performed.** Read-only source,
Git diff and file-identity inspection are the evidence below. These reviews do
not establish runtime correctness, accuracy, qualification or absence of bugs.

## Policy and guidance review

An independent GPT-6.1 Sol reviewer compared the candidate against the pinned
archived policy/adapter/contracts and main guidance source. The first pass found
no concrete extraction regression, but could not inspect the portable core
because it was absent from the checkout. The exact pinned core source was then
copied into this candidate and a second read-only pass inspected that dependency.

- `policy_layers.py` retains its archival bytes. Registry changes its import;
  adapter changes dependency bindings and its fixed OFF metadata type.
- Allocation, actuator-limit antiwindup, common brake blend and retained driver
  projection/preview/pursuit/edge formulas have no intentional numerical edits.
- The new public demand helper calls the original driver once and strict AWD
  normalization once; it advances no clock or plant.
- All 11 copied core Python files retain PR #166 Git blob identities. Inspected
  imports refer to standard-library modules or the included namespaces. Referenced
  exported names exist in those source files. This was not an executed import.
- Guidance and command normalization bind the same portable `PlanarControls`
  definition; adapter type/function bindings refer to the copied actuation core.

## Raw-journal review and repair

A separate independent GPT-6.1 Sol reviewer inspected storage ordering, raw
lineage, body/envelope limits, quota reserve and commit/recovery separation.
It found one concrete defect: the first journal version applied the bridge's
256 KiB checkpoint-body cap to the whole checkpoint envelope. A bridge-valid
near-limit body could therefore be rejected by storage.

The source now keeps distinct body/envelope bounds for both checkpoint and chunk
records. Stored checkpoint reads/writes use the envelope bound; validation also
retains the original body bound. A follow-up read-only review found that defect
resolved in the affected paths. No new concrete issue was identified there.

The reviewer also confirmed an integration limit: every terminal record,
including `paused_budget`, closes this store. Continuation is not implemented.
The guide and method docstring now state that explicitly. A future continuation
protocol needs its own parent-manifest/terminal/checkpoint/admission/fresh-resource
contract; no local JSON or storage digest supplies that authority.

## Remaining limits

Source inspection cannot establish actual import/build success, behavioral or
numerical equivalence, crash/power-loss behavior, Windows behavior or end-to-end
execution. The original bridge remains responsible for full physical/telemetry
validation; the original guarded owner remains responsible for authenticated
inputs, execution/cleanup receipts, exclusive ownership and fresh resource bounds.
No tournament runner, admission override, automatic resume or completed result
is provided. Those integration and later authorized qualification gates remain
open as described in `README.md`.
