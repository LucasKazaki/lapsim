# Cooperative FSG replay-worker cancellation, portable dev35

`FsgReplayWorker.request_cancel()` now provides a bounded worker's cooperative
cancellation path. It is not native OS Stop, process containment or admission.
The missing original predicate is neither reconstructed nor replaced. The new
main-PC source assessment is recorded as reported source verification, not as
authentication of an executing code/import/runtime closure.

## Lifecycle ordering and owned consumer

A separate short lifecycle lock and persistent Event coordinate cancellation
without acquiring the execution lock held throughout numerical work. Before
terminal sealing, `request_cancel()` sets the worker Event, forwards the request
to the active internally owned consumer, and returns `True`. Consumer publication
forwards any request accepted during construction, so it cannot be lost. The
worker checks cancellation again immediately before initialization and around
each replay/extension call.

Returned literal interval/endpoints and attempted work are retained before
cancellation is classified. A partial cancelled prefix never becomes replay
divergence, never advances the extension, and produces no eligible child. The
current in-flight tick may commit before its next cooperative boundary observes
the Event; its raw output and work remain evidence, not a refund or a completed
requested interval. No extra numerical call is made to manufacture a cancellation
row or rewrite an already captured endpoint.

Successful result sealing and cancellation acceptance use the same lifecycle
lock. Accepted cancellation before sealing prevents or quarantines any candidate
child. Once the result is sealed, the consumer is detached and the worker marked
finished before the lock is released. A later `request_cancel()` returns `False`
and leaves the result/snapshot unchanged. This gives a definite ordering to the
publication race instead of relying on two unlocked Event checks.

The enclosing deadline is rechecked before and after publication inside that
short critical section. A delayed publication cannot seal a late success. The
one-shot execution claim and refusal of retries remain intact, and all exit paths
detach the consumer. The worker never returns a live numerical consumer.

## Failure precedence and retained evidence

Genuine exceptions retain priority over simultaneous cancellation. The original
exception, raw output and known/unknown work accounting survive; pending
cancellation is recorded separately. A returned numerical `invalid` interval
now raises `FsgReplayRejected` after retaining its exact record and charging work,
before cancellation is classified. Thus a caught numerical/predicate rejection
cannot be relabeled as clean cancellation. Non-invalid raw terminal outcomes
remain data-only and cannot produce an eligible replay checkpoint.

Review found two concrete gaps and their reproducing tests are preserved:
cancellation accepted during identity/origin validation previously still entered
the initializer, and a returned invalid interval could be mislabeled as cancelled.
The fixes add the immediate pre-constructor check and explicit numerical rejection
precedence. Earlier red tests also retain the formerly missing cancellation API
and publication-deadline fence. Synthetic race/exception tests are not native
cancellation or authenticated original-predicate evidence.

## Main-PC source findings and remaining observation

The parent reports that a read-only main-PC assessment matched original demo SHA
`b7ee2a2c822c646203af4b471d8c851685c575fa2477a982d4f0519fc409b171`
and recovered adapter SHA
`570438d155f28edd1eefdcc165cfd4b9ca4e516d5cd18a942dc12d7a5e1a987c`,
with its seven-file source manifest matching. No new manifest SHA/file list or
private source bytes were supplied here. The adapter implementation pin is distinct
from the demo provenance pin. Reported source presence does not identify the code
actually loaded into an executing worker or grant current admission.

The earlier exact reported predicate applies the speed-at-or-below-2 condition
to both negative actual pack power and any negative actual wheel torque. The
latest prose summary is not a new precedence/units contract. No formula, absolute
speed conversion, tolerance, requested-regeneration exemption or changed threshold
was implemented; separate development OFF-domain checks remain unchanged.

Authenticated native observation must still establish:

- Actual loaded adapter/function/code/global/import identities against the
  reviewed implementation and source closure, using supported original evidence.
- Complete current numerical source/environment facts, including applicable
  interpreter/ABI/stdlib/distribution/native-module and numerical-state bindings.
  Selected helper hashes or a seven-file source manifest do not prove that closure.
- Genuine input/line/history admission and fresh ownership/activity/resource
  lease, challenge and finite enclosing deadline under the original owner.
- Actual terminal/output-retention and cleanup evidence, including the original
  watchdog/observer/reader/owned-process closure requirements.

No private source transfer, unknown module import, native probe, lease or job was
performed. The original predicate remains a required external input. The tests
continue to use explicitly UNTRUSTED interface doubles; no fresh runtime
observation or authentication is synthesized from hashes or flags.

## Validation and limits

Eleven focused cases exercise pending cancellation before initialization,
cancellation during identity validation and construction, real short in-flight
replay/extension, candidate-child quarantine, a two-thread publication race,
post-return immutability, genuine thrown and returned failures, and deadline
crossing during publication. All test threads are joined with finite bounds.
The complete source/installed suite and artifact identities are recorded against
the final commit, with race/control fixtures separate from numerical evidence.

The development replay profile remains 16 segments, 1000 ticks and 4 MiB. It does
not implement full-event continuation, native worker/Start/Stop registration,
process interruption, authenticated admission or cleanup. A blocked constructor,
predicate or plant call still needs the original OS deadline/watchdog/containment
mechanism. Windows, actual-car/full-course qualification and held-out results
remain outside these checks. Earlier frozen releases and evidence remain intact;
the unchanged delivery failure was not retried.
