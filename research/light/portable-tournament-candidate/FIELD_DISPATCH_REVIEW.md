# Frozen field dispatch coordinator — source only

Base: `afb1a03eaa885dca0fb970c1a8fae849b5c8df49`. Bounded E05 source unit.
This behavior contract precedes implementation. No candidate execution, imports,
syntax checks, builds, tests, observations, leases or simulation are authorised.

Implement a real one-request-at-a-time in-memory seven-policy coordinator. Take
the exact existing canonical frozen plan, a fixed externally reviewed provider
pin, explicit finite requested-wall-time and retained-payload caps. Keep all
seven frozen slots and the unchanged origin bytes. Accept only an externally
prepared existing v2 request pinned to the current slot's full identity and exact
current parent. Preflight known provider availability, request consistency and
remaining caps. Consume local request hash/nonce and proposal accounting before
calling the real `dispatch_owned_chunk`; no fake provider or request issuer.

Retain every `OwnedChunkResult` that actually returns, including its immutable
raw request, raw chunk, linked checkpoint and opaque original receipt bytes.
Continue a running cell only from that exact returned checkpoint, preserving
global clocks and cumulative work. Move to the next frozen origin only after
numerical completion. A terminal numerical failure or a failure received in the
claimed body after dispatch consumption seals this field when finalization
completes; remaining slots stay missing.
No retry, skip, reset, import/restore or terminal-revival operation is provided.

Bound the field to seven times the existing journal record limit. Reserve the
whole maximum request/result transport allowance before dispatch; actual retained
payloads must fit the explicit cap. Separate requested tick/work/wall/RSS maxima
from accepted tick/work counters and unknown failed-call exposure. Proposal caps
are not original finite allocations, measured elapsed time, actual RSS or failed
work. Each cell retains its own mission counters across chunks; field totals
include preceding cells when a new frozen origin is selected. A local
mutex protects only coordinator state; no provider/numerical callback runs while
that lock is held. A local seal is not active Stop or evidence of OS cleanup.

The fixed numerical program is reached through the original provider's existing
numerical family; the native owner must actually wire `chunk_worker` inside its
owned worker. No direct numerical bypass, process bootstrap/registration, native
factory, observer, challenge service, writer, watchdog, receipt or lease is added.
The provider must preserve unreturned/partial/failing output: existing dispatch
can raise after worker output was created but before returning it to this layer.
Snapshots retain the original canonical plan, including all unchanged origins,
as well as current checkpoints and request/result history. The payload cap covers
that history only; the separately bounded plan/current checkpoints and Python
object overhead are not RSS measurements. Snapshots are post-call memory, not
crash durability or campaign eligibility.

No journal receipt, storage terminal, `RawCellExport`, rank or award is synthesized
from in-memory results. The real native writer retains actual output under its
original controls; existing raw export/reduction works only on actual journal
artifacts. A closed paused-budget journal requires the existing explicitly
admitted outer continuation path, which this first coordinator does not invoke.
The genuine provider must reject ordinary requests against closed native history.
This object cannot observe external file closure and cannot restore old history.

## Inert regression specifications — not executed

| ID | Future separately authorised check | Required result |
| --- | --- | --- |
| F01 | Missing/wrong provider pin, malformed request, wrong cell/parent or insufficient cap | Refuse before consuming a dispatch; no worker call or fallback. |
| F02 | Seven actual completed cells in frozen order | Each new cell starts from its own exact frozen origin; all seven slots retained; no awards or storage terminals fabricated. |
| F03 | Running chunk from global tick 53 | Next request binds the exact returned parent, global clocks and cumulative counters; no origin reset. |
| F04 | Duplicate request hash or nonce after a returned chunk | Refuse locally before dispatch; original global challenge authentication is still required. |
| F05 | Maximum-sized original result | Reserve request plus complete bounded result before dispatch; never launch and discard merely because a later payload cap is exceeded. |
| F06 | Provider, receipt verifier or post-cleanup binder raises | Preserve the received exception; mark consumed operation failed/unknown and seal field. Provider retains any output that never returned. |
| F07 | Returned result followed by coordinator validation failure | Retain that returned packet without adopting a new parent; seal field; do not retry. |
| F08 | Returned invalid, time_limit or other non-completed terminal checkpoint | Preserve its exact status and packet; seal field with remaining slots missing. |
| F09 | Requested horizon exceeds remaining mission intervals | Preserve original request counts; accepted deltas come from the returned checkpoint, not the proposed extent. |
| F10 | Snapshot or second dispatch races an active call | Refuse in-progress observation/entry; no mixed state, overlapping provider call or claim of original resource exclusion. |
| F11 | Explicit idle local seal, or a completed seven-slot sequence | No subsequent dispatch/reset; idle seal performs no process action or cleanup verification. |
| F12 | Process death, interruption originating during finalization, repeated asynchronous interruption, OOM, or closed external paused journal | No recovery, durability or automatic continuation claim; original native controls/evidence remain mandatory. |
| F13 | An exception interrupts consumption or adoption bookkeeping inside the claimed body, then finalization completes | Each stored transition carries its request/nonce/reservation or checkpoint/adoption metadata together; no mixed accepted/unresolved snapshot. Preserve any result already received by this layer. |

These are frozen future checks, not executed tests or fabricated results. Source
inspection cannot qualify numerical behavior, concurrency, ownership or cleanup.

## Independent source findings and repairs

Two read-only reviewers inspected the real code. Three distinct bookkeeping
findings were repaired: lost original plan/origin bytes after the first adoption;
a consumed-flag/store gap that could lose request/nonce/reservation accounting;
and separate checkpoint/adoption assignments that could contradict accepted and
unresolved counts. The plan bytes are now retained in snapshots, and one frozen
state reference commits each complete consumption/adoption transition. A locally
received result is retained on the failure path before sealing. Both reviewers
confirmed these repairs by inspection.

A follow-up documentation finding narrowed interruption handling: exceptions
received within the claimed dispatch/body are bare-raised unchanged, and failed
consumed calls are sealed when finalization completes. An interruption first
originating inside finalization is outside that handler and has no recovery or
sealing guarantee. This is a documented limitation, not implemented crash recovery.
The actual native owner must retain original evidence and enforce the original
admission/cleanup boundary independently of this local bookkeeping.

No candidate imports, parsing/syntax checks, builds, tests, model calls, worker
processes, resource probes or leases occurred. The inert checks remain unrun.
