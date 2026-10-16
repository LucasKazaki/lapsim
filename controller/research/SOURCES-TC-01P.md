# SOURCES-TC-01P — aggregate DC-power budget for the portable torque allocator

Accessed 2026-10-06.

## Current ENME408 repository state

Repository: `LucasKazaki/lucas-agent-studio`
Research branch: `research/enme408-tc00-20261001`
Head before this write attempt:
`6efeb73f57215f83415b2ed133e18d50142a1c7e`

- branch is 93 commits ahead / 0 behind `ops/school-focus-20260930`;
- merge base is `254b7453ea2802f7d17e6758a52419de0dded110`;
- current allocator blob:
  `7d1f14489bb92604de015871a7f4c3011774ab38`;
- current TC-01N source blob:
  `53877b2c23d833fa0b995207f6d35d083eb0ad9d`.

TC-01P wraps the current branch allocator directly.

## Formula SAE current resources

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

At access, `2027 Formula SAE Rules` is listed as Version `V1`.

Official Formula SAE Electric 2027 registration:
https://www.fsaeonline.com/cdsweb/reg/CompAttendance.aspx?CompetitionID=14b1f772-0ac9-4eef-a96e-cd02a076097d

No competition-wide accumulator power, current, voltage, motor-count,
inverter-count or torque limit is inferred by TC-01P.

## Hard power constraints in EV energy management

"Optimal Power Allocation in Battery/Supercapacitor Electric Vehicles Using
Convex Optimization," IEEE Transactions on Vehicular Technology, 2020.
https://ieeexplore.ieee.org/document/9193947/

The paper enforces hard power-output constraints in an EV energy-storage
allocation problem. TC-01P uses this only to support treating shared source power
as a constraint distinct from individual wheel-torque limits.

## Energy-aware multi-motor control allocation

"Adaptive Energy-Efficient Control Allocation for Planar Motion Control of
Over-Actuated Electric Ground Vehicles," IEEE Transactions on Control Systems
Technology, 2014.
https://ieeexplore.ieee.org/document/6674064/

The low-level allocation incorporates motor-efficiency functions and actuator
input constraints. TC-01P does not reproduce that optimizer.

## Current STM32F405 context

STMicroelectronics STM32F405OG:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405og.html

Current ST information identifies Cortex-M4/FPU operation up to 168 MHz and
includes general-purpose DMA and two CAN 2.0B interfaces. TC-01P makes no native
timing or firmware-acceptance claim.

## Portable model

Forward propulsion only:

`P_wheel_candidate = sum(tau_i * omega_i)`

`P_wheel_budget = eta_dc_to_wheel * P_dc_available`

If the candidate exceeds the budget:

`alpha = P_wheel_budget / P_wheel_candidate`

`tau_i_final = alpha * tau_i`

The common scale preserves the base allocator's wheel-to-wheel torque ratios.
It is a deterministic reference policy, not an energy-optimal controller.

Unproven constraints remain separate: actual accumulator voltage/current/SOC
power limit, inverter current, thermal derating, efficiency maps, tire/slip,
regen, and actual driven-channel architecture.
