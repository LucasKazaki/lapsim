# Research-to-LapSim development roadmap

Prepared 11 October 2026 against repository commit `67b3659a4d9dcf88a7074fb52b526f19d9aee30b`.

This is a proposed engineering backlog, not a claim that the changes below have been implemented or physically validated. The research upload is documentation-only. Re-read the current source and tests before implementation; this snapshot can become stale.

Sources are indexed in [F1](f1_teams_and_telemetry.md), [additional professional programs](additional_professional_teams.md), and the [prior 50-source catalogue](formula_racing_research_catalogue_2026-10-10.md). The machine-readable task list is [backlog.json](backlog.json).

## 1. Start from what this repository already has

The following was established from the live README, architecture documentation, four-wheel documentation, source-profile documentation, and the beginning of the tyre implementation. These are repository observations, not independent validation of their physical accuracy.

| Existing capability | Inspected evidence | Consequence for future work |
|---|---|---|
| Common endurance/acceleration/skidpad facade and component-based vehicle | [Architecture](../../architecture.md), `src/vehicle_model/vehicle.py` | Extend component interfaces; do not replace the whole event API. |
| Distance-domain main simulation with internally calculated elapsed time | [Architecture](../../architecture.md) | Do not run a real controller once per distance cell and call that a fixed-frequency control loop. |
| Component-owned namespaced telemetry and NaN backfill | [Architecture](../../architecture.md), `src/lapsim/core/` | Add metadata/validation without breaking optional channel extensibility. |
| Recorded-control replay and event analysis | [Event simulation](../../event_simulation.md), `src/lapsim/data/`, `analysis/` | Reuse these paths; do not build a competing recorder/replayer by default. |
| OCV/SOC/one-RC battery and existing battery validation reports | [Battery model](../../battery_model.md), [RC validation](../../battery_rc_validation.md) | Extend known state/limit boundaries rather than introducing a disconnected battery estimate. |
| Provenance-aware external vehicle profiles | [Source profiles](../../source_vehicle_profiles.md) | Retain unknown/null values, explicit selections and inherited defaults. Keep the evidence bundle private. |
| Four-corner load-sensitive tyre model and opt-in Pacejka implementations | `src/vehicle_model/mech/tire.py` | Do not claim the project has no combined-force or Pacejka work. Validate fit scale and operating domain before enabling another law. |
| Separate ten-state planar model, four wheel-speed states, RK4 and wheel-slip-based internal step limit | [Four-wheel experiment](../../four_wheel_dynamics.md) | Preserve existing wheel inertia and stiffness/time-step checks; avoid double-counting inertia. |
| Planar torque requests not constrained by motor/battery/controller/brake actuator | [Four-wheel experiment](../../four_wheel_dynamics.md) | This is a direct limitation for comparing realizable EV torque-control strategies. |
| Planar static-load baseline; no downforce/ride-height map or vertical road dynamics | [Four-wheel experiment](../../four_wheel_dynamics.md) | Do not imply four-wheel trajectories already have the main solver's entire component model. |
| Course provenance, replay records and optional grid-sensitivity checks | Root README, [course bundles](../../course_bundle_format.md) | Improve validation of these features rather than recommending they be created from nothing. |

The main distance-domain model and separate transient planar experiment have different state and fidelity assumptions. A shared interface does not require identical integration coordinates or identical state vectors. Their results should only be cross-compared on deliberately matched, supported cases.

## 2. Recommended order and decision gates

**First:** R01 metadata/quality contract, R02 feasible actuator envelope and R03 correlation harness. Work on R05 tyre/load identification in parallel as authorized data become available.

**Then:** R04 fixed-clock software-in-the-loop, R06 braking/regeneration and R07 energy/thermal experiments.

**Later:** R08 aero/road validity, R09 hardware-in-the-loop, and R10 driver/experiment interfaces. Work packages can overlap, but their acceptance dependencies must remain visible. This ordering is a recommendation, not a commitment to dates or available team hardware.

### R01. Add a signal metadata and quality layer

