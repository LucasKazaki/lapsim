# TC-01AC | Wheel-speed interval mechanical-power screen

Access/analysis date: **2026-10-14**. Research-only for a **hypothetical four-channel 2027–28 U.S. Formula SAE Electric** drivetrain. Not the 2026–27 team vehicle, not an STM32 firmware change, and not authority to actuate anything.

## Decision

**Keep as a portable TC-01 dependency experiment, not an accepted torque-control requirement.** TC-01P's current aggregate-power reference at PR #66 evaluates wheel power from one snapshot of wheel speeds. If torque persists while speed rises, the snapshot computation cannot establish the upper power demand over that interval. A speed interval `[observed, upper]` can provide a conditional mechanical-power screen: for nonnegative torques and nonnegative speeds, `sum(torque_i * speed_i) <= sum(torque_i * upper_i)` for every speed within the interval. The intervals must be independently justified by sensors, actual timing, and a dynamics or measurement bound. This pass **does not create or certify those bounds**.

## Frozen synthetic counterexample

Four wheel channels each request 100 N·m; the observed wheel speeds are 20 rad/s. Point-sampled mechanical power is 4 × 100 × 20 = **8,000 W**, below a **hypothetical** 9,000 W wheel-mechanical budget. Under an unverified ceiling of 25 rad/s per wheel, upper mechanical power is 4 × 100 × 25 = **10,000 W**. The reference's common torque scale is approximately 0.9, giving approximately 90 N·m per wheel. Its independently tested negative control deliberately mistakes the observed snapshot for a guaranteed hold-interval maximum and fails as expected.

The actual 2027–28 motor count, speeds, torque limits, inertia/acceleration envelope, command-hold time, message latency, inverter current behavior, and CAN timing are **unknown**. This reference never estimates DC-side demand, thermal limits, transient currents, voltage headroom, tire adhesion, regeneration or shutdown effectiveness. A wheel-mechanical budget is assumed for illustration and is not SAE compliance evidence.

## Relationship to existing reference

- Current PR #66: `research/enme408-tc00-20261001` head `e765585f157321af770de3199ac7563139650e34` as inspected 2026-10-14; `projects/enme408-torque-control/reference/aggregate_power_budget.py` blob `dfc336f099101d71e897374543f3ba8268a39a29`. That module uses a snapshot of four wheel speeds, a constant scenario conversion of DC power to mechanical wheel power, and a common torque factor. **It was not executed in this pass.**
- Frozen TC-01AB predecessor archive verified separately: **119 selected tests pass** in CPython 3.13.5, and two intentionally defective negative controls fail by design. Those tests are not from the current GitHub checkout.
- New isolated TC-01AC Python reference uses a **wheel-mechanical** budget in watts and does not conflate the result with battery DC power. The reference is not a patch to the existing allocator and has no vehicle command authority.
- The tighter speed interval is monotonic: widening ceilings cannot increase the permitted common torque factor, conditional on the stated model. This is not a proven practical bound because no team-certified ceiling or delay is available.

## Acceptance / reject rule

Keep this as documentation/simulation until an independent controls-team reviewer establishes the source of bounds and tests whether the speed ceiling actually envelopes observed motion over real command delivery/hold intervals. Reject using it as a deployed safety/power constraint without those receipts. Any integrated implementation must preserve independent shutdown/watchdog ownership, real CAN timing, and motor/inverter limits.

## Backlog (dependency order)

1. TC-00: Verify drivetrain channel count, sensor path/units/signs, power-budget definition, latency/hold period, clock synchronization, and source of credible angular-speed ceilings from authorized team data.
2. TC-01: Reproduce the interval counterexample on the exact authorized GitHub checkout; compare with snapshot baseline and add a source-specific failing test. Review before modifying the existing module.
3. TC-02: Build a synthetic missed-deadline/late-message scenario; show explicit `bound_invalid` rather than silently trusting an expired ceiling.
4. TC-03: Independent controls-team review and actual STM32/bus measurement receipts before bench planning. No vehicle work authorized by this pass.

## Sources and applicability

See `SOURCES-TC-01AC.md`. Equations and numeric scenarios in this note are self-contained derivations, **not assertions from ST/SAE or measurements**.
