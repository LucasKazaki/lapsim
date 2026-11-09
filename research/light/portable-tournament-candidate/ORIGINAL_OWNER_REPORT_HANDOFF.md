# Original main-PC source report — complete forwarded receipt

Review base: `546ac762c7784fb74da397b0d5c7a262d7c302ba`.
Status: **complete owner reports received; original twenty files not received;
existing public line-binding copy independently identified; no current authority**.

## Receipt and evidence scope

The complete original-owner report was forwarded verbatim in the current
delegation. Its reference is thread `<PRIVATE_CONVERSATION_ID>`,
turn `<PRIVATE_CONVERSATION_ID>`. This resolves the earlier request
for report text. Direct cross-thread reading remains unavailable, but is no
longer needed for this handoff. The report was read as forwarded text.

The owner reports read-only file inspection and SHA-256 hashing on the main PC,
without denial, candidate code/imports/tests/simulation/resource probes, changes
or uploads. The initial twenty-file table below remains **owner-reported**;
its source bytes were not received or imported here. A later supplementary
line-binding pin has now been compared with existing public archival bytes.
The machine-readable inventory is
[ORIGINAL_OWNER_SOURCE_INVENTORY.json](ORIGINAL_OWNER_SOURCE_INVENTORY.json);
its original twenty report entries retain their false local-verification flags.
Its supplemental records and explicit local-availability section distinguish
the one existing exact source copy from the genuinely missing artifacts.

## Bounded cloud source-availability reconciliation

At base `0f9015234934e47074ca59c699201fd34683e844`, the existing
`research/light/awd-standing-v15/line_binding.py` is 8947 bytes and hashes to
`90629a948024c6e6db15026475d8accac5c740a4060fa07c0c489db95fac3aea`,
matching both the public archive manifest and the later native HANDOFF pin.
This is pre-existing local source, not a recovered private transfer, import,
authenticated producer bundle or runtime admission. No code was copied/wired.

New named checks covered ignored local staging paths and source payload headers
in 32 existing scratch patches, plus the relevant named reachable Git paths.
No additional exact original source was found. The ordinary
`scripts/bootstrap.py` is not the reported P09 path or evidence of its source.
The inventory now retains the original 20 pins, adds the four reported r02
helper pins and line-binding pin, and gives bounded availability for all 22
source records. Seven additional P09 siblings lack supplied hashes and their
expected source paths remain unavailable; historical receipt files were not
rechecked. Absence claims apply to the checked cloud scope, not the active PC.
No main-PC operation, transfer, runtime probe or execution was attempted.

## Exact reported roots

```text
R = <ORIGINAL_SOURCE_ROOT>
V15 = R\work\torque-light-awd-racingline-standing-20261102-v15
P09 = R\work\torque-light-awd-line-producer-20261102-p09
EXTERNAL_HELPERS = <ORIGINAL_EXTERNAL_HELPERS_ROOT>
```

These paths are provenance, not runtime defaults or permission to access the
main PC. `V15` expands to the actual **standing** directory above. The guessed
`consumer-…-v15` directory is absent. The two V15 validator files are reported
byte-identical to their v14 counterparts; no v14 path was supplied or guessed.

## Reported original sources and whole-file SHA-256 pins

| Root-relative source | Owner-reported SHA-256 |
| --- | --- |
| `R\lapsim-aero-fidelity-20261028\src\lapsim\experiments\torque_light_demo.py` | `b7ee2a2c822c646203af4b471d8c851685c575fa2477a982d4f0519fc409b171` |
| `V15\producer_receipts.py` | `d622288d48d01a71ddbf13e8fbaa4abb771d78b74627e82d9898116fe23b7e50` |
| `V15\numeric_evidence.py` | `2e440ca9fb615968893b84893b6d28fa3662775a5ef168d49e84cfd4dc547e57` |
| `R\lapsim-public-courses\work\tournament-audit-20261028\run_owned_chunk13.py` | `835e4c0286fabd85c374c404a094d9888f99a8660201f1ae15ff3e9ff5b41a9f` |
| `R\lapsim-public-courses\src\lapsim\experiments\background_readiness.py` | `83beb340bd792f0e02fe7284cd942e1a1da809cfc3eabb91bc1492b2e9cb8c87` |
| `R\lapsim-guard-safety-20261028\scripts\owned_batch_safety.py` | `d84167ec269a88f58647b6a5db501a43c3b2b0a59fb5dc9b27c4d6658588a91c` |
| `R\work\torque-light-stop-qualification-20261031-p01\stop_inner.py` | `ad500198223dcce920671542f384acb08962d080e1e5c913b7a6575fa25d3350` |
| `R\lapsim-public-courses\work\tournament-audit-20261028\chunk_bridge.py` | `816b46ae9c5a621729c35c0a9094221c8c3e263461009c4816b0a96387d3f3e3` |

