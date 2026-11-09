# Fixed chunk-worker program — source only

Base: `3b285f0e79085c59df80b42059ab522ea1763368`. Bounded E05 source unit.
Frozen behavior contract written before implementation. No candidate execution,
imports, syntax checks, builds, tests, simulation or runtime qualification.

Implement the actual request-to-numerical-output program missing from the old
load map: select only the existing numerical family and callback-free v2 entry;
validate immutable request/parent bytes; bind the full bridge identity; resume
the exact parent; advance once with the original requested ticks and no progress
callback; validate/link through the real numerical bridge; enforce the original
request's tighter tick/work/counter bounds; verify unchanged observed source.
Return immutable RAW chunk/checkpoint bytes, never an owned receipt or admission.

The object consumes its local attempt before observations/work. It never resets
or retries. A local lock serializes that claim only: it is not the original
resource/writer lease or a fresh challenge service. After return or exception,
an immutable snapshot retains bytes already produced before later failures.
This is memory evidence, not durable storage or process-death/OOM recovery.
Exceptions received from the bridge/observer/binder propagate unchanged; the
bridge's own historical exception handling is not replaced or requalified.
Existing RawOutputQuarantined remains failed evidence on its original path.

The genuine native provider must authenticate inputs, consume the real fresh
challenge and own original guards, allocation, deadline/watchdog, output/writer
exclusion, durable partial/failure retention and cleanup. Numerical consistency
validation occurs inside that allocation; original execution/cleanup admission
is still mandatory before adopting an authorised next parent or campaign result.
No provider, process bootstrap, OS worker executable, launcher or seven-policy
runner is supplied by this single-chunk program. No original receipts are made.
The frozen 93-file Library ZIP and its load map remain unchanged.

## Inert regression specifications — not executed

| ID | Future check under separately authorised testing | Required result |
| --- | --- | --- |
| W01 | Unknown family, altered v2 function/callback, wrong request pin or noncanonical input | Refuse before numerical work; no fallback registry/provider. |
| W02 | A different bridge identity or nonexact bridge type | Refuse before resume/advance. |
| W03 | Resume at tick 53 and request 50 ticks | Pass requested ticks 50; retain global phases: driver +1, allocator +5, blend +50 if all intervals commit. |
| W04 | Request extends three ticks beyond the remaining mission horizon | Pass the original requested count, retaining normal horizon/finish semantics; never replace it with committed tick count. |
| W05 | Real bridge returns zero-tick invalid output | Preserve its invalid raw chunk and linked accepted-state checkpoint; never retry or mark a completed lap. |
| W06 | Acceptance fails after advance returned | Snapshot retains the exact chunk bytes, no successful result; preserve received exception type/identity. |
| W07 | Request-specific tick/work binding or final source observation fails after linking | Retain both produced byte envelopes as failed RAW evidence; no result/admission. |
| W08 | Bridge raises RawOutputQuarantined | Propagate the same exception/evidence_raw; never promote its nested artifact. |
| W09 | Unknown owner-control exception, MemoryError or BaseException is received inside the claimed worker call | Propagate unchanged; seal that local attempt in finally. No claim that bridge-internal handling preserves every original exception, or that repeated asynchronous interruption/process death is recoverable. |
| W10 | Second or concurrent execution on one object, after any outcome | Refuse further work; this local exclusion does not authenticate campaign attempt uniqueness. |
| W11 | Compare returned bytes with advance output and checkpoint(accept result) | Exact canonical envelopes; unlinked embedded output remains unchanged, linked parent equals chunk body digest. |
| W12 | Use metadata binding inside worker and after guard receipt authentication | Same original tighter request checks; external execution/cleanup authentication still precedes post-cleanup binding. |
| W13 | Snapshot races with the initial attempt claim | Capture readiness and fields under the same local lock; either capture the constructed state or refuse until the claimed call finishes. |
| W14 | An exception interrupts entry after the invocation claims the object | The enclosing finishing scope seals only that invocation; rejected re-entry cannot seal another active call. |

These definitions are future checks, not fabricated numerical results or tool
receipts. Actual behaviour, numerical parity, concurrency, failure retention,
native bootstrap and provider integration remain untested.

## Independent source findings and repairs

Two read-only reviewers inspected the actual worker and shared result-binding
source. One found no numerical/admission defect; the second identified two local
lifecycle issues: snapshot readiness/capture could race the claim, and the old
finishing scope began too late after the claim. The snapshot now holds the same
lock across check/capture; the outer finishing scope covers claim and work with
an invocation-local flag set before the instance flag. Both findings were closed
by independent follow-up inspection. A further local review replaced explicit
lock acquisition/release with the standard lock context manager, avoiding a gap
between acquisition and entry into a release scope. The lock guards only brief
bookkeeping, and no numerical callback runs under it.

The original numerical acceptance docstring was also clarified to distinguish
input/operation admission before in-allocation validation from later original
execution/cleanup receipt admission. Its implementation is unchanged. RAW result
binding is shared with existing guarded dispatch; actual provider authentication
still precedes its post-cleanup metadata call. No original provider, signature,
receipt, allocation, cleanup or campaign authority is manufactured by this unit.

These are inspection findings, not bug-free, runtime, physics or native-integration
claims. The fixed program/resolver is real source; the production OS worker and
registered original provider, authenticated campaign runner and durable native
writer remain missing. The existing frozen package and launcher are untouched.
