# FSG predicate and continuation boundary validation

This separate test tranche targets frozen portable dev33 at source commit
`907f094047120bbe75c5906f4c9ff16d15fa43db`. It changes neither the runtime
package nor its source manifest, fixtures, release ZIP or native safeguards.

The original residual adapter remains unavailable here. Exact filename checks
and metadata inspection of 25 existing local EV archives found neither the
reported adapter nor the original demo source. Owner-reported r02 adapter pin
`570438d155f28edd1eefdcc165cfd4b9ca4e516d5cd18a942dc12d7a5e1a987c`
is distinct from the demo's provenance pin. No reported formula was recreated,
no double was promoted and no hash/claimed authentication flag grants authority.
The adapter's actual source/import closure and genuine loaded-source/runtime/
admission evidence remain necessary. Exact targets and source-supported
continuation requirements are in [SOURCE_REQUIREMENTS.json](SOURCE_REQUIREMENTS.json).

The tests exercise actual development behavior with explicitly untrusted
predicate interface doubles: strict Boolean refusal, pin drift, failed
post-step retention, exact 65 ms in-memory carry across the 50 ms driver boundary,
no global-work refund, and terminal cancellation. Real driver/allocator/plant
functions run only in short bounded probes. No full lap, original predicate,
process restoration, native admission or cleanup is tested.

Legacy worker-family/type and checkpoint-schema rejection tests establish that
the current FSI chain cannot consume FSG objects/raw snapshots by wrapping or
hashing them. An exact frozen no-auth FSI metadata fixture is used only for that
negative worker boundary. Its synthetic request is not admission evidence.

A separate test records why future continuation needs literal immutable endpoint
bytes: cancellation changes snapshot metadata after an interval returns, even
when the accepted physical state is unchanged. Current raw intervals/snapshots
supply no restore API, segment/parent chain, finalized paused-budget journal or
admitted continuation. Unknown attempted work must not be refunded; terminal,
quarantined, rejected or cancelled outcomes cannot be relabeled as pauses.

Validation uses the already isolated, offline-installed dev33 wheel. From the
producer's existing checkout, the bounded command is:

```sh
env PYTHONDONTWRITEBYTECODE=1 timeout 45s \
  /workspace/scratch/light-fsg-event-dev33-install-20261108/bin/python -I -B \
  /workspace/scratch/run_fsg_boundary_tests_20261108.py \
  --tests /workspace/lapsim-tournament-integration/research/light/fsg-boundary-validation-20261108/tests \
  --output /workspace/scratch/a-new-boundary-evidence-directory
```

The tests explicitly verify the installed version, module bytes and frozen
manifest before running. Those are selected identity checks; whole-wheel byte
verification is separate earlier dev33 evidence, not fresh loaded-runtime
authentication. This is a producer-local validation command, not a
native setup or tournament command. Evidence is recorded outside the source tree
and bound to the final test revision. All 14 cases passed in 9.007 seconds on
Linux CPython 3.12.14, with zero failures, errors or skips. The previous 204-case
dev33 acceptance remains separate; it was not rerun for this test-only tranche.
No install, original-source import,
resource/lease probe, native job, held-out result, upload retry or publication
occurs in this tranche. The previously failed Library preparation remains blocked.
