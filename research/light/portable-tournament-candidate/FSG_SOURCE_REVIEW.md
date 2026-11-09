# FSG source-course preparation, dev27

This source component constructs the exact public FSG arc grid and its local
cone frame. It closes the FSG source-input construction gap; it does not produce
a sampled driving reference, authenticate a line, widen seven-policy execution
or qualify a course. No optimizer, source-arc driving-line fallback, native worker
or original provider is added.

The API is `lapsim_light_course.course.construct_fsg_course(bundle_raw, cones_raw)`.
It returns a frozen `FsgSourceCourse`, distinct from the exact `SourceCourse`
type required by existing numerical/reference consumers. Its contract is
`lapsim.light-fsg-source-course.v1`, status `SOURCE_INPUT_ONLY_UNQUALIFIED` and
local frame schema `ev.fsg-cone-frame.v1`. No canonical reference-artifact pin is
supplied. Package data now include both complete FSI and FSG public inputs.

## Exact inputs and construction

Only these FSG LF bytes are accepted; another encoding requires separate review.

| Input | Bytes | SHA256 |
| --- | ---: | --- |
| `data/amz_fssim_fsg_approx.json` | 76,673 | `c6e4c47a3a4e5aa6efd3c1e4b93d332dc9cd1796f8ae88d02d4a970f6e6525af` |
| `data/FSG.yaml` | 8,710 | `7b3351cd9db27912131b9f5de427861061e2144ed6795498fe980adcd905c30d` |

The saved 724-cell clockwise grid is retained unchanged, including all 725
station/x/y values, 306.45041872992834 m length and geometry SHA256
`0863d0fe882a9e7d756e35b211ee510e829f1dde3384ec85d26d4737e748c0ee`.
No coordinates are regenerated to redefine that identity. The existing source
builder processes FSG and FSI through the same 96-left-sample, nearest-right,
midpoint and tangent-fillet recipe. The private numeric kernel replays that
arithmetic to check full-grid correspondence and map all 94/88 distinct cone
vertices into the local frame. Cone simplicity, winding, left/right crossing,
finite SI values and source identity screens remain mandatory.

Fixed FSI/FSG wrappers own the raw/geometry pins and frame labels. Unknown or
cross-paired inputs fail before reconstruction. Source arrays are bounded to
5,001 points; every generated segment must fit the complete fixed source-cell
count before its arrays expand. Existing full-grid limits remain 1e-7 m for XY
and station errors and 1e-9/m for curvature, with no best-fit alignment.
These are reconstruction screens, not relaxed geometry-hash identity checks.

The frame remains `APPROXIMATE_SIMULATOR_CONES_NOT_SURVEY` with
`runtime_or_corridor_admission=false`. The source bundle's assumed uniform width
is preserved as provenance; it does not become a certified physical corridor.
Local frame floats are not a cross-platform canonical producer artifact.

## Verification and preserved execution boundary

Fifteen new tests pass, covering actual complete FSG reconstruction, exact saved
channels, immutable DTO projections, cross-course/tampered/invalid inputs,
unsupported FSG CRLF, retained FSI LF/CRLF types, grid allocation caps, failed
reconstruction, native decoding refusal, retyped DTO identity rejection and the
unchanged FSI-only execution registry. The whole six-file source suite passes
93 cases, zero failures/errors/skips, in 4.246 seconds on Linux CPython 3.12.14.

Independent source review passed. Complete FSI LF and CRLF construction results
were compared with the previously installed dev26 package on the same platform;
metadata, original arrays, source/raw pins and every local-frame field matched.
The existing synthetic canonical-artifact tests remain in the full suite.
Raw source/frame check bytes and installed acceptance are retained externally,
bound to the final source/manifest/artifact identities.

The existing `SourceCourse` fields/properties, FSI reference-artifact constructor,
numerical inputs, numerical bridge, worker factory, registry and tournament-plan
acceptance are not widened. Even manually retyping FSG fields as `SourceCourse`
fails the independent FSI geometry/frame checks. The source-preparation type is
not a worker capability or continuation/admission token. All seven policies
remain native `UNRUN`, campaign-ineligible and FSI-only for their existing
numerical contract. Development and held-out results are not merged.

Next integration still requires a complete sampled FSG driving-reference
artifact with its canonical frame and physical gate, a reviewed producer and
admission chain, and explicit reviewed generalization of the FSI reference and
numerical mission contracts. Rebranding an ordinary planner proposal or source
centerline cannot supply those inputs. Original ownership, finite allocation,
source/environment observation, authentication, retention and cleanup remain
mandatory before native execution. No native job, upload or publication occurs
in this source milestone.
