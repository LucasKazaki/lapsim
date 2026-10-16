# TC-01A — conservative torque allocator and deterministic replay

Status: portable reference only. Parent plan commit: `254b7453ea2802f7d17e6758a52419de0dded110`. Target car context remains 2027-28 and all vehicle interfaces remain unverified.

## Decision

Keep the first executable baseline simpler than traction control or torque vectoring. The reference allocator accepts a synthetic total positive propulsive torque request, four per-wheel positive limits, wheel-enable flags, an input timestamp, an external interlock, and an explicit torque unit. It equally shares the request across available wheels and deterministically redistributes only the unserved amount from a saturated or disabled wheel.

This baseline is not a yaw controller, traction/slip controller, regenerative-braking controller, CAN implementation, vehicle-dynamics model, or safety system. It exists so later algorithms have a reproducible lower bound and fail-closed interface checks.

Sun, Lee, and Tian (SAE 2021-01-0373) describe a Formula SAE distributed-drive architecture with an upper direct-yaw-moment controller and a lower torque-distribution controller. That supports keeping the low-level constrained allocation contract distinct from the later yaw objective. Their vehicle parameters and performance results are not transferred to Terps Racing. A 2023 Formula SAE EV modeling study in World Electric Vehicle Journal evaluates torque-vectoring benefits only after calibrating a vehicle model from telemetry, which reinforces not inventing Terps Racing tire, mass, geometry, or actuator parameters here.

## Reference contract

Inputs are a nonnegative synthetic torque request in `N*m`, four finite nonnegative wheel limits, four wheel-enable flags, timestamps, and an external interlock. Negative torque is rejected rather than interpreted as regeneration. Future-dated or stale critical input fails closed. An open interlock fails closed.

Outputs are four finite nonnegative commands. No output exceeds its supplied wheel limit; disabled wheels stay at zero; aggregate saturation is explicit; and identical ordered inputs reproduce identical outputs. The 50 ms stale-input threshold in the test fixture is synthetic only, not a Terps Racing sample-rate requirement or FSAE rule.

## Portable verification

Sandbox: Python 3.13.5 on Linux 6.18.44 x86_64, standard library only.

Commands:

```text
python -m unittest discover -s projects/enme408-torque-control/reference -p "test_*.py" -v
python -m py_compile projects/enme408-torque-control/reference/allocator.py projects/enme408-torque-control/reference/test_allocator.py
```

Observed: 14 tests passed, 0 failed, 0 skipped; `py_compile` exited 0. Tested SHA-256: allocator `78e3ab41f06c1e504ba0519a4b1a7b60a6ff27a7598ccc38e7edd76916b4c960`; tests `f7fc68668d5a184e91d956be3c98dd960ac8d59de8c85f77e1a5e8bd4117aa51`.

Coverage includes equal allocation, disabled-wheel redistribution, per-wheel and aggregate saturation, stale/future timestamps, open interlock, NaN/Inf, negative request, wrong torque unit, invalid wheel limits, no available wheels, zero request, and deterministic replay. These are synthetic tests, not STM32 timing, CAN, HIL, vehicle, or rules-compliance evidence.

## TC-00 gaps before vehicle-specific work

Still required: exact motor/inverter count and identities; command representation, units/signs/limits/timeouts; real CAN messages and ownership; pedal/brake arbitration; wheel-speed/steering/IMU availability and timestamps; shutdown/watchdog ownership; exact STM32F405 part/package, board wiring, clock/firmware/build environment; logging and bench/HIL access; approved sample periods and failure requirements.

The STM32 family documentation is relevant to later embedded feasibility, but it does not prove which peripherals or clocks this custom PCB uses.

## Keep/revert rule

Keep this baseline only while it remains a stateless deterministic reference with no vehicle-specific claims. Split or revert any future change that adds yaw/slip objectives, regeneration, real CAN identifiers, team calibrations, or safety authority without separate evidence and review.

## Next bounded task

TC-01B: add a small JSON scenario format and CLI replay/report tool that validates these invariants and emits machine-readable status/fault results. Keep all values synthetic until TC-00 receives team interface evidence.
