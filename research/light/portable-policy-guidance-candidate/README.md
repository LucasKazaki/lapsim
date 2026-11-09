# Portable light policy, guidance and raw-storage source candidate

**UNTESTED / UNBUILT / UNQUALIFIED.** These are complete source files in an
isolated candidate directory. There is no tournament runner, executable provider
registration or launch command. The existing archival files and active simulator
package are unchanged.

Source baseline: `main` at `07ccb4b84138aedcc5b9cb85c2e81d283d6c132e`.
Portable-core origin: PR #166 at
`eda45185a4debeae7239dce906b72cfdf3909da9`, copied without scientific changes.
That PR remains a separately reviewed source candidate, not runtime evidence.
See `SOURCE_MANIFEST.json` for exact source and output file identities, and
`CORE_NOTICE.md` for the retained core provenance notice.

The source distribution metadata includes all four local namespaces with no
declared external runtime dependency or console entry point. It has not been
built or imported. `setuptools>=68` is a provisional build declaration, not an
exact environment lock. This candidate includes the `lapsim_light_core`
namespace itself; a future environment must select this complete distribution
rather than combine it with a separately installed copy of PR #166's package.

## Frozen behavior contract

- Importing the package initializers performs no I/O or eager imports. No
  candidate module, test, syntax check, build or simulator job was executed here.
- The seven exact policy IDs and four independent synthetic AWD channels remain
  explicit; regen stays OFF. Registry entries remain unqualified and ineligible.
- Allocation, actuator-limit antiwindup, common friction authority and plant
  battery accounting retain their original source formulas. No physical state,
  energy or SOC correction is added.
- Driver settings, projection, preview, pursuit and edge-response formulas are
  extracted from the pinned main source. The standing-settings helper comes
  from the archived AWD fixture. New package types/source identities cannot be
  substituted into historical checkpoints or qualification certificates.
- `common_awd_driver_command` calls the original scalar-demand driver and then
  `normalize_driver_command` exactly once. Its output is the equal four-wheel
  request before policy allocation. Never apply `_controller`'s raw two-channel
  scalar-demand proxies to the plant. Driver, allocator, plant and logging clocks
  remain the eventual guarded owner's separate responsibilities.
- `ReferenceTrack` is a structural annotation. Neither it nor the copied
  polyline helper constructs or admits a course/racing line. Complete geometry,
  boundary-uncertainty and externally authenticated line checks are still needed.
- Raw storage checks consistency, never execution authority. Immutable chunk and
  checkpoint objects precede a receipt written last. A committed storage tail is
  separate from torn/orphan recovery candidates and is not an admitted resume
  checkpoint. Unknown or inconsistent storage blocks further append until the
  original owner reconciles it. No automatic recovery, retry or resume is added.
  In this candidate, `paused_budget` closes the journal just like the other
  terminal records: it records cessation, not an implemented continuation API.
  A future explicit continuation contract must bind the predecessor manifest,
  terminal receipt, checkpoint, external admission and fresh resource authority.
- File flush/fsync is requested by default; POSIX directory fsync is requested
  where supported. Standard-library Windows directory flushing and power-loss
  durability are not claimed. The original single guarded writer/resource lease
  remains necessary; this source introduces no replacement lock or supervisor.

## Launcher integration boundary

The intended source path is admitted common track/state -> common guidance ->
one AWD normalization -> selected allocator -> constrained portable plant.
The guarded owner must retain the requested/proposed/limited/achieved values,
full dynamic/controller state, raw failures and exact source/config/input IDs.
It must validate raw bridge results and actual owned execution/cleanup receipts
before promoting any result or committed tail to admitted progress.

The raw journal currently speaks the archived bridge's checkpoint/chunk schema.
A newly ported bridge must preserve or explicitly version that schema and undergo
separate review. A storage digest establishes consistency, not trust. Declared
environment hashes must come from the reviewed owner; local JSON is not proof
of a measured numerical environment or an authenticated producer.

The original activity/session/game/memory checks, exclusive lease, finite fresh
allocation, hard cutoff, watchdog and owned cleanup are still required. No safety
or resource guard is removed, replaced or disabled. A launcher must continue to
fail closed while its genuine admitted backend is unavailable.

The physical fixture, portable course/resource construction, authenticated line
binding, numerical/dependency environment lock, complete stepping bridge,
guarded dispatch, result verification, replay/export and actual app behavior
remain integration work. Development comparisons must freeze identical inputs
and preserve held-out separation. No accuracy, lap, point, winner, overnight
readiness or completion-time claim follows from these source files or reviews.

No executable tests were added or run under the owner's current no-testing instruction.
The behavior contract and source comparisons are static review evidence only.
