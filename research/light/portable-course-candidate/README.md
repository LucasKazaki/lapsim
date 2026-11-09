# Portable FSI source-course construction candidate

Status: **source only, unimported and untested**. Bounded E05 source work based
on main `07ccb4b84138aedcc5b9cb85c2e81d283d6c132e`. This is a separate module;
it does not change the active simulator, original archive, policy/guidance
candidate, line admission, runner or execution controls.

## Frozen implementation contract (5 November 2026)

- Accept caller-supplied `bytes` for exactly the retained processed FSI bundle
  and FSI cone YAML. Accept only the explicitly pinned LF main and CRLF PR #166
  encodings. Check byte counts and complete SHA-256 before decoding. Caller
  digests, mutable manifests, private paths and generic course substitution
  cannot widen the accepted inputs.
- Preserve the source station, x/y and per-cell curvature values, closed seam,
  direction, frame, provenance and assumed-width labels. Never resample, smooth,
  reverse, scale, force-close or substitute a path during loading.
- Reconstruct the archived 96-centre/tangent-fillet source frame against every
  source-grid sample, using the retained cone parser and frame algorithm.
  Return immutable source geometry and transformed simulator cone polylines.
  Preserve the original numerical screen tolerances and uncertainty labels.
- The interface is `lapsim_light_course.course.construct_fsi_course(bundle_raw,
  cones_raw) -> SourceCourse`. Inputs are bytes already obtained by the owner;
  this module performs no filesystem/network/resource discovery. The output's
  `source_track` supplies immutable `distance_m`, `x_m`, `y_m`,
  `curvature_per_m`, `closed`, `cell_count`, `length_m`, `cell_length_m` and
  `cell_center_distance_m`. `source_track.geometry_dict()`, `metadata_dict()`
  and `frame_dict()` return fresh JSON-compatible projections. Types are
  distinct from `lapsim.*` and from any
  unpublished owner module; adaptation requires separate explicit review.
- The result is always `SOURCE_INPUT_ONLY_UNQUALIFIED`. It does not supply an
  admitted driving reference, surveyed corridor, optimized line, trusted
  receipt, replay certificate or permission to run. Its source identity must
  be bound by a later reviewed consumer. A digest establishes consistency.
- The initializer is inert. Imports are limited to Python standard-library
  modules and the adjacent geometry module. No package installation, console
  entrypoint, command dispatcher, optimizer or plant dependency is introduced.

The LF inputs already exist under `configs/courses/` on main. PR #166 at
`eda45185a4debeae7239dce906b72cfdf3909da9` retains their CRLF equivalents under
`research/light/portable-course-inputs/`. That PR remains unmerged. These data
are approximate MIT-licensed AMZ simulator inputs, not official event geometry.
Retain the existing upstream license/provenance when distributing them.

The reported policy/guidance commit `9cf2db6646d3cc293756d0612e81ebf9b9beb912`
and patch `lite-policy-guidance-20261105.patch` were absent from this checkout
and from the inspected public branch inventory. No compatibility with that
unseen implementation is claimed. This new directory is the complete write
scope, so its patch can be reviewed without replacing another owner's files.

## Review and remaining acceptance

See [SOURCE_REVIEW.md](SOURCE_REVIEW.md) for source identities, the extraction
boundary, manual review findings and execution limits. No test, import, build,
simulation or application run is authorized by this document. Future actual
acceptance must cover both pinned encodings, exact geometry/frame parity,
input mutation/shape/finite-value rejection, immutable projections, isolated
imports and integration with the independently authenticated reference path.
