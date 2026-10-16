# Dynamic bicycle acceptance contract (E03/E04)

Frozen before implementation, 16 October 2026. Synthetic, forward-driving,
axle-lumped force-input plant; no car calibration, wheel-slip controller,
pack model or independent wheel authority. The existing lap and four-wheel
plants and their saved records retain their physics.

State: world X,Y (m), heading psi (rad), body u,v (m/s), yaw r (rad/s).
x forward, y left; steering/yaw positive counterclockwise. Parameters:
positive m, Iz, a,b, axle cornering stiffnesses, regularization speed, gravity
and integration cap; nonnegative friction. Defaults are a versioned synthetic
profile, separate from model/topology/backend identity.

Balances: Xdot=u cos(psi)-v sin(psi), Ydot=u sin(psi)+v cos(psi), psidot=r;
udot=Fx/m+r v, vdot=Fy/m-r u, rdot=(a Fy_front_body-b Fy_rear_body)/Iz.
Static axle loads are mg b/L and mg a/L. No rotating-mass correction or wheel
angular states are added. Inputs are axle contact-force requests in N, not
motor torque. Rotate both front force components through steering.

For local tire velocities xf,yf after steering rotation, alpha=atan2(-yf,
max(xf,v_floor)); Fy=C alpha. Rear uses xf=u, yf=v-b r. This converges to
ordinary forward slip angle above the floor; at rest zero velocity generates
zero lateral tire force even with steering. The continuous speed-floor
regularization keeps lateral/yaw dynamics throughout; it is not a kinematic
substitute. Reject reverse states rather than pretending they are validated.

Radially scale the pair (requested Fx, C alpha) to the common mu Fz circle.
Zero load/grip yields zero contact forces. No load transfer, suspension, aero,
thermal or tire calibration is claimed. Report force limits and large-slip
validity separately. Reject nonfinite/Boolean parameters, invalid loads,
steering at +/-pi/2, nonpositive step and derived numerical overflow.

Pure force queries own no mutable controller/sensor/battery state. Held-input
RK4 subdivides using a lateral/yaw stiffness bound and a 50,000-stage-step
budget. A scenario advances fixed plant ticks; logging only observes them,
so changing logging period cannot change the physics. The initial stage has
no controller backend (prescribed axle force); later closed-loop work must
use its own declared causal interface and the four-wheel plant for allocation.

Acceptance scenarios, fixed before tuning:
- Zero-input equilibrium, exact straight constant-force acceleration and coast.
- Zero steer, left/right mirrored maneuver and force/yaw/sign/unit balances.
- Neutral-steer small-angle steady-turn limiting case, with finite-slip caveat.
- Combined circle, zero-load/zero-grip boundaries, stationary steering.
- Continuous low-speed transition, finite admissible inputs, explicit failures.
- Smooth maneuver integration refinement (fourth-order region); independent
  logging-rate invariance; bounded work.
- Versioned scenario/result round trip and replay; separate model, profile,
  topology and backend; actual desktop/browser initial selection and exports.

Primary references accessed 16 October 2026: MathWorks R2026b
https://www.mathworks.com/help/driving/ref/bicyclemodel.html and
https://www.mathworks.com/help/vdynblks/ref/vehiclebody3dof.html distinguish
single-track longitudinal/lateral/yaw dynamics from kinematic steering.
They are design references, not code or runtime dependencies; repository axes
and the equations above define this implementation's signs.

## Execution and evidence

Run `python -m lapsim.ui.basic_dynamics`, or use the desktop header's
**Basic dynamics · bicycle** action. The browser's **Basic dynamics** navigation
opens `basic.html`, running the same Python plant in the existing Pyodide
worker. Both new-session selectors start at the synthetic bicycle. A compact
CLI example is `python -m lapsim.experiments.basic_dynamics --output run.json`;
replay with the same module and `--replay run.json`. Offline source/desktop
execution requires no browser runtime download or controller build.

`tests/test_dynamic_bicycle.py` covers the frozen physical checks;
`tests/test_basic_dynamics_record.py` covers clocks, schema and numerical
replay; `tests/test_basic_dynamics_ui.py` creates actual Tk sessions and checks
selection, execution, stale results, save/load and close behavior.
`quality/run_basic_dynamics_runtime.py` executes actual Chromium/Pyodide runs,
mirrors steering, downloads JSON/CSV, replays in CPython and checks responsive
light/dark views with axe. These are numerical/software evidence. They do not
establish vehicle correlation, steering actuator dynamics or target execution.

Records identify model, parameter profile, topology and backend separately.
Their content digest detects accidental changes, not malicious provenance;
the runtime/source identity is declared metadata. Replay recomputes outputs
from stored inputs and validates solver/units/assumptions too. Absolute and
relative numerical tolerances are each 1e-9 in the declared SI quantities.
Changing controls invalidates displayed/exportable results until rerun.

The initial synthetic profile has mass 300 kg, yaw inertia 160 kg m²,
CG-to-axle distances 0.8 m each, axle cornering stiffnesses 16,000 N/rad,
friction coefficient 1.2 and regularization speed 0.5 m/s. These values are
illustrative. Linear stiffness is a small-slip assumption; recorded slip
angles beyond 0.2 rad carry a validity diagnostic even when friction limiting
keeps the computed forces bounded. No measured calibration envelope is implied.