**Motivation:** HRC's synchronized channels/cameras; F1 live/full-log separation; Waterloo's raw/decoded workflow. Sources N01-N02, F01-F04, S39.

**Where:** `src/lapsim/core/`, `src/lapsim/data/`, the existing profile/manifest and run-record interfaces. Confirm concrete file names before editing.

**Deliverable:** an optional metadata registry alongside existing namespaced scalar channels. Record unit, axis/sign convention, clock domain, sample timestamp, source identity, measurement/estimate/simulation class, validity, and transformation provenance. Decoding a raw log should not destroy the raw record. A derived channel should identify its dependencies and algorithm version.

**Acceptance:**
- Existing components can still add optional channels and retain NaN backfill.
- A synthetic import/export/replay round trip preserves units, timestamps and validity; known zeros remain distinct from unknown values.
- Missing, duplicate, non-monotonic, stale and out-of-order samples are flagged or handled by an explicit tested policy.
- Alignment offsets are stored. No blanket interpolation silently fills long outages or categorical fault states.
- Metadata do not expose private source paths, measurements or credentials in public fixtures.

### R02. Constrain the transient model with feasible actuator limits

**Motivation:** Genesis hybrid/brake validation, Bosch subsystem boundaries, and the current planar model's unrestricted torque inputs. Sources N04, N19; repository four-wheel documentation.

**Where:** `src/vehicle_model/interfaces.py`, `powertrain/drivetrain.py`, `powertrain/motor.py`, `electrical/inverter.py`, `electrical/battery.py`, and the planar model behind the four-wheel lab. Inspect its actual path rather than assuming a new package.

**Deliverable:** a shared feasible-command evaluation that reports requested, limited and achieved motor/wheel torque plus the active limitation. Account for motor speed, gear/differential topology, inverter limits, pack terminal constraints and actuator rate/delay where parameters are supported. Keep provisional limits explicitly labeled.

**Acceptance:**
- Equal left/right commands preserve expected symmetry on a symmetric test; swapping left/right and mirroring the maneuver produces the mirrored result within a declared numerical tolerance.
- A torque request outside the envelope cannot create unbounded power or bypass the battery model.
- Motor-side and wheel-side torque/rate units and ratios are tested in both power directions.
- Wheel and rotor inertia are accounted for once, with state ownership documented.
- Existing idealized planar experiments remain available only as explicitly unconstrained reference cases, not silently renamed production controller results.
- All A/B controller runs share initial state, vehicle, road, energy/power limits and numerical settings.

### R03. Build a reusable prediction-versus-measurement report

**Motivation:** Cadillac's pre/post-event correlation and the broader F1 validation loop. Sources N03, F39; existing battery/replay analyses.

**Where:** `analysis/`, `src/lapsim/data/`, existing validation reports and saved manifests.

**Deliverable:** a common report for time- and distance-aligned comparisons of supported channels. Include speed, acceleration, wheel behavior, yaw, electrical power/energy, SOC and temperature where actually measured. Report missing channels rather than inventing them.

**Acceptance:**
- Preserve pre-test predictions and raw evidence; calibration produces a new version rather than rewriting history.
- Split fitting and evaluation chronologically or by independent maneuvers/conditions. Prevent holdout leakage through preprocessing or parameter selection.
- Plot residuals, bias, relevant norms and alignment sensitivity. Tolerances come from sensor uncertainty and the intended decision, not an arbitrary professional-team percentage.
- Separate numerical grid/time-step sensitivity from measurement uncertainty and parameter uncertainty.
- A matching lap time alone cannot pass validation when channel-level discrepancies remain unexplained.
- Comparisons clearly distinguish replaying recorded controls from validating a closed-loop driver or torque controller.

### R04. Add a deterministic fixed-clock SIL adapter

**Motivation:** PREMA HIL and Mahindra's reuse of models/real controls. Sources S08, S31; F03.

**Where:** an adapter around the transient plant and a separately testable controller core. Keep event APIs and the distance-domain solver intact.

**Deliverable:** a controller interface receiving a timestamped sensor snapshot and returning actuator requests. Use an explicit controller clock, sample-and-hold behavior, sensor schedules and latency. Plant substeps may differ from controller periods. The STM32-targeted core should also run in desktop tests with a hardware-abstraction boundary.

