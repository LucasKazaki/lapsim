# Canonical reference frame repair — dev23

The fixed worker now consumes the complete frame saved in its exact pinned
reference artifact. Local floating reconstruction previously supplied that exact
identity, so last-bit numerical differences could reject unchanged source inputs.
Dev22 source geometry itself already comes from a fixed JSON artifact; the public
stadium regeneration finding does not directly change that geometry.

`course.construct_fsi_course_from_reference(bundle_raw, cones_raw,
line_artifact_raw, *, expected_line_artifact_sha256)` checks immutable bounded
raw bytes and the inherited request hash, strict JSON, all saved frame fields,
source/encoding bindings and the complete frame digest. It retains every saved
frame value, including producer diagnostic claims. The legacy
`construct_fsi_course` still runs unchanged for its local geometric screens.
Those local diagnostics are not used to rewrite the saved frame or its identity.
No frame-matching tolerance was introduced.

The returned frozen `SourceCourse` also retains
`canonical_frame_artifact_sha256`. `raw_reference_inputs` binds its complete raw
artifact to that pin before parsing and still requires exact canonical frame and
source equality. Legacy source-only construction retains a `None` artifact pin;
the fixed worker explicitly uses the new required-artifact constructor, with no
fallback. The worker/bootstrap arguments are unchanged.

This constructor checks consistency. It does not establish that the frame was
produced from the YAML by the original producer. That relationship, original
producer/source/tool/cleanup evidence, authentication and current admission stay
with the original native provider. Hashes supplied by an untrusted caller do not
create authority. Existing exact source/environment, field, checkpoint,
continuation and replay boundaries remain; old checkpoints must not be relabeled
with a new source manifest.

## Verification

Command from this project directory:

```text
PYTHONPATH=src timeout 60s python3 -B -m unittest discover -s tests -v
```

On Linux / Python 3.12.14: **39 tests passed, zero failures/errors, 3.282 seconds**.
These comprise 16 new canonical-frame tests, nine fixed-factory preflight/wiring
tests and 14 existing metadata/storage tests. The new tests execute actual public
source-course arithmetic and raw-reference consistency checks using an explicitly
synthetic local artifact. They cover controlled cosine sensitivity, exact raw
artifact/frame/source/encoding binding, malformed and nonfinite JSON, canonical
size expansion, local screen failure, retained producer diagnostics and rehashed
cross-environment rejection. The cosine perturbation is a sensitivity experiment,
not a model of an actual platform library.

The initial capability regression errored before implementation because the new
constructor did not exist. The first combined run found a stale mocked constructor
target, corrected before the passing runs. Independent read-only reviewers found
and closed two issues: canonical-size expansion bounds, and missing cross-API raw
artifact binding in the first implementation. Reviewers did not rerun tests.

No worker, policy step, lap, native observer, admission or cleanup was executed.
Metadata/storage tests use deliberately untrusted providers and temporary files.
Original-artifact compatibility and actual Windows/Linux dev23 identity remain
unverified here. The native owner reports a local 361,833-byte original
`line-artifact.json` matching SHA256
`1779ff9b9254f16e09a49f24d45603f3e7de88edb7650055e6aa5159e4e6a00b`;
these raw bytes have not been provided to this cloud checkout.

## Preserved source and next integration gate

This is a separate dev23 candidate based on checkout
`79d6a9b4ee7badbf3a1497327038347ee5387cb7`. Frozen dev22 remains commit
`d573d456ab2ca408cf2891db52e69b2f17ab4e05`, manifest SHA256
`9f516656fe7fc6dec3723bd5d7ca206edf13cd865f076776b1b5c08d513ab5ee`,
and ZIP SHA256
`eae6d18431ea4aed1d994207c7269148a6bdf48887f3d41e5e928ec208e90605`.
No saved dev22 artifact was modified, transferred or republished.

Before native integration, review and pin the new source manifest, verify the
constructor with the original complete artifact and corresponding raw source
encoding, and establish the genuine current admission/environment/guard/cleanup
chain. A shared canonical frame does not establish numerical equivalence across
environments or authorize merging historical results. No one-command or
production-runtime acceptance is claimed by this repair.
