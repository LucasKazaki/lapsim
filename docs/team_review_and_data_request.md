# Team review and focused data request

16 October 2026. For E13 in [the work plan](../ENME408_IMPLEMENTATION_PLAN.md). **No new team/Slack information has been received.** This is the next request/review agenda, not a claim that the listed data exist or have been approved.

## 1. What to demonstrate

Show a source-identified build and declare its capability level before showing results. Use a coherent public synthetic course rather than ranking the fused course's unvalidated racing-line result.

| Demonstration | Ask the team |
|---|---|
| Architecture/source map and current-car schematic | Does this represent the system? Who owns each interface? What is wrong or still provisional? |
| One repeatable synthetic basic run and its saved configuration | Are units, controls, plots and export useful? Can another person repeat it on their computer? |
| Bicycle versus independent-wheel model selection, once implemented | Are the different model capabilities clear? Which comparison matters first? |
| Equal-total-request four-wheel baseline/candidate, with actual constraints once integrated | Which actuators are independent? Is the first objective wheelspin control, corner-exit predictability or yaw response? |
| Native replay or later real closed-loop run, clearly distinguished | Are inhibit, input freshness, recovery and command-rate policies consistent with the intended interface? |

Do not present a viewer replay as a running controller, a synthetic yaw improvement as a lap-time gain, an ARM object as firmware execution, or a partial TREV profile as a complete current-car calibration.

## 2. Minimum useful data package

Ask for **one approved configuration, its signal definitions and one complete logged test with metadata**. Review the existing source registry as approved/superseded/unknown instead of requiring people to recreate every known parameter.

| Owner role to identify | Request | What it enables |
|---|---|---|
| Vehicle/dynamics lead | Car/revision identity; measured mass and driver/load condition; axle/corner weights; wheelbase/tracks; tire and loaded radius; CG/inertia estimates with uncertainty | Reproducible baseline, load/force model and yaw dynamics |
| Powertrain lead | Motor/inverter count and independently commandable channels; differential/topology; gearing; torque units/sign; torque-speed and generating limits; measured feedback semantics | Feasible allocation and correct motor/wheel conversion |
| Battery lead | Pack/cell configuration/capacity; power/current/voltage limits; SOC/temperature charge acceptance; available OCV/resistance/derating data | Energy, discharge and regenerative feasibility |
| Controls/electronics lead | Exact STM32 part and PCB revision; schematic/power/connector info; current firmware/build tooling; available probe and UART/USB; scheduler/watchdog ownership | Non-guessed bench firmware and safe isolated connection |
| Software/DAQ lead | DBC/signal dictionary, firmware revision, units/scales/axes, clocks/timestamps, sample rates, validity/freshness and loss behavior | Correct decoding, alignment and causal controller input |
| Tires/suspension/brakes lead | Permitted tire data/fits with load/camber/pressure/temperature/domain; steering ratio/mapping; front/rear brake pressure-to-torque relation and deadbands | Slip, yaw, braking and combined-force correlation |
| Testing lead | Original log plus decoded export; maneuver description; vehicle/firmware revision; driver/load; initial SOC/temperatures; tire pressures; weather/surface and sensor faults | First measured-versus-simulated test and later independent evaluation |
| Track/data owner, later | Coherent coordinates/station/heading/curvature/frame plus measured boundaries and their provenance | Defensible full-path/lap comparisons |

For every parameter retain value, unit, configuration/revision, owner, source, date, evidence status and uncertainty/range. A design nominal is not an as-built measurement. A source bundle's TREV designation does not by itself prove a model year.

Desired logged channels, only where available: driver pedal(s), brake pressure/demand, steering with reference frame, wheel/motor speeds, IMU acceleration/yaw, torque command/feedback, pack voltage/current/SOC and faults/enable state. Request raw/native-rate channels before downsampling; a low-rate exported trace does not establish controller latency. Preserve raw evidence and transformation/alignment history.

## 3. Decisions needed, even before detailed measurements

Confirm the first controller objective and what the software team will review. Confirm the current RWD actuation topology rather than assuming independently driven rear wheels. For future AWD, record known versus undecided architecture without filling it from a vendor's product options.

Agree on command authority: who turns pedal demand into total request, who owns final inhibition, how limits arrive, which clock defines freshness, which component owns recovery, and what interface version is expected. Do not select thresholds/update rates as real requirements without their owner/source.

Ask who can review the synthetic assumptions and who can approve a disconnected STM32 bench. Do not request a vehicle-driving test as the first hardware milestone.

## 4. Intake and privacy

Keep authorized private measurements outside the public repo through the existing `LAPSIM_DATA_BUNDLE` mechanism. Store public synthetic fixtures and schema examples here. Public manifests should use safe relative identifiers or hashes rather than revealing local personal paths/private URLs.

Reserve independent maneuvers or chronological holdout data before fitting. Record fitting, alignment and preprocessing decisions; do not tune on the same dataset and describe the result as independent prediction. Report missing channels and sensor uncertainty, not invented acceptance percentages.

## 5. Suggested message to the team

> I have a working simulation/replay foundation and a detailed plan to consolidate the controller and simulator into one easy-to-run repository. The current examples are synthetic, so I would like a review of the drivetrain/control interfaces and agreement on the first torque-control objective. The most useful next input is one approved car configuration, its signal definitions/DBC and one complete logged test with vehicle/firmware/test metadata. Please mark existing parameters as approved, superseded or unknown rather than re-entering everything. I also need the STM32 PCB/connector and current firmware details before connecting a board to the simulator. Private or restricted data can stay in the team's approved storage; the public demo will not require them.

This draft has not been sent. Update its capability wording to match the exact demonstrated build.
