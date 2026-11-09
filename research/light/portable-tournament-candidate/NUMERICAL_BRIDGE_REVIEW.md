# E07 numerical bridge source tranche

Base: `38aed320ca7d2e09be9c4c32767f4b02942c5979`. Status: **UNTESTED / NO
IMPORTS / NO EXECUTION**. Earlier branches, patches and original candidate
directories remain preserved. No guard, verifier or environment is invented,
installed, registered or treated as qualified by this source work.

## Frozen contract before the port

- Port the complete archived one-lap numerical lifecycle: stationary
  initialization, explicit state/memory reconstruction, checkpoint/resume,
  observation domain checks, driver/allocator/friction/plant/gate ordering,
  bounded raw chunks, acceptance and raw summary. Keep portable source/types
  and configuration identities distinct from historical qualification.
- Preserve the 1/50/10/20/100 ms global clocks, once-only AWD normalization,
  requested/proposed/limited/achieved controls, shared pack accounting, common
  brake shortfall rejection, atomic accepted state and available rejected state,
  cumulative work/counters, physical finite gate and source/reference separation.
- The absent `stadium.residual_low_speed_regen(u_mps, electrical)` implementation
  remains a mandatory externally reviewed adapter with no default result. Its
  formula must not be inferred from its name or from the separate command clamp.
  A genuine source/runtime identity observer is also mandatory; a declared hash
  or a callback identity attribute is not proof of its provenance.
- A raw reference input must contain sampled guidance geometry, separate source
  geometry, original cone frame/gate, vehicle/clearance parameters and provenance.
  Internal geometry checks do not authenticate producer evidence or replace
  the missing producer/numerical receipt modules. No source-track fallback.
- Independently identified archive defect: `accept_chunk` does not validate or
  endpoint-bind several scientific fields, including yaw, wheel speeds, tire
  temperature and DRS modes. The port must use an explicit full row inventory,
  validate retained scientific fields and bind complete endpoint rows to saved
  state/memory/recomputed observations. Hashes and externally admitted receipts
  remain separate from these internal consistency checks.
- Any guard integration is a new adapter contract, not a recovered original API.
  With no real original provider it must refuse before numerical work. Actual
  activity/session/game/memory guards, exclusive owned lease, fresh allocation,
  deadline/watchdog, once-only challenge, source/runtime verification, execution
  receipt admission and owned cleanup remain required. No local replacement
  watchdog, lock, permit booleans or success stub is introduced.

No new function may be called while Lucas's no-testing instruction remains in
force. Source review, byte/text comparison and metadata hashing are the only
verification authorized in this tranche; independent findings will be recorded.

## Source origin and scope

The numerical lifecycle is ported from archived `light_core_bridge.py` into
`numerical_bridge.py`, using included portable dataclasses, the standing fixture,
explicit raw reference inputs, the existing one-tick adapter and required
external source/residual-rule interfaces. State/memory decoder field inventories,
global numerical ordering, energy/net-increment accounting, rejection atomicity,
raw parent linking and finite-gate completion are retained. Context construction
and source observation use new portable identities; old private-path/demo/line
imports are removed. No optimizer or missing predicate is silently substituted.
The old v1 checkpoint/chunk container shapes are retained for raw-journal
interoperation, not for reuse of historical qualified checkpoints.

Full geometry and physical-gate source files are byte-preserved copies:

- `lapsim_light_course/racing_geometry.py`: SHA-256
  `5db3492dfdf4418a980179f1f7d548e8c2e90cb4d7c3b4ce1c1f2cf4606fa253`.
- `lapsim_light_campaign/gate_ledger.py`: SHA-256
  `438f021c06b28ae44dd1edd0f26baa0fda0487c26bd03f3a2c47500e9852063e`.

Both `cmp` source-byte comparisons returned exit 0. The numerical reference
parameter dictionary is copied from the archived line producer without importing
or bundling its optimizer. Raw artifact bytes are retained in the transport DTO
so live guidance geometry/frame/parameters/gate can be rechecked when consumed.
Source course channels and metadata are reconstructed for payload hashing.
These are consistency checks, not producer/receipt/continuous-clearance approval.

