# Partial car-profile integration — dev24

The real fixed worker can now consume a complete ordinary `ResolvedManifest`
export as explicit immutable input. The partial fixture projects mass, coupled
wheelbase/front static fraction, front/rear tracks, CG height and air density into
the actual light-model objects. It does not import the ordinary simulator or
require new third-party packages at runtime.

`profile_projection.resolve_partial_profile` requires manifest v1, exact field
units/use classifications, all 15 known selected/inherited paths, consistent
constructor-snapshot values, and the complete raw SHA256 supplied by the reviewed
caller. It preserves the complete raw JSON, declared source hashes, unused
records, field accounting and limitations. These are consistency checks, not
verification of original source artifacts or current authentication.

`fixture.construct_partial_profile_fixture` reuses the pinned baseline recipe.
For wheelbase L and static front fraction f it sets CG-to-front distance to
L*(1-f), CG-to-rear distance to L*f. Other supported fields map directly in SI.
Closed aero cannot supply the two light DRS states; roll-axis heights cannot
supply the roll-moment split. Those and all unmapped inertia, wheel/tire,
powertrain, pack, brake, thermal and controller assumptions remain synthetic and
are individually accounted for. No current/as-built car is claimed.

The existing reference still assumes a 1.4 m wide rectangle extending +/-1 m
longitudinally, a 1.6 m producer wheelbase and other provisional tracking limits.
The adapter rejects wheel centers outside that rectangle; this does not establish
the true tire/body envelope or requalify a line for the changed geometry.

## Actual worker and checkpoint contract

`construct_worker_bridge` adds paired optional keyword inputs:

```text
resolved_manifest_raw=None
reviewed_resolved_manifest_raw_sha256=None
```

If supplied, both must validate before course construction. Invalid profile input
raises; there is no fallback. The resulting complete fixture configuration hash
must match the request's `configuration_sha256` before bridge construction.
With no profile, the original baseline path remains available and unchanged.

The profile raw hash, full JSON, accounting and limitations enter the hashed
configuration and checkpoint context under the new partial fixture family.
`validate_standing_fixture` reconstructs the complete recipe and checks both its
bytes and actual typed objects. All seven policy origins must share this exact
context. Resume revalidates context and refuses baseline checkpoints relabeled
as profile checkpoints. Native origin/request construction must occur after
resolving the same profile configuration, with fresh source/environment/input
admission; the optional argument is not an execution permit.

Bounds are 64 KiB raw/canonical profile, 96 KiB fixture configuration and 128 KiB
profile context. The existing complete checkpoint-body bound remains 256 KiB.
Oversized data fail explicitly without truncating provenance. These bounds are
not a guarantee for arbitrary future profiles/checkpoints.

## Validation and review

From this directory:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src timeout 60s python3 -B -m unittest discover -s tests -v
```

Linux/Python 3.12.14: **62 tests passed**, exit 0, 3.663 seconds. These comprise
20 profile tests, 12 worker preflight/wiring tests, 16 canonical-frame tests and
14 campaign/storage tests. Actual bridge construction/state initialization and
negative resume use synthetic reference and source-observer/residual doubles.
All seven real policy recipes and shared actuation functions are exercised using a synthetic
typed state and static-load observation double. No force evaluation, integration
step, worker process, lap, native observation, admission or cleanup was executed.
Policies retain native qualification UNRUN and campaign eligibility false.

Separate cross-package checks used the actual ordinary public exporter, with an
explicit empty intake directory preventing private-bundle discovery. The first
two checks failed: the normal baseline export was 39,760 bytes, above the initial
32 KiB limit. Raising the explicit profile limit to 64 KiB repaired that integration
gap. Both checks then passed: the actual repository-baseline export projected
285.7631931 kg with all 15 inherited labels, and the actual 39,468-byte Prius
export was rejected for its incompatible reference envelope. A standalone
39,760-byte regression preserves this counterexample without an ordinary-package
test dependency. Original private TREV5 compatibility remains untested.

Independent source reviews found and closed missing complete-field accounting
and acceptance of contradictory `model_use` labels. Root review also removed a
future-runtime availability claim about private TREV5 bytes. Reviewers inspected
source; their review did not rerun tests or establish native qualification.

The no-profile fixture remained exactly 4,075 bytes / SHA256
`d39f13388c29e06814235f0cad9cbd77bb2566e7ba82edf6035034017e8ff3cd`
for the pinned test reference. Baseline context comparison also remained exactly
9,602 bytes / SHA256
`a05e201cd59f5f3b83b78dda629d167aa34fb754b0b96d5f55500de0a43c65e3`.
The latter used identical synthetic reference and S/E declarations; real source
identity must still change for new code. It grants no old-checkpoint continuity.

## Native/UI handoff and remaining release work

The existing exporter requires no user-written adapter:

```text
python -m lapsim.profiles --data-dir <validated-intake-root> preview trev5_working_geometry --output <new-private-file.json>
```

The authorized native owner should retain those exact private bytes and reviewed
raw hash, construct the partial fixture, create matching fresh origins/requests,
and pass the same bytes/hash to the fixed worker. A garage JSON or profile label
does not replace the complete manifest. Export builds/validates an ordinary
vehicle but performs no rollout. No standalone GUI manifest-export button or
active light campaign integration was added in this tranche.

This candidate preserves dev23 commit
`9885a2e2d1dad2e9e40139a991b4ba7f68ab728b` and manifest SHA256
`09f43daf9d76a361cda4fc136017d8ca89a368106732be20d1ac43ad2f5d18cf`.
Earlier dev22/dev23 patches and source packages are unchanged. New source/config
pins and profile-specific admission are required.

Nine-course light execution still needs the other eight actual reference/frame
inputs and a reviewed geometry/clearance contract. Original native ownership,
observation, fixed bootstrap/registration, authentication, finite accounting,
cancellation, writer/continuation and cleanup remain required. Their owners and
launcher/UI source were not modified. No source upload, public publication,
merge, hourly service or verified one-command release is claimed here.