The table uses root aliases, not literal directories named `R` or `V15`.
The inventory also gives their complete resolved Windows paths.

At line 175 of the reported `torque_light_demo.py`:

```python
def residual_low_speed_regen(speed,electrical):
    return speed<=2 and (electrical.pack_power_w<0 or any(v<0 for v in electrical.wheel_torques_nm))
```

The archive and portable bridge pass `point.u_mps` and evaluated actual
electrical output at this observation boundary. The threshold is inclusive;
strictly negative pack power OR any strictly negative actual wheel torque
triggers the low-speed generating-output branch. No tolerance, absolute-speed
conversion, requested-regen exemption or false fallback is added. Recovering
the predicate does not resolve or qualify the historical regen failure.
No genuine adapter has been installed from the excerpt.

## Original entry points and candidate integration boundaries

| Owner-reported contract | Source-level integration implication |
| --- | --- |
| `producer_receipts.verify_bundle(...)` | Historical bundle consistency, with independently trusted promotion/tool evidence still required. This agrees with the archived consumer's `BUNDLE_CONSISTENCY_ONLY` boundary; it is not platform-event authentication or current permission. Full signatures and `NAMES`/source constants require source bytes. |
| `numeric_evidence.verify_file_inventory(...)`, `validate_phase(...)`, `validate(...)` | Review pinned numerical inventory and before/after observation semantics. Do not turn snapshot evidence into continuous-runtime or transient-load guarantees. Compatibility with the candidate's environment v2/new source identity is unproved. |
| `owned_batch_safety.validate_observation`, `AttemptJournal`, `require_reconciled`, `require_admission`, `ObservationPump`, `OwnedDeadline`, `supervise_owned` | Actual original guard/journal/admission/deadline/ownership interfaces to inspect before implementing the NEW portable `OriginalGuardProvider` adapter. Names alone do not supply callable signatures, cleanup semantics or authority. |
| `run_owned_chunk13.foreground`, `running_games`, readiness observation | Preserve original activity/game/readiness behavior. The owner warns that the observer has top-level reads and module loading. Inspect as text; do not import it merely to discover behavior. |
| `stop_inner.context_snapshot` | Additional bounded resource/context observation used by P09, not a resource probe authorized in this session. |
| Original `chunk_bridge.py` | Inspect worker/bridge/receipt shapes and source identities before mapping chunk, continuation or replay providers. Historical source, file hashes and qualified/runtime identities are distinct scopes. |

The reported public-courses `background_readiness.py` differs from the
guard-safety copy. They are **not interchangeable**. No hash for the other
copy was supplied. No listed module is assumed safe to import before static
effect/closure review. No provider, observer or validator implementation has
been replaced, fabricated, registered or executed here.

## P09 operational source closure

The owner reports these 14 siblings:

```text
contract.py
bootstrap.py
stable_reader.py
stable_writer.py
numeric_runtime.py
runtime_assurance.py
admission_evidence.py
run_producer_command.py
inner.py
production_owned.py
worker_gate.py
worker.py
bounded_caller.py
producer_fixed_body.py
```

Seven principal whole-file hashes were supplied:

