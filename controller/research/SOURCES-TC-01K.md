# SOURCES-TC-01K — finite-scenario LLTD uncertainty and robust yaw feasibility

Accessed 2026-10-05.

## Clover and Bernard — lateral load-transfer distribution matters

Chris L. Clover, James E. Bernard,
"The Influence of Lateral Load Transfer Distribution on Directional Response,"
SAE Technical Paper 930763, published 1993-03-01.
DOI: 10.4271/930763
https://saemobilus.sae.org/papers/influence-lateral-load-transfer-distribution-directional-response-930763

Primary-source abstract:
- lateral load transfer occurs in directional maneuvers;
- front/rear lateral load-transfer distribution depends on roll stiffness and
  suspension geometry;
- the distribution has significant implications for directional response and
  can affect limit behavior.

Applicability:
This supports treating LLTD as a source-backed vehicle property rather than a
hidden 50/50 constant. TC-01K does not transfer the paper's vehicle parameters.

## Sun, Lee, Tian — Formula SAE hierarchical torque vectoring

Yiwen Sun, Runfeng Lee, Guangyu Tian,
"Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE
Racing Car," SAE Technical Paper 2021-01-0373, published 2021-04-06.
DOI: 10.4271/2021-01-0373
https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373

Primary-source abstract:
- two-layer architecture with an upper direct-yaw-moment controller and lower
  torque-distribution controller;
- lower controller estimates wheel vertical load through lateral acceleration;
- lower controller selects torque distribution using tire-friction-ellipse
  lateral-force margin.

Applicability:
TC-01K remains a lower-layer feasibility screen. It does not generate a yaw
target or claim controller performance.

## Serralvo Neto et al. — calibrated Formula SAE 4WD model

Rafael Serralvo Neto et al.,
"Performance Prediction of a 4WD High-Performance Electric Vehicle Using a
Model-Based Torque-Vectoring Approach," World Electric Vehicle Journal 14(7),
183, published 2023-07-13.
DOI: 10.3390/wevj14070183
https://www.mdpi.com/2032-6653/14/7/183

Primary-source applicability:
- the study calibrates a Formula SAE vehicle model against instrumented 2WD
  telemetry before predicting 4WD behavior;
- dynamic wheel-load estimation is part of the model used for tire-potential
  and torque-vectoring analysis.

Applicability:
This reinforces that TC-01K's synthetic scenario set is not vehicle validation.
Team data or measured/high-fidelity validation is still required.

## Rajamani et al. — torque-biasing feasibility has operating limits

R. Rajamani et al.,
"On the Use of Torque-Biasing Systems for Electronic Stability Control:
Limitations and Possibilities," IEEE Transactions on Control Systems Technology,
15(3), 581-589, published 2007-05-31.
DOI: 10.1109/TCST.2007.894656
https://ieeexplore.ieee.org/abstract/document/4162493

Primary-source abstract:
- hierarchical control separates desired yaw-moment generation from lower
  torque biasing;
- the desired transfer of longitudinal tire force cannot always be achieved by
  torque biasing;
- achievable yaw-moment behavior depends on operating condition.

Applicability:
This supports explicitly checking yaw-moment feasibility before treating an
upper-layer yaw request as realizable. TC-01K's finite-scenario intersection is
a conservative portable design choice, not an algorithm claimed by this paper.

## Formula SAE

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing at access:
- `2027 Formula SAE Rules` — Version `V1`.

TC-01K derives no LLTD range, friction coefficient, lateral utilization,
geometry, torque limit, yaw target, sample period, or safety threshold from the
rules listing.

## Mathematical design boundary

For each explicit LLTD scenario, TC-01K:
1. computes quasi-static normal loads from the same narrow accounting model used
   in the external TC-01J handoff;
2. applies an idealized friction-circle reserve
   `Fx_reserve = mu * Fz * sqrt(1 - u_lat^2)`, where `u_lat` is a
   caller-supplied lateral-utilization ratio;
3. converts that reserve to wheel torque with rolling radius and intersects it
   with an actuator torque cap;
4. computes exact minimum/maximum yaw moment for a fixed positive total-torque
   request under those independent wheel caps.

The finite-set robust interval is:
- lower bound = maximum of all scenario lower bounds;
- upper bound = minimum of all scenario upper bounds.

This is exact over the listed discrete scenario set only. It is not a proof for
every continuous LLTD value between listed points.

The idealized friction circle and fixed lateral-utilization ratios are screening
assumptions, not a validated tire model. No tire load sensitivity, combined-slip
nonlinearity, transient suspension, aero generation, motor speed/current/power
envelope, CAN behavior, or safety authority is represented.
