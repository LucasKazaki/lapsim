# Source/environment identity closure — source review

Base: `95022fd4dc0dbab28680d95e09247f7d25405914`.
Bounded E07 source tranche. **UNTESTED / UNBUILT / UNQUALIFIED.**

## Independent P1 finding

The v1 environment/source contracts form a cryptographic bootstrap cycle:

```
E = H(entire environment recipe, including source_sha256 = S)
S = H(source observer body, including numerical_environment_sha256 = E)
```

`validate_environment_recipe` requires the expected source hash inside its
recipe and returns the digest of that complete recipe. Dispatch staging requires
that digest to equal the identity's environment hash. `NumericalBridge.source_identity`
requires the source hash to cover a body containing that environment hash.
`raw_journal._bind_checkpoint` independently checks the source-body hash too.
An unrelated placeholder source hash cannot satisfy those contracts. Ordinary
construction would require a cryptographic fixed point; this is a source-level
blocking defect, independently confirmed without executing candidate code.

## Frozen repair contract, before implementation

- Explicitly introduce environment-envelope schema v2 and a separately
  versioned numerical-content schema. Reject v1 rather than reinterpret its
  hash scope or migrate historical environment/checkpoint qualification.
- The numerical-content payload contains the exact interpreter/ABI/executable/
  standard-library identities, platform, binary64 contract, artifact inventory,
  dependency versions/file hashes and verifier identity. Preserve all existing
  validation rules. Its digest `E` is independent of the generated source hash.
- Retain the unchanged source-observer body and hash: `S` still covers static
  reviewed source-manifest identity, `E` and external observer/predicate bindings.
- The v2 envelope contains schema, `source_sha256=S` and the numerical-content
  payload. Validate its source binding against the independently supplied `S`.
  Match the COMPLETE canonical recipe and observation envelopes, including `S`.
  Make API/hash-scope names explicit: `E` hashes numerical content, not that
  source-bound envelope. Do not weaken the source-binding equality checks.
- Admission continues to authenticate the complete subject containing both
  `source_sha256=S` and `environment_lock_sha256=E`, plus the existing fixture,
  course, cones and line identities. A content digest or matching declaration
  alone still proves no measured runtime, trust, permission or resource lease.
- Provide source-independent numerical-content validation so an owner can
  compute the identities in acyclic order from actual independently reviewed
  artifacts. No fake recipe, observer, verifier, measurement or dependency is
  created. Generated source bindings/observations/certificates belong outside
  the static numeric-content identity; do not put a hash-dependent envelope
  back into its own artifact/manifest closure.
- Preserve source-observer hashing, original raw-journal/checkpoint/chunk schemas,
  scientific code and earlier artifacts. No candidate execution/import/syntax
  check/test/simulation/inference/build/installation, push or public publication.

The constructible data order is static artifacts/source manifest -> numerical
content `E` -> observed source body/hash `S` -> source-bound recipe/observation
envelopes -> separately authenticated input statements. This is a dependency
contract, not a command sequence or evidence that those actual artifacts exist.

Original predicate, actual producer/observer/guard/receipt/cleanup implementations
and authenticated environment measurements remain unavailable as documented in
[INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md). No restriction is cleared.

## Implementation and independent follow-up

`validate_numerical_environment` retains every existing interpreter, platform,
binary64, artifact, dependency and verifier rule but hashes only the new exact
numerical-content payload. Its explicit source-independent schema gives that
digest a distinct domain. Content is capped at 1 MiB minus 1024 bytes to reserve
room for the source-bound envelope, whose full bound remains 1 MiB.

`validate_environment_recipe` now accepts only v2's exact three-field envelope
and separately checks the externally expected source binding. It returns the
numerical-content digest, not an envelope hash. `require_environment_match` uses
the explicit `expected_numerical_environment_sha256` keyword, validates recipe
and observation source bindings, and compares their COMPLETE canonical envelopes.
Its declaration-only result identifies the hash scope and separately checked
source binding while retaining false authority/probe flags. Dispatch's call site
uses the new keyword and leaves its signed subject's source and environment
identities unchanged. No source-observer or raw-journal hash rule was weakened.

