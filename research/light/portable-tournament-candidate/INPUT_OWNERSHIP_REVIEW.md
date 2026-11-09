# Retained numerical-input ownership — source review

Base: `2cf402ea94939d9a8813018926201eace7b68cce`.
Bounded E07 source tranche. **UNTESTED / UNBUILT / UNQUALIFIED.**

## Independent P2 finding

`SourceTrack` is a frozen dataclass, but its annotated tuple fields have no
runtime constructor check. A directly constructed exact `SourceTrack` can hold
caller-owned lists. Initially correct lists pass the numerical consumer's
geometry digest checks. `raw_reference_inputs` retains that source track and
the bridge retains the original course/reference, so a later interior-coordinate
list change affects source-progress projection and physical-gate winding.
Unchanged stations keep the recorded length and identity strings unchanged;
context construction does not rehash the retained channels on every interval.

The ordinary course constructor produces immutable tuple/bytes fields and
avoids the issue. Direct DTO construction remains accepted by the consumer,
however, so frozen dataclass syntax and an earlier content hash do not establish
retained-input immutability. Unknown nested track objects can also have their
methods called before the consumer establishes their native representation.
This is an input-consistency defect, not an execution-authority bypass.

## Frozen repair contract, before implementation

- Preserve the original course source, scientific kernels, math, fixed input
  identities and all earlier artifacts. Fix the numerical consumer only.
- Before invoking nested track methods, require exact native `SourceTrack`
  objects with immutable tuple channels of finite builtin int/float values,
  explicit closed status and the existing bounded grid/shape inventory.
  Reject mutable/unknown representation rather than silently coercing it.
- Require exact native `SourceCourse`, immutable bounded metadata/frame bytes,
  and immutable typed identity/encoding declarations. Direct DTO construction
  remains no proof of trust; existing geometry/payload/frame/raw-artifact and
  independently supplied identity checks remain mandatory.
- Apply the checks both to the public raw-reference constructor and to the
  bridge before it invokes nested methods or retains the course/reference.
  The reference's retained guidance/source tracks must satisfy the same native
  representation contract before their geometry is compared/rebuilt.
- Normal constructors already emit this representation. Preserve their exact
  numbers and byte projections without cloning, normalization, fallback,
  changed geometry, new authority or invented source provenance.
- These are representation checks, not authentication, a Python sandbox or a
  substitute for genuine loaded-source/runtime/owned-worker controls. Missing
  original producer/observer/predicate/guard/cleanup dependencies remain closed.
- No candidate execution, imports, syntax checks, tests, simulations, inference,
  build, installation, pushes or public publication.

Independent source inspection confirmed the alias path through reference
construction, retained bridge inputs and source-progress projection. No live
object, mutation counterexample or numerical interval was executed.

## Repair and independent follow-up

`numerical_inputs.require_native_track` checks the exact native type before
accessing nested methods, requires tuple channels of finite builtin numbers,
explicit closed status and the existing bounded shape inventory. The source
course helper additionally requires immutable bounded metadata/frame bytes and
typed immutable identity/encoding declarations. The 2 MiB byte-projection cap
accommodates the existing fixed source representations; it establishes no
authentication and does not substitute for the existing exact content checks.

Both `raw_reference_inputs` and the bridge apply these checks before retaining
inputs; the bridge also checks both reference track objects before geometry
comparison/rebuilding. Nothing coerces mutable data into a new representation.
The original course source and scientific kernels remain byte-preserved.

Independent follow-up source review found the retained-input finding addressed
and no concrete regression. It confirmed rejection of lists/unknown objects,
boolean/subclass numeric values and mutable byte projections, normal constructor
compatibility by inspection, unchanged content/identity comparisons and no
import cycle. This is not an executed compatibility or mutation regression.

No candidate validator, constructor, parser, observer/predicate/provider
callback, numerical step, replay, file writer or Tk function was invoked.
No candidate import, syntax check, test, simulation, inference, build or
installation ran. All genuine source/environment/producer/guard/cleanup and
runtime acceptance dependencies remain unresolved as in the integration handoff.
