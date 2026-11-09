# Bounded FSG replay checkpoints and raw worker, portable dev34

This adds a distinct development checkpoint/worker profile without restoring
arbitrary saved physics or pretending to authenticate the missing original
residual predicate. It is not a native Start/continuation ABI. The conservative
profile permits at most **16 segments, 1000 total ticks (1 simulated second),
and 4 MiB of encoded checkpoint history**. Those are engineering compute/storage
limits, not full-course capability or new physical assumptions.

## Literal endpoint capture

`FsgDevelopmentConsumer.advance_with_snapshots(...)` returns a frozen
`FsgRawInterval(before_raw, interval_raw, after_raw)`. The existing `advance(...)`
still returns its interval bytes. Both use one lock-owning execution core and
one original cooperative deadline, so endpoints are the literal immutable bytes
whose hashes appear in the interval. A later cancellation snapshot is never
substituted. DTO construction and size checks precede the final deadline fence.
On late consumer serialization, `FsgDevelopmentDeadlineExceeded.raw_record`
retains all available endpoints as quarantined data, alongside `raw_interval`;
no successful record or eligible checkpoint is returned.

## Closed development checkpoint

`fsg_checkpoint.origin_checkpoint(consumer, identity)` captures a clean computed
origin. `extend_checkpoint(...)` appends a literal complete successful call.
`validate_checkpoint(...)` checks the distinct canonical envelope, raw/body hashes,
fixed field inventory, declared identity, bounded history, exact endpoint chain,
call schedule and recursive parent-prefix hash. This is structural consistency,
not numerical proof, native admission or restoration authority.

The identity binds declared source-manifest/environment/residual-rule pins and
the actual metric-course record hash. These declarations are not observations.
The course record binds base, phase, source geometry/frame, parameter table,
retained sampled metric and initial projected offsets. Literal origin context
also contains full fixture, effective driver, policy/model settings and original
initial physical state. Authentication flags remain false.

Every stored segment retains the original requested ticks/work cap and literal
before/interval/after bytes. Only complete `running` prefixes with known attempted
work, no cancellation, violation, rejected attempt, quarantine or finish are
eligible for replay. Terminal or unknown-work results cannot be relabeled as
pauses. Capacity, context and parent linkage are checked before replay; a child
that exceeds output capacity fails with generated raw evidence retained.

## Real bounded replay and extension

`fsg_worker.prepare_request(...)` binds a checkpoint's exact bytes and identity,
an origin-context pin, extension schedule, aggregate actual plant-work cap and
one cooperative wall window (at most 40 seconds). These are raw declarations,
not signatures, fresh challenges, leases or permissions.

`FsgReplayWorker(...).execute(course=..., residual_regen_rule=...)` consumes its
local attempt before initialization/replay. It constructs a fresh real numerical
consumer, compares the computed origin bytes, replays the original ordered call
partition/caps, and compares every actual interval and both endpoints byte for
byte before extending. It never assigns saved state, controller memory, offsets
or event flags. Replay preserves the original initial energy origin and derives
departure/arming by actual execution. The original required predicate interface
and matching input pin remain mandatory; the caller must supply the actual
compatible original implementation with independently verified provenance for
any genuine use. Object attributes do not prove freshness, purity or provenance.

Replay executes real plant work. The worker separately reports inherited/replayed
ticks, newly advanced ticks, replay work, extension work and total work of this
attempt. Prefix replay earns no new progress. Every recorded per-call work cap
must fit the remaining aggregate worker cap before that call starts; actual
returned attempted work is charged before acceptance. Mission caps remain fixed.
The worker deadline begins before its request revalidation and covers numerical
calls, comparison, checkpoint construction and finalization. Course preparation
is a separate bounded operation that a genuine owner must include inside its
original enclosing allocation/deadline; this worker does not grant that authority.

The worker returns a `RawFsgWorkerResult`, never `OwnedChunkResult`, a native
terminal or cleanup receipt. A terminal extension retains raw data and returns no
eligible child checkpoint. A successful clean extension can return a structurally
eligible development replay checkpoint; it still has no native authority.
No live consumer escapes the one-shot worker.

## Failure and accounting repairs

Generated raw records are retained before subsequent checks. Any raised attempt
is sealed; a refused second call leaves the prior result unchanged. A child
published just before an interruption is quarantined and cleared, so a failed
worker never exposes it as its eligible child. Late finalization also quarantines
rather than returns success.

An unreturned numerical call first marks accounting incomplete. Failure capture
is guarded: if consumer snapshot serialization also fails, the original exception
is propagated, the last known work remains explicitly a lower bound, and capture
failure is recorded. Diagnostic formatting is best-effort in both consumer and
worker; a failing exception `__str__` cannot mask the original failure, skip
unknown-work accounting or prevent child quarantine. Two reproducing red cases
are retained separately from the final acceptance evidence.

The frozen dev34 worker has no cancellation-forwarding/production Stop adapter.
Dev35 adds the cooperative path described in FSG_CANCELLATION_REVIEW.md; native
process Stop and original admission/cleanup remain separate requirements. Its finite
wall/work bounds do not replace original OS containment, external cancellation,
watchdogs, output retention or cleanup. Native registration and admitted outer
continuation remain absent. A serialized clean flag never establishes current
permission or cancellation freshness. Quarantined bytes may be audited but not
promoted into a successful worker result or admitted predecessor.

## Validation and remaining boundaries

Eighteen focused cases exercise real short replay/extension with an explicitly
UNTRUSTED predicate double, exact state parity across driver/allocator boundaries,
three/four-segment lineage, literal endpoints after cancellation, state/event/identity/
parent mutations, strict schedule/cap checks, terminal/unknown/quarantine refusal,
aggregate replay charging, missing predicate, no retry, secondary capture failure,
interrupted publication, deadline quarantine and failing error formatting.
Synthetic mutations, clocks and injected exceptions are clearly separate from
real numerical probes. No original predicate, complete runtime observation,
native guard, Windows execution, actual car or full FSG lap is qualified.

The complete source/isolated-install suite and package identities are recorded
externally against the final source commit. Prior dev33 runtime and the separate
14-case boundary-validation artifacts stay frozen. The original predicate bytes,
complete authenticated source/environment/line evidence, native fixed worker/
Start/continuation/Stop composition, durable output qualification and actual-car/
full-trajectory validation remain required. No held-out results, private source
reconstruction, native job, publication or unchanged delivery retry occurred.