| Root-relative source | Owner-reported SHA-256 |
| --- | --- |
| `P09\contract.py` | `10a78b6adbfcc2fee4d354db1b33c1dbd0ae17162656ff1bcb150b1caa8cafeb` |
| `P09\admission_evidence.py` | `b4f81ee8f651eb9085a1b267788452c80d3717d7a52d7003fdd0f8e76ef98460` |
| `P09\production_owned.py` | `ea05971c2cef95d2609eb7cf4389410eaf52e61962b9811588bf1980cb0aa04f` |
| `P09\inner.py` | `dd164533731e7c76e3cdd90ef9b51edabacce4a10f7e6a2314c551b11abeb007` |
| `P09\run_producer_command.py` | `b2f2e7db44c2254946485c4f3573365fcc4e034a6dd99ae7a64be3c05f1fc981` |
| `P09\bounded_caller.py` | `66d07b3d56267bdb537a6db33a1f7f80fc6ff302235481cdbdcffb2fb5bba447` |
| `P09\producer_fixed_body.py` | `d70d4a6e13ce61616b85bf53578079f4257b4db932938c2103c8a1a364edb736` |

The other seven sibling hashes were not supplied; the inventory leaves them
null. This is not a claim that a complete portable dependency closure exists.

P09 also depends on two reported original helper files outside R:

| Root-relative source | Owner-reported SHA-256 |
| --- | --- |
| `EXTERNAL_HELPERS\experiments\chess-queen-v1\gpu_worker.py` | `1164d8fd1dbc59221a7d51ce410bb5e9a3109998fd3b6f9d00db071d237948c0` |
| `EXTERNAL_HELPERS\experiments\chess-queen-coach-daytime-v1\owned_worker_v2.py` | `fe4ce0abb0f6be934f2b78681115ec0aa0c9c85e2ef54a6955dc2e6778103ae8` |

Those external files were reported present and matching their declared pins.
Neither they nor a shared lock were accessed from this environment. The owner
also reports no shared-lock access during inspection. Source dependencies in
the separate chess-named tree do not authorize running that project, acquiring
its lease, probing its jobs or changing its shared resources.

## Historical producer evidence — not current admission

| V15 file | Owner-reported SHA-256 |
| --- | --- |
| `V15\producer-promotion-manifest.json` | `0bf61c3119a5cb3b9f1e5fe32b776ebff11a44cd67fd58c53365943e842b0112` |
| `V15\line-artifact.json` | `1779ff9b9254f16e09a49f24d45603f3e7de88edb7650055e6aa5159e4e6a00b` |
| `V15\line-artifact-admission.json` | `1b71ddca7d0fca99d2cb7db679eef6d274eacecd2a23402e83cb1103d108b5a6` |

`V15\producer-receipts` contains 14 reported receipt files. The promotion
map's two remaining logical entries refer to the root `line-artifact.json`
and root `line-artifact-admission.json` (logical name
`independent-audit.json`). Their individual 14 filenames/hashes and the actual
promotion-map bytes were not supplied. No such inventory is invented here.

These are historical local bytes, not freshly authenticated platform receipts,
new signatures or current admission. Do not install the historical promotion
SHA as a newly approved trust anchor solely from this report. The candidate's
separate signed-input, source/runtime, original-guard and owned-cleanup gates
remain mandatory. Earlier source IDs/checkpoints/qualifications do not migrate.

No verified self-contained private archive was established. Original files
retain absolute paths, external dependencies and expired phase-specific
allocations. In particular, **P09's historical 180-second accounting is not
today's reported 120-second contract**. Neither duration is a fresh allocation
to this cloud task; no wall-time request or spent budget is reset/populated from
these historical values. Current contract bytes/permission remain separate.

## Minimum source transfer for later adaptation

No source bytes are needed merely to record this report; that documentation
step is now complete. Transfer/publication, full dependency qualification and
runtime authorization remain separate gates. No transfer is attempted here.

For a later authorized static adaptation, use small tranches and preserve bytes:

1. Predicate/validator review can start with the reported `torque_light_demo.py`,
   `V15\producer_receipts.py` and `V15\numeric_evidence.py`. Preserve their
   original line endings, declared byte counts and reported whole-file pins;
   hash the received bytes independently and inspect text without imports.
   This is an initial review set, not a claim of complete closure.
2. Before mapping guards/observers/worker bridge, obtain the other five exact
   original source files in the first table, then only imports/types/constants
   their static source actually requires. Keep the two readiness copies distinct.
3. For P09 execution/receipt mapping, follow actual static imports through its
   reported siblings and the two external pinned helpers. Obtain missing hashes
   for any additional files selected. No guessed closure, broad machine copy,
   helper import or shared-lock access substitutes for this review.
