# Portable approximate FSI input archive

**Unvalidated simulator data, not surveyed course limits or an admitted racing
line.** No geometry recomputation, optimizer, driver replay or numerical test
was run for this publication. These files do not grant execution permission.

`FSI.yaml` is public simulator cone data from
[AMZ-Racing/fssim](https://github.com/AMZ-Racing/fssim/blob/cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4/fssim_gazebo/models/track/tracks_yaml/FSI.yaml),
pinned to commit `cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4`.
The complete [MIT notice](LICENSE.md) is retained. Its source and notice were
compared with the immutable upstream Git blobs. The copied local files use
CRLF; replacing CRLF with LF reproduces the upstream bytes. Both identities
are recorded in [PROVENANCE.json](PROVENANCE.json), without silently describing
the raw CRLF copies as byte-identical to upstream.

`amz_fssim_fsi_approx.json` is the existing project approximation. Its source
provenance describes ordered left-boundary samples projected onto nearest
right segments, midpoint approximation and tangent fillets, with source Gazebo
coordinates interpreted as meters. Event year and survey accuracy are unknown.
It explicitly records **absent** boundary data and an **assumed uniform**
3.000 m half-width, not measured physical clearance. Retained cone coordinates
do not certify a continuous corridor or a swept vehicle footprint.

The JSON's source hash is the LF-normalized YAML hash; its own raw-file and
geometry-field hashes are separate. The latter is a preserved declaration,
not a newly recomputed or validated geometry result. The processed bundle
retains its processing/provenance and the upstream MIT notice alongside it.
That notice does not grant a license to unrelated repository files.

The scoped `.gitattributes` retains reviewed bytes on checkout. No global Git
configuration or existing source/evidence is changed. A future loader still
needs explicit package/resource binding, validated units/frame/geometry and
independently authenticated racing-line admission; no local JSON may promote
itself to a qualified line. Existing raw producer receipts and private promotion
bundles are not included. No centerline fallback is claimed as a racing line.
