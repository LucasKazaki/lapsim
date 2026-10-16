# TC-01B — kinematic electronic differential baseline

Accessed 2026-10-02. Target remains the 2027–28 Terps Racing EV torque-control project.

## Decision

Add a kinematic electronic-differential reference before any yaw-moment torque-vectoring controller.

TC-01A allocates a nonnegative torque request among four available wheels under wheel torque limits, but it does not encode the geometric fact that independently driven wheels follow different path radii in a turn. TC-01B fills that gap without inventing Terps Racing wheelbase, track, tire radius, steering mapping, motor/inverter limits, CAN interfaces, or tire behavior.

This is a separate layer from:
- traction control, which limits drive torque from longitudinal-slip evidence; and
- yaw-moment torque vectoring, which deliberately creates left/right longitudinal-force differences to change yaw response.

TC-01B requests no yaw moment and no torque split. It only computes no-slip geometric wheel path/speed references.

## Research boundary

Julio-Rodríguez, Santana-Díaz, and Ramirez-Mendoza describe an electronic differential for independently driven EV wheels that coordinates different inner/outer wheel speeds during turning. Their vehicle-specific experimental results are not transferred here.

- “Individual Drive-Wheel Energy Management for Rear-Traction Electric Vehicles with In-Wheel Motors,” Applied Sciences 11(10):4679, published 20 May 2021, DOI 10.3390/app11104679, CC BY 4.0.
  https://www.mdpi.com/2076-3417/11/10/4679

Barman's 2024 IEEE Potentials overview gives the standard Ackermann/Jeantand side-speed relation and explicitly notes that static steering geometry is useful for quasi-static/low-speed cornering but does not capture centripetal-force/tire effects.

- P. Barman, “Electronic differential: A vital component of electric vehicles,” IEEE Potentials, Jan./Feb. 2024, DOI 10.1109/MPOT.2023.3280338.
  https://read.nxtbook.com/ieee/potentials/potentials_jan_feb_2024/electronic_differential.html

For the later torque-vectoring layer, Sun, Lee, and Tian's Formula SAE paper uses an upper direct-yaw-moment controller and lower torque-distribution controller.

- Y. Sun, R. Lee, G. Tian, “Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE Racing Car,” SAE 2021-01-0373, published 6 Apr 2021, DOI 10.4271/2021-01-0373.
  https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373

A 2023 Formula SAE modeling study also supports calibrating the vehicle model against measured telemetry before making 4WD performance claims.

- “Performance Prediction of a 4WD High-Performance Electric Vehicle Using a Model-Based Torque-Vectoring Approach,” World Electric Vehicle Journal 14(7):183, published 13 Jul 2023, DOI 10.3390/wevj14070183.
  https://www.mdpi.com/2032-6653/14/7/183

## Portable geometry

Definitions:
- L: wheelbase
- t_f: front track
- t_r: rear track
- r_w: effective rolling radius
- delta: bicycle-equivalent front steering angle; positive means left turn
- v: speed at the rear-axle midpoint

For nonzero ideal steering:

R = L / tan(|delta|)
|yaw_rate| = v / R

For a left turn:
- rear-left radius: R - t_r/2
- rear-right radius: R + t_r/2
- front-left radius: sqrt((R - t_f/2)^2 + L^2)
- front-right radius: sqrt((R + t_f/2)^2 + L^2)

A right turn swaps inner/outer sides.

Each wheel path speed is v_i = |yaw_rate| R_i and each ideal wheel angular speed is omega_i = v_i / r_w.

These are instantaneous-center-of-rotation equations. They do not model tire slip, compliance, understeer, load transfer, motor dynamics, inverter limits, road friction, regen, or transients.

## Frozen synthetic scenario

The portable handoff uses explicitly synthetic values:
- L = 1.6 m
- t_f = t_r = 1.2 m
- r_w = 0.23 m
- v = 8.0 m/s at the rear-axle midpoint
- equivalent steer = +15 deg
- duration = 2.0 s

The reference gives a centerline turn radius of about 5.9713 m. Rear-left path speed is about 7.1962 m/s and rear-right path speed about 8.8038 m/s. If all wheels were instead assigned the same 8.0 m/s path speed for the two-second segment, the largest geometric path-distance mismatch in this four-wheel fixture is about 2.1221 m.

Those numbers demonstrate geometry only. They are not Terps Racing measurements and do not imply tire force, energy loss, torque, safety, or lap-time change.

## Portable verification

Standard-library-only Python:
- python -S -m unittest -v test_kinematic_ediff.py
- python -S -m py_compile kinematic_ediff.py test_kinematic_ediff.py

Observed in the external handoff:
- 43/43 tests passed, 0 failed, 0 skipped
- py_compile exit 0
- kinematic_ediff.py SHA-256: 0d6ef2c33e98d6ff64d22d87f953065d93f82034cf25a24192971d58324ea387
- test_kinematic_ediff.py SHA-256: bcc9e0e5fdb0c47a09530a4fb529106fb20ed8c0d2b4ea425ab755e997ae30da

Coverage includes straight-line equality, left/right symmetry, inner/outer speed ordering, Ackermann front-angle ordering, path-radius derivation, wheel-radius conversion, zero-speed behavior, steering singularity, invalid geometry, NaN/Inf, near-straight handling, equal-speed counterexample behavior, speed/steer scaling, unequal tracks, deterministic JSON, and explicit zero yaw-moment/traction/action authority.

No STM32 build, motor/inverter model, CAN traffic, HIL, dyno, track test, flashing, or vehicle actuation occurred.

## Integration boundary

Do not directly turn these speed ratios into wheel torque commands. A source-specific controller would still need actual steering/wheel-speed signals, timing, effective wheel radii, motor/inverter control mode, tire-slip policy, fault behavior, and reviewed interaction with driver request and independent safety systems.

TC-01A remains the conservative torque-allocation baseline. TC-01B is a separate geometry reference.

## Next source-specific action

When team data exists, bind:
1. wheelbase;
2. front/rear track;
3. effective rolling-radius definition and uncertainty;
4. steering measurement and conversion to equivalent angle;
5. steering sign/range;
6. wheel-speed units, signs, timestamps and freshness;
7. whether each motor interface is speed-, torque-, or otherwise controlled.

Then replay measured low-speed steady turns against the kinematic ratios before tuning any yaw-moment controller.

No production firmware change, flashing, CAN transmission, vehicle actuation, or safety-system change is authorized.