## Independent review findings and source repairs

The independent reviewer audited the archive first, reviewed the full port,
then reviewed its repairs and the new guard adapter. Five findings were
addressed at source level:

1. **Archived incomplete telemetry acceptance.** The port uses an explicit
   51-field row inventory, scalar/vector/type/domain checks and complete first/
   last-row recomputation from saved state/memory and observations. This binds
   yaw, wheel speeds, tire temperature, DRS and other retained scientific fields.
2. **Live reference substitution.** A replaced track could retain old declared
   provenance. The consumer now rebuilds from retained artifact bytes, rejects
   changed live track/source-track/metadata, and checks the source-bundle payload
   reconstructed with its original geometry model field.
3. **Interior telemetry contradictions.** Reference progress aliases must agree;
   negative wheel speed is rejected as required by existing `actuation.py`.
   Saved slip is checked using the planar wheel-plane formula, including its
   zero-normal-load => zero-slip special case. Work and lap counts retain their
   cumulative/physical-gate relationships. No new physical sign rule is invented.
4. **Incomplete combined/DRS resume identity.** Resume now checks automatic DRS
   enable, DRS policy/clock hash and nested thermal/light/configuration hashes
   against fresh expected state, in addition to the combined model hash.
5. **Incomplete guard subclass detected too late.** A provider inheriting the
   unimplemented receipt method could execute before receipt admission failed.
   Provider methods are now abstract, and preflight rejects known bound/unbound
   placeholders before execution. The same early rejection protects missing
   source observer/residual-rule implementations before initialization.

Follow-up independent source inspections found these repairs addressed, with
no further concrete defect identified in the inspected changes. They confirmed
method remaps, numerical ordering, zero-load slip arithmetic, copied file bytes,
segment-slot limits and guard/request/result relationships. Running segment 750
cannot plan or advance another chunk; a terminal output at segment 750 remains
valid within the existing 750-record limit. New port whitespace was normalized;
byte-preserved archive copies retain their original line endings.

No new constructor, parser, source observer, residual predicate, state decoder,
checkpoint/resume, numerical step, endpoint observation, receipt callback or
guarded dispatch function has been invoked. No candidate import, syntax check,
test, simulation, inference, build or installation ran. Independent inspection
does not establish runtime correctness, parser behavior, numerical parity,
cross-platform behavior, crash evidence retention or actual guard enforcement.

## Guard adapter boundary and remaining gaps

`guarded_dispatch.py` is a new protocol for integrating a real original provider.
It imports only metadata/serialization modules and refuses a missing or known
incomplete provider before numerical work. A genuine implementation must map
the original actual guard APIs, authenticate/recheck source/runtime/input and
checkpoint/line data, consume the fresh challenge, own all worker/resource/
deadline/watchdog lifecycle and retain complete raw/partial/failing evidence.
It must finish owned cleanup on every return/exception path and authenticate
exact execution/output/cleanup receipts. No implementation is supplied here.

The adapter verifies request/parent/remaining bounds and requires that real
receipt callback; only bounded JSON/hash/clock/work consistency checks follow
cleanup. It performs no numerical validation outside the owned allocation and
returns only raw transport with no campaign/continuation authority. Its 8 MiB
opaque receipt transport cap is a new bounded interface, not a claim about the
unavailable original receipt format. Oversized/invalid results are refused;
the real provider remains responsible for durable preservation of originals.

Still unavailable: actual `torque_light_demo.residual_low_speed_regen` source,
an authenticated loaded-source/runtime observer and exact environment lock,
`producer_receipts.py`/`numeric_evidence.py` and actual admitted producer bundle,
real original guard/worker/receipt/cleanup API mappings and a qualified provider.
No trusted key, live observation, lease or registration is manufactured here.
Full numerical replay, admitted continuation, durable crash/Stop/Close behavior,
app integration and matched laps need later authorized qualification. This is
source preparation, not a runnable/qualified tournament or a cleared restriction.
