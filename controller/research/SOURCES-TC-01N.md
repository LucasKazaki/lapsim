# SOURCES-TC-01N — speed-dependent motor torque/power envelope

Accessed 2026-10-06.

## Formula SAE current resources

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

At access:
- `2027 Formula SAE Rules` is listed as Version `V1`.

Applicability:
TC-01N does not use a competition-wide power value or infer any team motor,
inverter, battery, or gearing limit from the rules. The ruleset version is
recorded only to keep the U.S. Formula SAE Electric context current.

## Formula SAE distributed-drive torque vectoring

Yiwen Sun, Runfeng Lee, Guangyu Tian,
"Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE
Racing Car,"
SAE Technical Paper 2021-01-0373, published 2021-04-06.
https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373

Primary-source abstract observations:
- the studied Formula SAE car uses a two-layer torque-vectoring architecture;
- the lower layer distributes torque subject to a vehicle/motor model;
- tire, suspension, motor and aerodynamic parameters are measured or identified
  for the modeled vehicle.

Applicability:
This supports keeping real motor and vehicle parameters source-backed rather than
using generic placeholders as production limits. TC-01N does not reproduce the
paper's controller.

## Motor constraints as functions of operating point

S. Yun, K. Yi, S. Cheon, Y. Yoon,
"Development of a Motor Torque Distribution Strategy of Six-wheel-Driven
Electric Vehicles for Optimized Energy Consumption,"
SAE Technical Paper 2013-01-1746, published 2013-04-08.
https://saemobilus.sae.org/papers/development-a-motor-torque-distribution-strategy-six-wheel-driven-electric-vehicles-optimized-energy-consumption-2013-01-1746

Primary-source abstract observations:
- torque distribution depends on driving-motor characteristics and performance
  constraints;
- motor efficiency depends on motor speed and operating torque;
- maximum motor torque is a function of motor speed.

Applicability:
TC-01N implements only a minimal speed-dependent torque/power envelope. It is
not an efficiency optimizer and does not infer a real motor map.

## 4WD EV torque allocation under actuator constraints

J. Kang, K. Yi, H. Heo,
"Control Allocation based Optimal Torque Vectoring for 4WD Electric Vehicle,"
SAE Technical Paper 2012-01-0246, published 2012-04-16.
https://saemobilus.sae.org/papers/control-allocation-based-optimal-torque-vectoring-4wd-electric-vehicle-2012-01-0246

Primary-source abstract observation:
the allocation maps desired traction force/yaw moment to actuators while taking
actuator constraints into account.

Applicability:
TC-01N is one possible source of a dynamic actuator bound for the existing
portable equal-allocation reference. It does not implement optimal yaw control
or slip control.

## Current STM32F405 context

STMicroelectronics STM32F405/415:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415.html

Current ST page states:
- Arm Cortex-M4 with single-precision FPU;
- up to 168 MHz;
- up to 192 Kbytes SRAM;
- two CAN interfaces.

Applicability:
The portable arithmetic is small enough to be a plausible embedded candidate,
but TC-01N makes no execution-time, memory, CAN-load, or native firmware
acceptance claim. Those require the actual team build and board receipt.

## Mathematical envelope used by TC-01N

Forward propulsive scenario only:

`omega_motor = reduction_ratio * omega_wheel`

For `omega_motor > 0`:

`tau_motor_power = P_motor_max / omega_motor`

`tau_motor_limit = min(tau_motor_max, tau_motor_power)`

`tau_wheel_limit = efficiency * reduction_ratio * tau_motor_limit`

At zero speed the power cap is treated as non-binding and the motor torque cap
applies.

If the modeled motor-speed limit is exceeded, the portable channel returns zero
propulsive torque and an `motor_overspeed` status.

These equations are elementary mechanical-power relationships. Real inverter
current, DC-bus voltage, battery power, temperature, motor-efficiency map,
traction and regen constraints are separate and remain unproven.