4. Historical receipt consistency review additionally needs the three root
   evidence files listed above (including the promotion manifest) and the exact 14-file
   receipt name/hash map and unchanged bytes. This remains separate from fresh
   supported-tool/cleanup authentication and any current operation admission.

The full function/module signatures, complete import/effect graph, required
numeric/backend versions, concrete supported tool/receipt/cleanup mapping and
current allocation semantics cannot be recovered from filenames alone.
Absolute paths are not wired into the portable candidate. Runtime controls and
all genuine execution providers remain absent/disabled.

## Source review completed here

The forwarded predicate was compared by source inspection with archived and
portable observation calls. The archived `line_binding.verify_producer_receipts`
already requires independent promotion/tool evidence and checks consistency
only; the new source locations do not change that gate. The reported named APIs
have been mapped above to the candidate's deliberately unresolved interfaces,
without assuming matching signatures or importing top-level-effect modules.

No original source file bytes were received or locally rehashed, no PC resource
or shared lock was touched, and no candidate module/code/test/simulation/
inference ran. No permission setting, source adapter or runtime behavior was
changed, and no push or public publication was performed.

An independent read-only reviewer compared the documentation/inventory with
the compact baseline transcribed from the forwarded report. That reviewer did
not have the full forwarded report in its inherited context and did not inspect
original file bytes. All 20 pins, resolved roots, the predicate, 14 P09 siblings,
receipt layout and authority limits matched the supplied baseline. One P3
wording finding double-counted the promotion manifest in the minimum transfer
list; it was corrected to three root files total, including the manifest. The
reviewer rechecked the correction and the explicit NEW observer API and
original-source transfer flag scope, with no remaining concrete finding in
those refinements. This is transcription/contract inspection, not independent
verification of original source bytes or successful runtime integration.

## Frozen native HANDOFF report received on 6 November

The parent forwarded the original owner's read-only extraction from turn
`<PRIVATE_CONVERSATION_ID>`. This is additional reported source
evidence, not transferred module bodies or a measured runtime. The reported
`HANDOFF.md` SHA-256 is
`48a63f1d5fdf667bf865057601d254c9268ad5b5ba0a94a9ee845056779996d9`.
Its full filesystem path was not supplied in this reply and is not guessed.

`B = R/work/original-source-bindings-20261105-r02`; `P` and `V` in that report
are the same producer/standing roots called `P09` and `V15` above. Reported r02
manifest: `a792a2a1b6ff322ec02fcf2a118875e7e498b8ba12099b8dc1f22c67f27dae80`.
Reported r03 isolated cleanup-repair manifest:
`abeea981cd2e1577334650ffd1a27f0300d7a353c54744e11307a66507d7d6a3`.
No r03 root path was supplied. Both candidates are source-reviewed, unimported,
untested and unqualified; their manifest pins are not complete runtime identity.

| Source relative to `B/src/lapsim_original_bindings` | Reported SHA-256 |
| --- | --- |
| `residual_regen.py` | `570438d155f28edd1eefdcc165cfd4b9ca4e516d5cd18a942dc12d7a5e1a987c` |
| `producer_layout.py` | `64975a1f3aaaa9720c66d9f88d50adba3eb054474187749af21bded9ca5d1371` |
| `loaded_sources.py` | `ca23a15bedf12a13bc67725866ff0d3eee79c64ff556e413fac1d9180c68d85e` |
| `line_review.py` | `80a6bf964c91b2647edc70b8f7bc57e233948327e8c047f251203c017292273b` |

The reported helper interfaces are:

```python
RecoveredResidualRegenRule(implementation_sha256)
rule.residual_low_speed_regen(u_mps, electrical)
assemble_original_line_evidence(
    *, promotion_raw, expected_promotion_sha256, receipts_by_filename,
    root_line_artifact_raw, root_line_artifact_admission_raw)
bundle.original_arguments()  # promotion bytes, expected pin, fresh 16-item dict
record_loaded_module(
    module, *, expected_module_name, source_path, source_raw,
    expected_source_sha256, critical_exports, compiler_flags,
    compiler_optimize, critical_globals=())
observe_loaded_bindings(bindings)
prepare_original_line_check(bundle, *, consumer_source_manifest_sha256)
```

