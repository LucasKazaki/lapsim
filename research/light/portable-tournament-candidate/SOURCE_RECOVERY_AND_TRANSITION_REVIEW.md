# Source recovery and committed-transition review

Base: `17bb284dea891a61331e18c74c4c07a8b72cfe86`.
Bounded E07 source tranche. **UNTESTED / UNBUILT / UNQUALIFIED.**

## Supported read-only recovery evidence

Space listing completed both returned cursors with no accessible Space roots.
Page listing completed its cursor and returned three personal Pages. The one
relevant native artifact is [LapSim | ENME408 EV Meetup](<PRIVATE_HANDOFF_PAGE>),
dated 19 October 2026, native sequence 2. A read-only native-artifact inspection
returned the five slides' text with status `no_changes`, no committed sequence,
no image hydration and no rendering. It describes earlier simulator work and
future validation; the inspected text contains no original light predicate,
producer/guard implementation or implementation contract. No Page or Space was
edited. These account-scoped results do not prove absence in another owner's
account, project or machine.

The older team archive's identity is consistent across Library search, read and
the prepared transfer:

- Library ID: `<PRIVATE_LIBRARY_ITEM_ID>`.
- Underlying file ID: `<PRIVATE_FILE_ID>`.
- Name: `LapSim-Team-Lab-20261020.zip`.
- Declared size: 20,004,816 bytes; no local byte count or SHA-256 was established.

The earlier download exited 1 with a generic download failure; no local file
was found by targeted workspace inventory. The transfer has no `workspace_path`.
Its download host is absent from this managed environment's effective allowed
host list, but no detailed failure diagnostic establishes that as the cause.
No unchanged download was retried, no signed-URL workaround was used and no
network/access setting was changed. Library read exposes no archive text.
The archive's members/content remain **uninspected**. This is not a confirmed
automatic-review denial and does not clear any earlier execution restriction.

The repository/prior-owner evidence and missing artifact/API inventory remain
in [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md). No original missing source,
authentic producer bundle, genuine source/runtime observer, exact environment
lock or real owned guard/receipt/cleanup provider was recovered.

## Independent source findings

The reviewer disproved an initial type-check concern: explicit reconstruction
in `decode_state` invokes core dataclass constructors. Those constructors
already reject fractional, boolean and negative clocks/work counters. No
redundant repair of the byte-preserved kernels is justified.

Two distinct transition gaps were identified in the new numerical consumer:

1. **P2: reusing historical integration work.** Acceptance checks absolute
   `tick <= integration_substeps <= integration_trials`, nondecreasing totals
   and the chunk work ceiling, but not NEW counter deltas. A source-consistent
   advanced parent with tick/substeps/trials `10/40/100` and an output
   `20/40/100` satisfies those old arithmetic checks while claiming ten new
   committed ticks with zero new integration work. This is a source-level
   counterexample, not an executed fixture or demonstrated passing full test.
2. **P2: intervention jumps without clock events.** A chunk from global tick
   11 to 12 has no allocator update, but old acceptance permits a slip
   intervention counter to rise if it stays under the cumulative allocator
   total. Matching saved endpoint telemetry does not resolve that contradiction.
   Per-tick electrical/generating/brake-redistribution counters have the same
   missing delta relationship to newly committed ticks.

Source basis: `powered_planar.advance_powered` increments trials before each
attempted RK trial and accepted substeps after acceptance; every successful
positive-duration tick completes at least one accepted substep. `plant_tick`
restores those new counters to the old cumulative totals. The numerical loop
increments each policy counter at most once per allocator boundary and each
per-tick counter at most once per committed interval. A rejected prospective
interval retains old accepted state/memory; its provisional work is not added
to committed counters. These are existing source invariants, not new physics.

## Frozen repair contract, before implementation

- Preserve the scientific kernels and original candidates byte for byte.
- Introduce shared metadata-only transition checks: nonnegative integer counter
  deltas, `delta_substeps >= committed_tick_delta`,
  `delta_trials >= delta_substeps`, and the existing finite new-work ceiling.
  A zero-tick rejected chunk cannot change committed integration counters.
- Bind driver/allocator/blend totals to global boundary counts. Bound each
  allocator intervention delta by new allocator updates and each per-tick
  diagnostic delta by new committed ticks; never reset phases at chunk edges.
- Apply the same checks to numerical chunk acceptance, metadata result binding
  after genuine cleanup, and original-request inventory staging for exact replay.
  The raw journal remains a consistency store; it gains no scientific authority.
- Require saved telemetry work to grow by at least its committed tick spacing,
  and saved intervention changes to fit the corresponding global row interval.
  Preserve complete endpoint recomputation and original raw failures.
- No new physical clipping, thresholds, integration formula, fallback, provider,
  permission or resource allocation. No candidate execution/import/syntax check,
  test, simulation, inference, build, installation, push or public publication.

## Repairs and follow-up review

`stepping.require_committed_work_transition` and
`require_clocked_counter_transition` now implement the frozen metadata checks.
`NumericalBridge.accept_chunk`, guarded post-cleanup result binding and exact
replay original-request staging share them. Saved telemetry additionally binds
work changes to row tick spacing and counter changes to row clock intervals.
The scientific integrator, thermal/DRS/force models, allocator formulas, raw
journal/export schemas and earlier source candidates were not changed.

Independent follow-up source review found both P2 findings addressed and no
concrete regression. It confirmed global phases, zero-tick rejected rollback,
initial rows/sampling gaps/invalid output handling, shared call-site consistency
and no numerical import cycle in the metadata paths. The reviewer found no
source case where a valid emitted chunk would violate the added checks. This
is not executed regression evidence or a claim of numerical/runtime acceptance.

No new helper or candidate parser/constructor/bridge/provider/Tk function was
called. No candidate import, syntax check, test, simulation, inference, build or
installation ran. Administrative repository/Library reads and read-only native
presentation text inspection did not run simulator/application candidate code.
Original trust/source/environment/guard dependencies remain unresolved; all
execution providers remain absent and the boundary stays closed.
