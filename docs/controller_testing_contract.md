# Bicycle and closed-loop torque-control test contract

16 October 2026. **Design/acceptance specification, not implemented functionality.** Implements E03/E04/E06/E07/E08 in [the work plan](../ENME408_IMPLEMENTATION_PLAN.md), extending existing R01/R02/R04/R06. Existing plant/source basis: [four-wheel dynamics](four_wheel_dynamics.md), `src/lapsim/dynamics/planar.py`, `src/vehicle_model/` and the imported controller lineage described in E02.

## 1. Keep four choices independent

Every experiment declares:

- `model_id`: prescribed-path lap, kinematic bicycle, dynamic bicycle or independent-wheel planar dynamics.
- `vehicle_profile_id`: synthetic reference or a source-backed configuration with explicit inherited defaults.
- `drivetrain_topology_id`: single-motor/differential RWD, independently driven rear wheels, or a declared AWD example.
- `controller_backend_id` and strategy: Python reference, native C, emulator or physical board; equal split, traction limiting or a later yaw/allocation strategy.

Use a capability check for unsupported combinations. A bicycle is useful for longitudinal/lateral/yaw verification but cannot independently validate four wheel slips. Four array slots in a controller do not prove four physical motor channels. Existing abstract slots remain abstract until a reviewed topology adapter maps them.

New basic sessions should open the synthetic bicycle. Preserve the existing distance-domain lap route and prior saved-record behavior. Selecting independent-wheel allocation switches explicitly to the four-wheel plant; never silently attach four independent actuators to an axle-lumped bicycle and label the result physical validation.

## 2. Bicycle requirements and reference equations

Implement the low-complexity baseline first without replacing the existing planar model. A kinematic mode is an analytic/reference exercise; the required dynamic mode includes lateral velocity and yaw rate.

Use the existing body convention: x forward, y left, yaw/steering positive counterclockwise. State for the dynamic bicycle: world `X,Y`, heading `psi`, body velocity `u,v`, yaw rate `r`. Front/rear CG distances are `a,b`, wheelbase `L=a+b`, positive mass `m` and yaw inertia `Iz`. All runtime units are SI; convert degrees/psi/RPM only at explicit interfaces.

Reference rigid-body balances, with all tire forces rotated into body axes:

```text
Xdot = u*cos(psi) - v*sin(psi)
Ydot = u*sin(psi) + v*cos(psi)
psidot = r
m*(udot - r*v) = sum(Fx_body) + Fx_external
m*(vdot + r*u) = sum(Fy_body) + Fy_external
Iz*rdot = a*Fy_front_body - b*Fy_rear_body + Mz_external
```

For a forward-driving small-slip baseline, declare the slip convention explicitly. One consistent choice is `alpha_f = delta - atan2(v+a*r,u)` and `alpha_r = -atan2(v-b*r,u)` with `Fy=C_alpha*alpha`, positive stiffnesses and a documented validity domain. Rotate the front longitudinal/lateral force through `delta`; do not drop its longitudinal projection silently. If adding saturation, combine longitudinal/lateral force consistently instead of independently granting full grip in both directions.

No division by an arbitrarily tiny speed may generate unbounded yaw/side force. Specify a tested low-speed mode/blend or explicit domain rejection, including transition behavior. Reverse is unsupported until deliberately modeled and tested. `r = u*tan(delta)/L` is a low-slip kinematic reference under its assumptions, not an exact high-speed dynamic target.

Analytic/structural tests: zero input equilibrium; straight propulsion/coast; constant-speed small-steer reference in its stated domain; zero-steer symmetry; left/right mirror; positive mass/inertia/wheelbase and finite-input checks; zero/low-speed behavior; continuous mode transitions if blending; integration refinement. Compare to the four-wheel plant only on matched supported limiting cases with aligned stiffness/load/inertia assumptions.

