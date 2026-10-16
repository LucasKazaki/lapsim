# Fixed-clock synthetic rear-drive experiment (E03/E06/E07)

Acceptance contract frozen 16 October 2026 before implementation. This extends
`controller_testing_contract.md`; original controller files remain immutable.
The first supported topology is **synthetic independent-rear RWD**. FL/FR
propulsion are zero. Two rear motors are an experimental assumption, not a
statement about the current team car. Differential RWD and AWD are unavailable.

The existing ten-state planar plant owns world X/Y, heading, body u/v, yaw and
four wheel speeds, including wheel/rotor inertia exactly once. Its pure force
evaluation computes achieved contact force from slip, not command torque/R.
Its existing low-speed tire regularization and synthetic validity limits apply.

Actuation contract: SI wheel-side torque is converted to motor torque using
declared gearing and direction-dependent gear efficiency. Motor torque is
bounded by peak torque, torque/current constant, motor and inverter current,
constant-power speed envelope, and a hard maximum speed. Motoring power flows
from pack through inverter/motor/gear losses; regeneration reverses the flow
with the corresponding efficiency products. A declared equivalent copper
resistance adds I²R loss, including at standstill. Regenerative torque is
restricted to the monotonic generating branch of that loss model. Negative
wheel speed is outside this first actuation domain and fails explicitly.

The pack is explicitly an ideal constant-voltage energy store, with declared
capacity, voltage, discharge/charge current and power caps. It is not an
electrochemical or thermal model. Shared bus power and interval energy bounds
apply to both actuators together. Available energy/headroom divided by the
remaining integration interval bounds signed bus power **before** evaluating
the plant. Integrate the signed ledger with the same RK stages as the plant;
never clip SOC after a solve. Empty/full boundaries cut propulsion/regeneration
respectively. Friction braking remains available during a propulsion inhibit.

Actuator memory follows declared lag and torque slew on the plant clock. Every
RK stage applies instantaneous physical bounds to the lagged request. Record
command, actuator memory and actual bounded torque separately; state memory
cannot authorize torque above current capacity. The energy ledger records pack
draw, wheel drive work, nonnegative conversion loss, contact dissipation,
friction-brake work and external/aero work. Check total mechanical plus pack
energy against the declared loss/work terms, with refinement evidence.

A final supervisory inhibit bypasses ordinary torque lag: it resets the
abstract torque-response memory to zero at that controller boundary, without
changing wheel speeds, mechanical or pack energy. This model contains no
separate magnetic-energy storage state. This preserves the imported guard's
immediate-inhibit policy and prevents latent response credit on recovery;
ordinary valid pedal changes retain modeled lag/slew. The reset is recorded.

Clock contract: integer microsecond plant time, integer-millisecond controller
period. Controller, sensor sample, sensor arrival and logging periods are
separate exact integer multiples of the base plant period. At a boundary:
apply explicit reset; create scheduled timestamped samples; deliver due
messages ordered by arrival and sequence; reject duplicate/out-of-order/future
samples without replacing the last accepted sample; call the controller once
if due; hold its guarded command during pure plant RK stages; log observations
without changing any state. An initial controller snapshot is unavailable
until a sample actually arrives. Delayed inputs never receive future truth.

The sensor adapter supplies normalized driver pedal/brake/steering, enable,
validity and wheel speeds plus body velocity/yaw as ideal synthetic sensor
measurements. It owns timestamps/session/sequence. The controller interface
receives only this snapshot, never the plant object, grip or true tire loads.
The traction strategy estimates longitudinal contact speed from the sampled
body motion and geometry. This is explicitly an ideal synthetic sensor study;
no estimator accuracy or production sensor suite is implied. Equal-split and
traction-limited runs share input/sensor realization, clocks and constraints.

Reuse the imported allocator, guard, pedal trust, fault/recovery and clock
owners in an incremental adapter. Preserve raw allocation and inhibition
reasons. Default backend is Python; native and emulator are separate explicit
capabilities. Do not label a fallback as either. Regeneration is a separate
bounded brake-demand path enabled only by healthy supervisor state; the
imported propulsive allocator does not suddenly support negative requests.

Frozen scenario matrix is TC-S01–TC-S12 in the parent contract. Required first
checks: standstill ramp, mirrored corner exit, split grip, actuator loss,
speed/power limits, empty/full SOC and brake transition, overlap/stale/invalid
inputs and latch recovery, delayed/duplicate/out-of-order arrivals and reset,
plant-step refinement, logging independence and actual backend comparison.
Numerical tolerances: force/power algebra 1e-9 relative/1e-8 SI absolute;
mirror states 1e-8 SI absolute; native/reference per-owner established contract;
energy integral refinement must reduce residual, with the actual residual
reported rather than hidden by a broad arbitrary threshold.

Versioned records reuse canonical JSON/content/runtime identity and keep every
input, source/model/profile/topology/backend ID, actuator/pack parameter,
sensor injection, controller event and logged plant/energy observation.
Recorded-input replay reruns the selected backend explicitly. UI follows actual
records. No physical transport, hardware access, measured calibration or safety
approval is part of this contract.

The raw driver wheel-torque map divided by radius is recorded **only as a
longitudinal contact-force proxy** (including the declared friction-brake and
regen request maps). It is never substituted for achieved contact force.
Integrate the proxy, actual sum of longitudinal body-axis tire forces and
absolute difference on the plant's RK stages. These diagnostic integrals do not
depend on logging. During pedal faults the raw contradictory input remains
visible; its proxy error is a diagnostic, not a valid-demand approval metric.

Brake-stop repair contract, frozen after reproducing review counterexamples:
RK trial stages must not pass a negative wheel speed into forward-only
actuation. Bound a decelerating braked wheel's substep to one quarter of its
linearized stopping time, then subdivide any rejected trial without advancing controller,
sensor or logging clocks. At a decelerating, friction-braked wheel speed at or
below 1e-9 rad/s, resolve the static stop to zero and record its remaining
kinetic energy separately as wheel-stop dissipation. The default wheel's
maximum event energy is 1.5e-19 J; it is never assigned to the battery. Retain
all integrated brake/contact/pack work and check total energy/refinement.
Actual RK trials plus stop events share the 50,000-work budget. Non-braking
reverse motion stays outside this adapter's domain. This is solver policy v2
and closed-loop record v2; earlier development v1 records remain tied to their
recorded source rather than silently replaying with a different policy.

Browser comparison import accepts at most 40 MB of strict JSON. It reruns both
stored Python scenarios before displaying an imported result, verifies the
comparison identity, common inputs and metrics, and preserves the original
record identity on export. Imported controls are read-only until New preset.
Cancellation terminates the owned worker; changing a new preset invalidates
its displayed result. Native/emulated records do not silently replay as Python.
