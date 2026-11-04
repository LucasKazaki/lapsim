# Portable light-plant source candidate

**SOURCE ONLY / UNBUILT / UNQUALIFIED.** This is a prepared library boundary,
not the working light application, a tournament runner or a reproducible release.
No import, build, test, installation, optimization or simulation was executed
for this candidate. The active repository package and accepted archive remain
unchanged. See [remaining integration gates](../../../docs/LIGHT_PORTABILITY.md).

## Implemented source preparation

The unique `lapsim_light_core` package contains the existing planar, actuation,
powered, DRS, force and common tire-thermal code with its local dependencies.
It has no console entry point, UI, server, resource probe, lease acquisition,
course loader or implicit runtime dispatch. Its initializer is inert.

Nine scientific modules were copied from the same source snapshot used by the
light archive. Seven retain their original bytes. In `actuation.py` and
`powered_planar.py`, only `from .bicycle import _finite` changes to
`from ._validation import _finite`. The new helper copies the original function's
body, including boolean rejection, `numbers.Real`, `math.isfinite`, exception
handling and error message. The unused bicycle plant is not bundled.

The source-level import graph therefore uses the Python standard library and
these local modules. It does not import the old package facade, optimizer,
UI/course catalog, `vehicle_model`, NumPy, SciPy, openpyxl, Matplotlib, a fitted
Pacejka model or a TTC dataset. This is a static inspection result, **not an
executed import proof**. The source manifest records file hashes, import edges
and the two deliberate edits. No import path or global environment is changed
by publishing this directory.

The retained generic actuation module supports several topologies, including
RWD defaults. This is **not an AWD-only API**. Any future target test or app must
explicitly select `AWD_TOPOLOGY_ID` with four independent available channels;
it must reject other topology/configuration identities for the requested AWD
campaign. No RWD numerical test was run for this preparation.

## Packaging and numerical identity

The proposed build discovers only `src/lapsim_light_core`, declares no external
runtime dependencies and does not vendor numerical packages. The existing
project's `setuptools>=68` build requirement is retained as a **provisional
declaration**, not an exact environment lock. A future build must freeze the
interpreter, build-tool/wheel versions, hashes and platform without downloading
anything implicitly. No wheel or installed dependency closure is verified here.

The algorithms' component-family labels are retained for provenance; they are
not runtime certificates. The package namespace and source bytes have a new
identity. Its dataclasses are distinct Python types from `lapsim.*`; do not mix
the two packages' objects or reuse old checkpoints/certificates. A future
adapter must bind this complete source manifest and its numerical environment
under a new campaign identity, then pass affected qualification.

This library alone has no driver, seven-policy adapter, racing-line admission,
gate-based lap completion, replay, energy-comparison protocol, official scoring
or guarded execution controller. It cannot resume the historical development
state or claim a completed lap. The [course-input archive](../portable-course-inputs/README.md)
is separate input data and does not supply an admitted racing line.

## Qualification still required

After the existing action-specific execution restriction is resolved through a
supported approval path, independently review a fresh finite qualification plan:
exact package imports without the old checkout; scalar-validation regressions;
explicit four-channel AWD command/achievement and shared battery accounting;
held-input and state-carry/energy closure checks; and artifact build/import
isolation. Use the original actual activity/session/game/memory safeguards,
exclusive lease, deadline and owned cleanup. Publication does not authorize a
test, renew a certificate or restore a retired allocation.

The higher-level bridge must be ported and qualified separately. The complete
simulator and tournament remain blocked/unrun, and private receipt files are
not replaced by success stubs. No executable launch commands are provided here
while the original execution denial remains active.
