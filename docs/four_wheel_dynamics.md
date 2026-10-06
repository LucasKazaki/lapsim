# Four-wheel dynamics experiment

The desktop **Four-wheel lab** is a small, synthetic torque-allocation model
based on the independent-wheel force balances in the supplied ENME408 EV
simulation and torque-control research report, sections 5–9. The report is a
design and audit source; its proposed capabilities are not treated as
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
m (du/dt − r v) = Σ Fx,body + Fx,external
m (dv/dt + r u) = Σ Fy,body + Fy,external
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
mistakes. A small equation residual alone does not validate the tire law.

## Scope before use with a team car

Replace the synthetic mass, inertia, geometry, tire stiffness, friction,
wheel inertia, and contact-load assumptions with reviewed 2026–27 values.
Then add tire/load-transfer measurements, motor and battery limits, steering
and braking actuators, controller timing, and telemetry comparisons. The
current lab supports equation-level experiments; it does not predict a
Formula SAE endurance time or a production Prius's torque-vectoring behavior.