**Acceptance:**
- Identical inputs, initial state and random seeds produce reproducible traces within a documented determinism contract.
- Changing logging/UI frequency does not change controller execution times or plant results.
- Plant-step refinement and controller-period changes are separate experiments.
- Inject sensor noise/bias, dropouts, stale packets, delayed commands and implausible readings; verify specified diagnostic/degraded behavior.
- Do not choose a control period merely because an online example used it. Establish target timing from the actual controller and I/O requirements.
- No LLM or network service is required in the hard-real-time control path.

### R05. Establish tyre and load validity envelopes

**Motivation:** Haas tyre science, HRC private tyre models, authorized TTC measurements and CTU control research. Sources F25, N01-N02, S46, S48.

**Where:** `src/vehicle_model/mech/tire.py`, existing Pacejka modules, `suspension.py`, `loads.py`, and profile metadata.

**Deliverable:** reviewed fits/maps with units, source, tyre identity, pressure, load, camber, temperature/test condition, fit method and valid ranges. Adapt common tire evaluation where appropriate without pretending the spatial and planar models have identical assumptions.

**Acceptance:**
- Test zero/low load, zero slip, combined slip, limiting friction and symmetry/sign conventions.
- Preserve the current opt-in distinction until absolute force scale and domain are validated.
- Flag extrapolation and zero-contact cases; no silent negative loads or physically impossible force capacity.
- Fit and validate on separate evidence; report residuals across load/slip, not only one lap.
- Restricted TTC data and private team measurements stay outside Git; use synthetic fixtures for public tests.
- Do not infer wet-grip, temperature or wear laws from a single uniform grip multiplier.

### R06. Coordinate regeneration and mechanical braking

**Motivation:** Formula E and LMDh hybrid/braking workflows. Sources S27-S31, N04, N19.

**Where:** `powertrain/drivetrain.py`, `electrical/battery.py`, `electrical/inverter.py`, `mech/brakes.py`, tyre interfaces and transient actuator evaluation.

**Deliverable:** braking-demand allocation subject to machine capability, battery charge acceptance, traction, topology and mechanical brake limits. Track requested braking, regenerative contribution, mechanical contribution and unmet demand separately. Confirm applicable Formula SAE rules before treating a control mode as permitted.

**Acceptance:**
- A full/high-voltage or otherwise charge-limited battery reduces allowed regeneration according to the modeled constraint.
- Remaining demand is handled by a defined mechanical-brake policy; diagnostics disclose unmet demand rather than creating force.
- Use consistent signs: positive pack-terminal power means discharge; charging is negative. Auxiliary loads and conversion losses are counted once.
- Pure regeneration, pure friction, transition, low-speed and loss-of-regen tests have energy accounting and stability checks.
- The plant cannot claim independent wheel authority that the physical motor/differential layout does not provide.

### R07. Add energy/thermal scenario studies with justified complexity

**Motivation:** Porsche component-to-system simulation, Penske/AVL energy studies, Canopy and TUM research. Sources S27-S29, S35-S36, S43-S44.

**Where:** existing battery/motor/inverter components, `src/lapsim/optimization/`, endurance event reporting.

**Deliverable:** replaceable loss/thermal models with source-backed maps where available and explicit low-fidelity baselines otherwise. Compare pace under a common energy budget and energy use at a common pace. Retain ambient/initial thermal and SOC conditions.

**Acceptance:**
- Power and energy balances close to an error budget justified by numerical convergence and model boundaries.
- Include pack-terminal versus stored-energy distinctions and polarization/loss state consistently.
- A cooling/derating study states its assumed parameters and validity; an unknown thermal coefficient is not converted into a confident number.
- Optimization cannot exploit unsupported extrapolation, negative losses or inconsistent timestep updates.
- Publish the speed/energy tradeoff and feasibility failures, not only the fastest selected run.

### R08. Improve aero/road representations only with traceable geometry

**Motivation:** HRC track fidelity, CFD/tunnel correlation and metrology. Sources N02, F16, F32, N23.