Reference reading: [MathWorks bicycle model](https://www.mathworks.com/help/driving/ref/bicyclemodel.html) and [vehicle 3DOF documentation](https://www.mathworks.com/help/vdynblks/ref/vehiclebody3dof.html), accessed 16 October 2026. These distinguish single/dual-track models; they are not implementation dependencies or team calibration. The MathWorks vehicle-body convention may differ from this repo; do not copy signs blindly.

## 3. Signal and driver-demand contract

Scenario input is a versioned, finite, bounded data file. Reuse existing serializers where possible. Include a schema/model version, explicit validity, units/axes, sampling timestamps/clock domain, source/provenance, initial state, parameters, seed and maneuver definition. Unknown values remain null/unavailable outside typed required fields; reject an experiment that lacks a required input.

A driver input sample should distinguish normalized accelerator, friction-brake demand/pressure, road-wheel steering or an explicitly calibrated steering-wheel value, requested mode, enable state and timestamp/age. Two pedal channels and their reconciliation need their own evidence/validity when modeling the real interface. Do not invent a steering ratio or turn a driver percentage directly into an unexplained wheel torque.

Demand processing stages:

1. Validate freshness, type/range, pedal consistency and enable state under a declared policy.
2. Convert driver input into aggregate longitudinal demand using a versioned pedal map. For example fixtures only, a labeled map may scale a declared envelope by normalized pedal. Team calibration is pending.
3. Apply approved supervisory limits, requested operating mode and optional reference-yaw/traction logic.
4. Allocate the achievable demand across the declared independent actuators.
5. Apply the final guard/inhibit/rate envelope, simulate actuator response and advance the plant.

The default synthetic baseline should not automatically increase total propulsion above the driver's declared request to improve a yaw metric. Any later strategy that trades longitudinal demand for yaw support needs an explicit policy and comparison. Independent friction braking is not silently erased by a propulsion inhibit.

## 4. Output stages must remain distinguishable

Record at least:

| Stage | Meaning |
|---|---|
| Driver input | Pedal/brake/steering sample as supplied, with validity and age |
| Requested aggregate | Desired longitudinal force or explicitly defined torque, and optional yaw target |
| Proposed allocation | Raw allocator result, even when later rejected |
| Feasible/guarded command | Accepted per-actuator command after topology, capacity, power, freshness and final inhibition |
| Actual actuator output | Torque after modeled delay/slew/limit behavior, or measured actuator feedback if genuinely available |
| Realized plant response | Tire contact forces, wheel acceleration/slip, body acceleration/yaw and energy |
| Unmet demand | Residual longitudinal/yaw demand and active limiting reason |

Use units in names. Define motor-side versus wheel-side torque and the wheel ordering `FL,FR,RL,RR` at the adapter boundary. Preserve the imported core's original abstract-slot API separately. A native producer result that fails the acceptance boundary stays visible as rejected evidence; do not rewrite it to a successful clipped candidate.

The plant owns physical state and achieved forces. The controller owns its estimator, integrators, latches/recovery and prior command state. The scheduler owns clocks/sequence order. The UI only reads results or submits a new run configuration. Pure force/limit queries cannot mutate battery, tire, aero or controller state.

## 5. Actuator feasibility and topology

The initial supported topologies must be named synthetic examples until confirmed by the team:

- One rear drive actuator plus a specified differential model: there is no independent left/right motor command. Equal rear splitting is an explicit idealized differential assumption, not evidence of the actual car's differential behavior.
- Two independent rear actuators: front propulsion is zero; rear left/right freedom is explicit.
- Four independent actuators: an AWD research example, not a confirmed 2027–28 bill of materials.

Map actuator torque to wheel torque with the declared ratio, losses and direction convention. Motoring and regeneration power flows need separate tests; do not reuse one efficiency multiplier in both directions without derivation. Use actual wheel/motor angular velocity for power. Near standstill, low mechanical power does not remove motor current/torque limits.

Feasibility covers per-actuator torque-speed envelope, inverter/current limits, shared pack power/current/voltage, generating/charge acceptance, SOC interval capacity, unavailable actuator flags, and declared rate/delay. Declare whether a bound is hardware-derived, an estimate or a synthetic test assumption. Do not invent a thermal curve to fill a missing field.

Wheel dynamics matter:

```text
J_i*omega_dot_i = Tdrive_i - Tbrake_signed_i - R_i*Fx_wheel_i - Tloss_i
Mz_tires = sum(x_i*Fy_body_i - y_i*Fx_body_i)
```

Consequently `T/R` is not automatically the realized contact force during wheel acceleration/slip. If the allocator uses a quasi-steady force proxy, record it as predicted and compare against the actual integrated contact force. Count wheel/rotor inertia exactly once and document any reflected inertia.

Maintain a signed energy ledger for pack, losses, shaft/wheel work, wheel/body kinetic energy and external forces. Nonzero wheel slip and wind require the declared contact/external-work terms; do not claim `pack energy = translational kinetic energy` universally. Start conservation checks with simplified zero-loss/no-wind matched fixtures, then add each loss/external term with its sign verified.

Do not use the distance-domain solver as a fixed-frequency controller clock. Its component interfaces may be reused where consistent, but it has different state/update assumptions.

## 6. Allocation strategy progression

Preserve and test the imported bounded allocator before introducing new algorithms. Implement an equal-split feasible baseline first, then traction-limiting comparisons. An electronic differential should respect turning kinematics; it must not force all wheel speeds equal through a turn or call the resulting scrub traction control.

For yaw allocation, explicitly define desired wrench `w=[Fx_request,Mz_request]` and a topology/steering-aware prediction `w_hat=A*q+w_other`, where `q` is declared actuator effort or a force proxy. Account for steered wheel force rotation and the full moment arm above; a track-width-only shortcut needs its restricted assumptions documented.

A later bounded least-squares/QP candidate may minimize weighted longitudinal/yaw error plus command-change effort, subject to feasible actuator/rate/shared-power constraints. This is a proposed strategy, not an implemented solver. Normalize objective units, bound iteration/time resources, and record infeasibility/timeout and deterministic fallback. Hardware/fault constraints take precedence; the trade between driver longitudinal request and yaw correction must be explicit. Never use an unconstrained allocation and hide infeasibility by clipping only the plot.

Tire-load/grip estimates used by the controller must be separated from true simulated loads. Run truth-assisted diagnostics and sensor/estimator-based controller tests under distinct labels. Use yaw integrator anti-windup and feasible reference saturation when those states exist. Leave gains and control frequency as versioned synthetic choices until reviewed with team evidence.

## 7. Fixed-clock runner

Use integer simulation ticks or an equivalently exact schedule representation for declared sample periods. Record their time base. Do not accumulate floating-point time in a way that unpredictably adds or drops controller calls.

At a logical controller tick:

1. Apply scheduled sensor arrivals and construct the causal snapshot available at that tick, including injected delay/noise/bias/validity.
2. Call the selected controller backend once with its explicit state, logical time and demand.
3. Validate and stage the returned command, including sequence/session identity and final guard.
4. Hold the accepted command while the plant advances to the next event using its own verified substep limits; evolve actual actuator state on that plant clock.
5. Record decisions, constraints and state at specified observation points without changing integration.

Specify event ordering when a sample, reset and control tick coincide. RK4 trial stages may evaluate forces repeatedly; they must not advance the controller or randomly resample a sensor. Seed random scenarios once and store the seed/algorithm. Where noninteger rate ratios are supported, use a deterministic event queue.

Realize Python reference and native C through the same logical adapter. A host C build is software-in-the-loop, not STM32 execution. Compare state-machine reasons/latches exactly where the contract requires it; predeclare numeric tolerances per quantity/platform. Bitwise equality is a separate stronger contract and must not be assumed across compilers/targets.

## 8. Minimum scenario matrix

All scenarios are synthetic until paired with authorized measured data. Freeze scenario/configuration before tuning and preserve failing cases.

| ID | Scenario | Required observations |
|---|---|---|
| TC-S01 | Standstill and bounded straight pedal ramp | Total request, realized acceleration, low-speed slip handling and actuator limits |
| TC-S02 | Symmetric fixed steer / corner exit | Inner/outer kinematics, yaw response and driver-demand tracking |
| TC-S03 | Mirrored S02 | Mirrored signed lateral/yaw quantities and swapped wheels within declared tolerance |
| TC-S04 | Split-grip straight and turn | Wheel slip, force/torque redistribution and unchanged shared power budget |
| TC-S05 | One actuator unavailable or constrained | Topology-aware allocation, unmet demand and no command to disabled channels |
| TC-S06 | High-speed motor cutoff / pack power limit | Feasible torque-speed/power behavior, finite state and active limit |
| TC-S07 | Near-empty/full battery; regeneration transition | Charge-budget handling, no hidden SOC overrun and explicit braking policy |
| TC-S08 | Pedal overlap / invalid input / stale sensor | Exact declared inhibition, retained raw proposal, latch/recovery and finite diagnostics |
| TC-S09 | Delayed/lost/duplicate/out-of-order messages and target restart | No stale command reuse, explicit epoch/clock handling, bounded failure |
| TC-S10 | Plant-step and controller-period sweeps | Separate numerical sensitivity from controller sampling sensitivity |
| TC-S11 | UI/logging-rate change | Identical control-event sequence and physics under the determinism contract |
| TC-S12 | Reference/native/emulator/PIL common fixture | Actual backend identities, matching logical inputs and scoped comparison evidence |

## 9. Metrics, comparison fairness and UI

Report longitudinal-demand error/residual, yaw-reference error when supported, peak/integrated slip under its regularization, torque slew, saturating duration, inhibition/recovery transitions, energy and completion status. Report runtime and deadline metrics separately from physical metrics. Do not choose arbitrary real-car accuracy targets from professional-racing claims.

A/B runs share model, car/topology, initial state, course/road, sensor realization/seed, pedal/steering program, limits, integration settings and controller period; change only the declared strategy or gain. If a closed-loop driver is also changed, label that as a different experiment. Equal elapsed time does not guarantee equal driver demand or equal energy budget.

The existing UI should show a scenario selector and backend badge, bounded controls, selected model/topology, provenance, paired plots and exportable records. A moving car rendering follows actual recorded `X,Y,psi`. The replay viewer remains a data presentation path unless it actually executes a backend; never conflate a JSON import with controller execution.

Done means the scenario runs and its assertions/results are inspectable. More screenshots, AI-generated research or node counts are not substitutes for these tests.
