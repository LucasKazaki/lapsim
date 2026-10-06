# Four-wheel dynamics experiment

The desktop **Four-wheel lab** is a small, synthetic torque-allocation model
based on the independent-wheel force balances in the supplied ENME408 EV
simulation and torque-control research report (Report I), sections 5–9.
Wind and flat-road grip inputs follow the separate *Aerodynamics, CFD, Track
Conditions, and Secondary Effects* report (Report II), sections 3, 7, 8, and
12. Both reports are design and audit sources; their example values are not
measured vehicle data. This module is separate from the prescribed-course
endurance solver.

## States and axes

The ten states are world position `X,Y`, counterclockwise heading `ψ`, body
forward and left velocity `u,v`, counterclockwise yaw rate `r`, and four wheel
angular speeds in front-left, front-right, rear-left, rear-right order. Body
`+x` is forward; body `+y` is left. At wheel position `(xᵢ,yᵢ)`, the body-frame
contact velocity is `(u−r yᵢ, v+r xᵢ)`. It is rotated through the commanded
steering angle to find the longitudinal and lateral velocity in the wheel
frame. Wheel-frame tire forces are rotated back to body axes before summing:

```text
m (du/dt − r v) = Σ Fx,tire,body + Fx,external + Fx,aero
m (dv/dt + r u) = Σ Fy,tire,body + Fy,external + Fy,aero
Iz dr/dt          = Σ (xᵢ Fy,body − yᵢ Fx,body) + Mz,external
Jᵢ dωᵢ/dt        = Tdrive,ᵢ − Tbrake,ᵢ − R Fx,wheel,ᵢ
```

The tire law uses a regularized longitudinal slip ratio and lateral slip
angle. Linear small-slip forces are scaled together when their combined
magnitude exceeds `μ Fz`. The default `Fz` comes from static axle loads;
callers may supply per-wheel loads, including zero for a wheel out of
contact. The current law is for forward driving; reverse behavior is
qualitative and has not been validated. Wheel inertia is integrated in four
separate states, so it is not also added to vehicle mass.

The model integrates with fourth-order Runge–Kutta. Its internal step limit
is derived from the fastest linearized wheel-slip mode, even when the user
chooses a coarser output interval. A time-step comparison and a low-speed
stiffness regression are included in the focused checks. The lab's default
one-second, one-degree-steer maneuver is intentionally short: a long open-loop
steering command can spin the synthetic car and is not a driver controller.

## Wind and road conditions

`PlanarEnvironment` supplies constant world-frame wind components, air
density, a drag area `CdA`, and a `PlanarRoad`. The default `drag_area_m2=0`
disables aerodynamic force exactly; wind defaults to zero. For heading `ψ`,
world ground velocity `vG`, world wind `w`, and body rotation `R(ψ)`, the model
uses

```text
Ubody = R(ψ)^T (vG − w) = (u, v) − R(ψ)^T w
Faero,body = −0.5 ρ CdA |Ubody| Ubody
Paero,vehicle = Faero,body · (u, v)
```

The last line uses **ground velocity**, because it is power delivered to the
vehicle. It need not equal aerodynamic force dotted with air-relative
velocity in wind. This drag force acts at the center of gravity; the current
model has no aerodynamic yaw or pitch moment, downforce, ride-height map, or
measured crosswind coefficient. Density does not scale electric-motor torque.
The main prescribed-course lap solver still uses its separate scalar aero
model and is not changed by these lab inputs.

At each force evaluation, including intermediate Runge–Kutta stages, wheel
`i` queries a fixed road at its **world** contact-center position:

```text
pwheel,i = (X, Y) + R(ψ) (xᵢ, yᵢ)
|Ftire,i| ≤ μbase × road_multiplier(pwheel,i) × Fz,i
```

`PlanarRoad` defaults to uniform reference pavement. Optional
`RectangularGripPatch` entries are axis-aligned in world coordinates and
return a material ID and peak-friction multiplier; the first matching patch
owns a shared boundary. A patch changes the combined tire force cap only,
not the tire stiffness, contact geometry, or normal load. It represents a
synthetic sensitivity case, not a measured wet-tire law. The flat road has
no height, slope, banking, roughness, vertical contact dynamics, or suspension
motion.

`RoadDomain` can bound where the assumed road data apply. An out-of-domain
query is marked invalid and uses base pavement grip solely so the trajectory
can be inspected. `run_planar_dynamics(..., environment=...)` returns
`PlanarRun.road_valid=False` if **any** accepted, final, or intermediate
force query left that domain. `invalid_road_queries` counts wheel-query calls,
not seconds outside the domain. `step_planar_dynamics(...)` raises
`ValueError` instead of returning an unmarked state; `PlanarSimulator.step`
retains cumulative status on its wrapper. Runs with invalid road queries are
diagnostic; they must not enter an unqualified A/B ranking. Force evaluations
and road queries are pure and deterministic, so numerical substeps do not
alter the environment.

## Reading the result

Both scenarios start from the same state and car parameters. The default A
and B examples request 240 Nm in total at the two rear wheels, allocated
120/120 and 110/130 Nm respectively. Equal total torque can be required so
the comparison isolates the left/right allocation. Wheel torque requests are
not clipped by a motor, battery, traction controller, or brake actuator.

The path and yaw plots use the same time axis as the four slip traces. The
time cursor selects an instantaneous car state and displays the matching
wheel slip, local longitudinal force, and normal load. The run also exposes
an instantaneous mechanical-power residual to catch sign or force-balance
mistakes. Its external-power term includes wind-aware aerodynamic work once.
A small equation residual alone does not validate the tire law. Paired A/B
comparisons should use the same environment and initial state.

## Scope before use with a team car

Replace the synthetic mass, inertia, geometry, tire stiffness, friction,
wheel inertia, and contact-load assumptions with reviewed 2026–27 values.
Then add tire/load-transfer measurements, motor and battery limits, steering
and braking actuators, controller timing, and telemetry comparisons. The
current lab supports equation-level experiments; it does not predict a
Formula SAE endurance time or a production Prius's torque-vectoring behavior.