Independent follow-up source review confirmed that the required cycle is removed
and found no concrete regression, missing old numeric validation or stale call
site. It verified complete envelope/source binding and v1 refusal, the signed
S/E subject, and unchanged observer/journal/scientific source. This establishes
source-level constructibility only; no actual identity or measurement was
constructed or verified by execution.

No candidate validator, parser, signer, observer, constructor, step, replay or
provider callback was invoked. No candidate import, syntax check, test,
simulation, inference, build or installation ran. Exact environment artifacts,
measurements and genuine trust/guard/cleanup integrations remain unavailable.

## Cross-module source/environment binding audit — 6 November 2026

Frozen before repair, base `7c23c1047a5806cdde78e58712a647dff95a5321`.
Concrete P2 metadata inconsistency: keep a valid current checkpoint/source whose
source digest commits numerical environment A, then change only its declared
identity's `environment_sha256` to a distinct valid B. `_bind_checkpoint` checks
the source digest but omits A == B, so raw journal creation/export replay and
chunk planning/staged-request/continuation consistency checks can accept that
contradiction. `tournament_plan._origin_parts` and `NumericalBridge.source_identity`
already reject it later. This is not an admitted execution or authentication
bypass, and no counterexample has been executed.

Repair only the shared raw checkpoint binder. If a source declares a numerical
environment hash, require an exact SHA256 equal to the supplied identity's E.
Require the field whenever context or source claims the current portable
numerical family. Preserve legacy storage-only contexts when neither family
claims that portable profile and their original source format has no E field.
Legacy storage consistency never grants current execution/admission authority.
Keep schemas, bytes/hash rules, policy algorithms, original guards and all earlier
frozen source packages unchanged; matching declarations still do not measure or
authenticate the runtime.

Inert regression specifications, all unrun:

- C01: current portable checkpoint S(E=A), identity E=B must fail at the shared
  binder before a journal/plan/request/continuation can report consistent metadata.
- C02: a current portable context or source with missing, non-SHA or mismatching
  E must fail; a different identity field cannot mask that missing binding.
- C03: matching current S/E declarations retain their existing raw paths; no
  permission, observed environment, qualification or real provider is inferred.
- C04: legacy source without E remains storage-readable only when neither family
  claims the current portable profile. A legacy source that explicitly declares
  E must bind it to identity E too; removing an explicit contradiction is not an
  automatic format upgrade or runtime admission.
- C05: seven-policy selection, callback-free request/worker bounds, linked-parent
  result adoption, failed/missing exclusions and opaque archive retention remain
  unchanged. Old immutable artifacts remain original bytes, without silent rewrite.

The patch will be reviewed independently as source only. No candidate imports,
syntax checks, tests, simulations, archive execution, probes, uploads or transfers
are authorised or performed by this audit.

Both independent reviewers confirmed the P2 gap and inspected the shared binder
repair. Any explicitly declared E now must be an exact SHA256 equal to identity
E; either current context/source family requires it. They checked the archived
`awd-standing-v15/light_core_bridge.py` legacy family
`lapsim.torque-light-awd-racingline-standing-development.v1`, whose old source
format lacks E, and confirmed that storage-only compatibility is preserved.
No additional concrete defect was found in the bounded audit of seven-policy
selection, fixed driver/allocator/blend clocks, raw rejected intervals, worker
linking, returned-result accounting/adoption, archive reconstruction, continuation
and failed/missing/completion exclusions. These are source-inspection findings,
not executed counterexamples or proof of numerical, runtime or cleanup behavior.

The repair changes no data schema, policy/model, clock, budget or provider call
order. New source pins and fresh real external review/admission are still needed
for future execution. The dev19 ZIP at commit `7c23c1047a58` remains frozen,
unchanged and unqualified; this later source repair is an incremental revision
and is not inserted into that ZIP or its pending upload request.
