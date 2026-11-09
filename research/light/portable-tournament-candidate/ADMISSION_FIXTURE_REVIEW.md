# Admission and fixture source tranche — frozen contract

Status: **UNTESTED / NO IMPORTS / NO EXECUTION**. This extends integrated source
commit `055bb7b8e95f8baedc82bc2adb5a737c805d00f6`; the two original candidate
directories and branches remain preserved. No trust anchor, signing key,
qualified environment or executable provider is installed or registered here.

## Source contracts before implementation

- Admission is an external trust boundary. The archive's `producer_receipts.py`,
  `numeric_evidence.py`, actual producer bundle and supported-tool receipts are
  absent. A self-hashed local JSON file, local success booleans or an arbitrary
  object with a promising type cannot replace them.
- The new admission adapter requires an owner-supplied, independently pinned
  detached-signature verifier and out-of-band Ed25519 public-key policy. No
  default verifier, signing helper, sample key, key discovery or configuration
  mutation is provided. Its statement binds audience, purpose, caller's fresh
  nonce, bounded validity, exact source/config/course/line/environment identities
  and raw supported-tool/review/cleanup evidence. Authentication of a statement
  does not execute geometric/physical validation or grant resource authority.
  The trusted external owner remains responsible for reviewer/receipt semantics,
  public-key/verifier provenance, trustworthy time and non-reused challenge state.
  This is a proposed portable protocol, not a claim that old receipts use it.
- Environment closure accepts only a complete, externally pinned exact recipe
  and a matching observation supplied by the trusted owner. It requires exact
  interpreter/platform/standard-library/dependency artifacts and source identity;
  it rejects missing/extra/drifted observations. It performs no probe or import
  and creates no environment lock from the current machine. Local declarations
  remain unqualified until authenticated and observed by the external owner.
- The fixture loader takes the byte-pinned archived parameter snapshot, uses
  explicit portable classes with exact fields, and preserves every physical,
  thermal, DRS, actuation and road value. Only the archived standing-start
  driver/reference/horizon changes are allowed. The old 5 m/s initializer stays
  historical provenance and is never used as a standing initial condition.
  Fixture construction is not line admission or a plant initialization run.
- Where clear, extract the archived one-tick work-counter adapter unchanged,
  under the portable imports. It remains a numerical primitive, not the full
  guidance/allocator/gate/checkpoint stepping bridge or a dispatch entrypoint.
  Actual resource checks, exclusive lease, deadline, watchdog, cleanup admission,
  full line validation and output validation remain mandatory external gates.

An independent read-only source review of commit
`8248069735c25d93a37221aaeb28be4e8786c305` completed on 5 November 2026.
It found no concrete defect in the assigned admission/environment/fixture/tick
scope. The reviewer confirmed the constructor inventory, archived driver
overrides, exact resource bytes and counter arithmetic. This is source review,
not executed acceptance or proof of runtime correctness.

## Manual review findings and changes

1. **Authentication boundary.** The signed statement uses domain-separated
   canonical bytes and exact field sets. Review covered key/audience/purpose,
   source/config/course/line/environment pins, raw receipt hashes, expiry and
   challenge binding, and callback error/return handling. It found that an
   ellipsis-only Protocol method could be inherited as a no-op returning `None`.
   The protocol now raises `NotImplementedError` unless a real implementation
   overrides it. A verifier identity attribute still does not prove its source;
   the externally reviewed bootstrap must provide the trusted implementation.
   Direct construction of a result DTO confers no authority. No real verifier,
   key, signed statement or receipt has been supplied or authenticated here.
2. **Environment declarations.** Interpreter versions require an exact full
   version; distribution versions reject ranges/wildcards and floating aliases.
   Declared executable, standard-library and verifier hashes must agree with
   their artifact inventory. Recipe and observation must match exactly with
   no extra/missing field. This remains declaration comparison, not runtime
   measurement; a copied/fabricated observation is not made trustworthy by it.
3. **Fixture closure.** The 6021-byte resource matches archival SHA-256
   `cef3c04c808f3ab8dc0f767ec4a0f24865dcd67371ac45f52689c67a0e145d22`.
   Its historical configuration digest remains
   `782eaf45732856e77c77affa25d79b0aefbd7d62ebee8ce37e7835c7a52dfb9f`.
   Explicit constructors were reviewed against the included dataclass fields;
   there is no dynamic class selection or silent default filling. Constructed
   physical values are compared with the canonical snapshot before the
   standing driver is produced. Only the archived one-lap reference/horizon/
   zero-speed overrides are made; synthetic car/pack/thermal/aero assumptions
   are unchanged. The new fixture identity inherits no historical acceptance.
4. **Tick primitive and package boundary.** The work-counter arithmetic is
   extracted from archived bridge lines 507–525. One explicit four-channel AWD
   topology check is added; the original counter reset/restore operations are
   retained. This is not an executed parity result or full stepping bridge.
   The resource is explicitly listed in package-data metadata. Initializers
   remain inert; all new imports name standard-library or included modules.

Source-text and byte comparisons are the only checks performed. No new
constructor, parser, verifier callback, recipe matcher, resource loader or plant
step has been called. Independent inspection does not establish package/import
acceptance, signature behavior, numeric-environment observation or physical
qualification. Source-only warnings do not become permission to run.

## Remaining gaps and dispatch decision

The original producer receipt verifier, numerical evidence module and actual
supported-tool/review/cleanup bundle remain unavailable. The new detached
protocol needs review plus a real trusted key/verifier integration; it does not
retroactively authenticate old evidence or create new trusted receipts.
Environment manifests need real, externally authenticated observations and a
frozen build/interpreter/dependency recipe, not values invented from this task.

Full racing-line/swept-footprint/gate admission, driver/allocator/log scheduling,
complete state/checkpoint continuation and output/owned-execution receipt checks
are not closed. The original activity/session/game/memory observer, exclusive
lease, finite deadline/watchdog and owned-cleanup APIs are not available here.
No guarded dispatcher or provider registration is added while those contracts
and authentic providers are missing. No alternative guard, local success stub,
automatic resume or source-track fallback substitutes for them. This is an
explicit integration blocker, not a new action denied during this source tranche.