The residual binding requires the NEW adapter-file pin above; the original demo
hash is provenance. The loaded helper covers selected module/function/code/global
bindings, not complete disk/native/stdlib/numerical-runtime observation. The
assembly returns `StagedOriginalLineEvidence`; `prepare_original_line_check`
returns `PendingOriginalLineReview` with false qualification/execution authority. None of
these implementations is imported, recreated or configured in the cloud CLI.

The actual `V/line_binding.py` pin is reported as
`90629a948024c6e6db15026475d8accac5c740a4060fa07c0c489db95fac3aea`.
Its APIs are `verify_producer_receipts(audit, artifact_raw, *, promotion_raw=None,
reviewed_promotion_sha256=None, evidence=None)` and
`load(source_track, *, reviewed_promotion_sha256)`. The earlier validator pins
remain unchanged. `verify_bundle(promotion_raw, expected_promotion_sha256,
evidence)` still returns `BUNDLE_CONSISTENCY_ONLY`, not independent tool
authentication or campaign eligibility. The 14 receipts plus two root files
have 2 MiB/item and 8 MiB total bounds, including promotion bytes. Real `load`
also checks geometry/frame, original generator bytes, chord distances, physical
gate and optimization labels; dynamic replay remains unqualified.

Original `owned_batch_safety.py` retains the pin in the earlier table and exposes
`supervise_owned(*, journal, observe, create_owned, verify_stage,
allocation_s=180)`. Its process adapter needs `identity`, `go`, `poll`,
`terminate`, `prove_empty`, `close`. The 180-second default is historical.
Required controls include fresh ownership/session/activity/game/RAM/VRAM checks,
exclusive nonblocking lease, empty Job membership AND signaled stable-process
exit, joined watchdogs/observers/output readers before handle closure, and an
enclosing deadline covering verification and cleanup. `verify_stage` follows
the leaf watchdog. Unproved cleanup requires `FatalCreatorExit` inside the lease,
without normal release/success; local staged receipts still need actual external
terminal evidence. r03 repairs creator exit before handle closure when its
watchdog stays alive; it is isolated and NOT applied to P09.

The owner explicitly confirms ABSENT complete portable `SourceObserver`,
authenticated line-admission provider, `OriginalGuardProvider`, fixed worker
registration, native campaign-start provider and exact installable runtime/
dependency lock. Original v3 snapshots do not fill portable-v2 ABI, stdlib,
distribution and rounding fields. This is not merely a patch-delivery blocker.
The file CLI operates on the existing portable schema; its local import hygiene
is not a replacement for these missing original runtime observations or guards.

## 2026-11-08 main-PC source assessment update

The coordinating parent forwarded a further read-only main-PC assessment:
original `torque_light_demo.py` matched SHA256
`b7ee2a2c822c646203af4b471d8c851685c575fa2477a982d4f0519fc409b171`,
and recovered `residual_regen.py` matched
`570438d155f28edd1eefdcc165cfd4b9ca4e516d5cd18a942dc12d7a5e1a987c`.
Its seven-file source manifest was reported matching. No new manifest SHA or
file list was supplied in that update, and none is inferred here.

This strengthens reported source presence on the main PC. It does not provide
source bytes to this cloud checkout, authenticate an executing callable/import
closure or numerical environment, or grant current native admission. The adapter
implementation pin remains distinct from the original demo's provenance pin.
No private file was transferred or imported and no reported formula was recreated.

The earlier exact reported predicate applies the speed-at-or-below-2 condition
to **both** negative actual pack power and any negative actual wheel torque.
The latest prose summary is not a new precedence contract. No requested-regeneration
exemption, absolute-speed conversion, tolerance or changed threshold is inferred.
The development consumer's separate OFF-domain rejection remains unchanged.

Current native observation must bind actual loaded adapter/function/code/global/
import identities to the reviewed sources, establish the complete supported
numerical environment/source closure, and supply genuine input/history admission,
fresh owned guards/allocation and terminal/cleanup evidence. Historical manifests,
source hashes and successful synthetic replay do not supply those observations.