**Where:** `src/vehicle_model/aero/model.py`, `environment.py`, `src/lapsim/courses/`, course-bundle and planar-road adapters.

**Deliverable:** validity-aware aero maps and richer road geometry when supported by measurements. Preserve reference area, force axes, signs, center-of-pressure assumptions, mapping frames and uncertainty. Keep synthetic wind/grip rectangles labeled as sensitivity scenarios.

**Acceptance:**
- Graphics and physics share a provenance-tracked geometry source or a tested explicit transformation.
- Vehicle ground speed and air-relative speed are not confused in aerodynamic work/energy accounting.
- Downforce, force application point and moments are included once with consistent units.
- Out-of-domain road/map queries propagate invalid status to comparisons.
- A scalar corridor certificate is not presented as surveyed cone clearance or swept-body containment.
- Do not infer a water-film, aquaplaning or suspension/roughness model from a visual road texture.

### R09. Add physical STM32/CAN HIL after SIL passes

**Motivation:** PREMA, Mahindra and Toyota HIL examples. Sources S08, S31, N06.

**Dependency:** R01, R02, R04 and relevant braking/fault specifications.

**Deliverable:** connect the real controller to a real-time-capable simulated plant through the approved I/O boundary. Measure timestamping, end-to-end latency, jitter, deadline misses and recovery; preserve hardware/firmware/DBC versions. Use a safe isolated bench before any energized vehicle integration.

**Acceptance:**
- Verify real CAN IDs, scaling, counters, validity and freshness against the team's reviewed interface; do not invent a production DBC from research examples.
- Record deadlines and failures rather than assuming a desktop process is hard real time.
- Repeat baseline/fault scenarios from SIL and explain discrepancies caused by hardware and timing.
- Run power-up/shutdown, communication interruption, invalid input and watchdog tests according to the agreed safety design.
- A passed HIL test does not authorize deployment to a moving vehicle without the team's safety review and controlled validation plan.

### R10. Add a driver/experiment interface without forking the physics

**Motivation:** Rodin, Nissan, HRC, McLaren Hypercar and Jaguar's automated tests. Sources S10, S25-S26, N01, N05.

**Dependency:** a defensible model/actuator/timing boundary and repeatable analysis.

**Deliverable:** an interactive driver adapter and experiment browser using the existing component contracts and telemetry. Automate parameter sweeps first; add cockpit/motion hardware only for identified human-response questions.

**Acceptance:**
- Presentation-frame rate does not determine integration or controller rate.
- Driver inputs, alarms, commands, results and video markers are synchronized and replayable.
- Compare paired configurations with identical external conditions, blind labels where useful, and a recorded subjective feedback protocol.
- A driver preference is reported separately from objective speed/energy improvement.
- Report model version, limits and whether the run is synthetic, calibrated, measured replay or closed-loop simulation in the interface.

## 3. Data and ownership decisions required from the team

Before treating any controller study as representative of the planned car, confirm independently commandable motors/differentials; torque-speed and electrical limits; pack topology and charge acceptance; brake architecture; sensor locations/axes/calibration; CAN/interface ownership; steering geometry; mass/CG/inertia; tyre identity and authorized data; and applicable rules/safety requirements.

The source-profile system already supports unknown values and explicit selections. Keep unsupported future-car parameters unknown or scenario-labeled. A TREV designation in the external evidence bundle does not, by itself, establish a model year or released vehicle configuration.

## 4. Handoff instructions for the next implementation session

Read this roadmap, the research index, the current architecture and four-wheel documentation, then inspect the current source and tests. Choose one work package and confirm which pieces already exist. State the physical question and acceptance criteria before editing. Preserve existing interfaces, defaults, validation evidence and public/private data boundaries. Add synthetic unit/regression tests and an inspectable example. Do not silently introduce professional-team parameters, copy restricted datasets, change the default tyre fit, or report a synthetic test as measured validation. Record the code commit, parameter and track revisions, assumptions and unresolved limits in the resulting report.

A documentation upload does not implement R01-R10. Track implementation and measured validation separately.
