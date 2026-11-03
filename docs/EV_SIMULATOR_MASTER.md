# EV simulator and torque-control research master

**Research status, 3 November 2026.** The immediate objective is a usable light
simulator and an evidence-backed, standing-start AWD technique comparison, one
course at a time. A reliable completion estimate requires measuring a full
standing lap and actual throughput. The detailed/full simulator is a separate
backend whose qualification must be established independently; shared
interfaces do not make the two implementations or results interchangeable.

This document is a source-and-results index. A technique, numerical value or
result is labeled **implemented**, **qualified**, **executed**, **provisional**
or **planned** according to its evidence. A source review alone is not a test,
and synthetic results are not a vehicle or safety validation.

## 1. Current state and target configuration

The tournament target is a simulated AWD car with four independently
commanded motors. Four independent drives do not imply four-wheel
steering. The working configuration uses front steering and provisional motor,
tire, aero, brake and battery assumptions; neither motor authority nor the
parameters are confirmed as the built car. A [June 2026 UMD article](https://cmns.umd.edu/news-events/news/terps-racing-ev-formula-sae-electric-competition-2026)
describes a single-motor car and a planned move to four motors. It is historical
context, not proof of the current build's final configuration.

The seven-policy AWD source registry contains equal torque, load-based
distribution, slip-target limiting, steering feedforward, yaw PI, combined
yaw/slip, and an energy-oriented neutral allocation. In the reviewed standing
source snapshot, these are **source-supported, regen-off provisional entries**;
the registry marks native qualification and campaign eligibility as unrun or
false. Implemented source is not the same as a completed tournament. Regen
recipes remain excluded pending the low-speed motor-lag, battery acceptance and
brake-blending qualification. Additional energy strategies are research ideas
until individually implemented and tested.

The latest independently audited standing-start AWD **development** record reaches
9.000 simulated seconds, 43.917 m of source-track progress and 3.168 Wh net
battery depletion, with **zero completed laps**. The published values are
rounded for display; internal evidence retains full precision. These are
partial-segment values, not lap time, competitive pace, official points or
a tournament comparison. A separate flying-start development lap is historical
and cannot serve as the standing-start baseline. Earlier RWD campaigns stay
historical and cannot be relabeled AWD.

A separate producer and verifier process passed the saved development
continuation audit. That verification is not an independent physics
implementation. Startup-environment equivalence to the original checkpoint
and exact initial guard samples of the older producer remain unproved;
the lineage is therefore development-only. The source registry's qualification
flags have not been promoted from this partial record.

The latest isolated operational repair binds a worker log reader's post-join
error and closure state through the inner, root and caller receipts. Its
75 qualification cases and five added regression definitions are **unrun**.
The latest process-ownership preflight was denied before process creation
because automatic review retained a source-only/runtime-probe restriction.
No qualification, lease acquisition or numerical run followed that denial.
Current global process and lease availability is unknown. Expired/retired
allocations are closed and cannot be reused.

This publication is a reviewed source-and-research snapshot, not a release of
a qualified interactive simulator. The archive below does not ship private
execution receipts, machine-specific supervisors or an admitted racing-line
bundle. It must not be used to bypass the original resource or execution
approval gates. See [the light snapshot](../research/light/README.md) and the
separate [full-simulator comparison](full-simulator/comparison-spec.md).

## 2. Physics and software boundaries

The active light development path is Python on the CPU. It evolves a planar
vehicle state with position, heading, body velocities, yaw and four wheel
speeds. A path-following driver observes geometry and state, a controller
proposes wheel torques, actuator/electrical and tire constraints limit them,
and the plant updates motion and battery energy. Aero drag and downforce,
load transfer, an automatic DRS state and a lumped common tire-temperature
state are model components with provisional parameters. Separate controller,
plant, thermal, logging and display clocks must stay explicit. The supported
GPU search in historical experiments is a different physics family; it is not
evidence that this coupled AWD light plant runs on the GPU.

The existing repository also contains other prescribed-path, four-wheel,
native and virtual-controller studies. Keep each backend's state, units,
topology, actuator assumptions, source identity and qualification separate.
Share a versioned course/line, configuration, controller-interface and result
contract where the backends actually implement and validate the same meaning;
do not replace the lite backend silently or infer full-model parity.

Detailed repository starting points at the inspected public `main` commit are
the [model parameter reference](https://github.com/LucasKazaki/lapsim/blob/feed2e37f8114ec2a3ed836a8ab780d22078da91/docs/model_parameters.md),
[source vehicle profiles](https://github.com/LucasKazaki/lapsim/blob/feed2e37f8114ec2a3ed836a8ab780d22078da91/docs/source_vehicle_profiles.md),
[closed-loop lab](https://github.com/LucasKazaki/lapsim/blob/feed2e37f8114ec2a3ed836a8ab780d22078da91/docs/closed_loop_lab.md),
[controller source guide](https://github.com/LucasKazaki/lapsim/blob/feed2e37f8114ec2a3ed836a8ab780d22078da91/docs/controller_source.md),
and [simulator research](https://github.com/LucasKazaki/lapsim/blob/feed2e37f8114ec2a3ed836a8ab780d22078da91/docs/simulator_research.md).
Those documents describe their own versions; they do not certify the newer
isolated AWD candidate. Source identities and evidence must be preserved when a
candidate is integrated.

## 3. Tires, loads and thermal modeling

Tire-force estimation needs documented longitudinal/lateral slip, normal load,
combined-force limits, pressure, temperature, camber and their valid domains.
The light candidate's synthetic limits and common lumped thermal sensitivity
are development assumptions, not measured behavior of four individual tires.
Changes to a tire curve or load model require continuity, domain, combined-slip,
energy and step-size tests, plus independent validation against appropriately
licensed data. Never tune coefficients solely to manufacture a preferred policy
result or match an unrelated leaderboard.

The repository's parameter guide describes an opt-in public UPC R20 example and
notes that parts of its longitudinal/combined-slip fit originate from another
model. It is an example with provenance and limitations, not confirmation that
the team uses that tire. Confirm the actual tire, dimensions, operating ranges
and approved data before adopting it. Do not put private Formula SAE Tire Test
Consortium files, derived confidential coefficients, raw team telemetry or
unauthorized supplier material into this public-repository draft.

## 4. Course and racing line

The active development course is a map-derived FSI approximation, not surveyed
event limits. Its widths, car clearance and tracking-error margins need source
and uncertainty records. The currently used candidate line was not proven
optimal; continuous swept-footprint clearance and real-car dynamic feasibility
remain open. Record the source track, paired bounds, vehicle-width and safety
margins, line geometry/hash, curvature, speed assumptions and validation status.

The public [TUM trajectory-planning helpers](https://github.com/TUMFTM/trajectory_planning_helpers)
offer minimum-curvature and iterative-QP building blocks. Minimum curvature is
a candidate heuristic, not a guaranteed minimum-time solution. A safe adapter
requires paired track widths/normals, a closed-loop join, consistent optimized
arc length and curvature, footprint clearance, tracking error and dynamic
feasibility. Preserve the centerline baseline; freeze one admitted racing line
for the first matched torque-policy screen. Per-policy line optimization is a
separate development experiment and must not consume held-out selection data.
No optimizer package installation or solver run is implied by this document.

The archived current candidate uses its separately named, bounded SciPy/SLSQP
producer rather than TUM IQP. A permitted nonconverged iterate still requires
every declared geometric screen; it is not a converged optimum or dynamically
qualified racing line. Its private producer receipt bundle is not shipped in
the public source archive, so the archived bridge is not a runnable release.

## 5. Fair technique screening and scoring

For the first course, use one verified standing-start lap per implemented and
qualified technique with identical course/line, car, driver, environment,
state and brake authority. Freeze the scientific and controller versions,
limits, timestamps, conditions, failure rules and energy boundary in each run.
Record requested, proposed, limited and achieved torques; wheel slip, loads,
yaw, intervention counts, lap crossings, time and net battery depletion.
If a controller never activates or a model-domain limit is exceeded, report
that fact. Equal outcomes can be legitimate; do not force a gap or score a
failed trajectory as a slow finish.

Screen techniques before genetic tuning. Select a predeclared short list only
after required development coverage, keep held-out data untouched until the
final selection, and report uncertainty and terminal state. Full-nine-course
or GA completion cannot be inferred from a single development lap.

The [2026 SAE rules reference](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=7de1794b-82d2-4ccd-ad4d-92fd2745bb89)
and event materials distinguish endurance time/completion from efficiency; the
historical maximum is 275 endurance points and 100 efficiency points, not a
simple linear time/energy weighting. Official scoring depends on the selected
edition, finish/driver-change eligibility, penalties, energy definition and a
frozen reference field. One simulated lap is not automatically official
endurance or efficiency points. If those inputs are absent, show time and energy
with points **pending**, or use a clearly labeled, separately defined proxy.

The separate 2026 rules review identified a 250-point time component plus up to
25 completion points, and an efficiency calculation using pace and CO2 per lap
relative to a reference field. It reports an electric conversion factor of
0.65 kg CO2/kWh and credit for regenerative energy, and an event meter that
integrates measured voltage and current. These are research notes for a future
version-pinned scoring implementation, not a completed scoring implementation.
Confirm D.13 and EV.3.2 against the applicable official edition, event
supplements and meter data before using them. Do not substitute an endpoint
kinetic-energy adjustment for the official measured energy.

SAE [announced the published 2027 rules](https://www.fsaeonline.com/cdsweb/app/NewsItem.aspx?NewsItemID=219f84d4-72a6-4672-9125-7f69d790ae3a)
on 15 September 2026. A separate rules research review verified specific clauses
in the official [2027 V1 rules](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38):
IN.16.2.3 permits powertrain parameter and software-calibration changes after
inspection approval; IN.16.1 restricts pre-approval changes; and changes
outside permitted limits may void approval and require reinspection. The
review also identified EV.3.1.3's restriction on increasing total driver
requested torque, the 80 kW and 600 V limits, and the prohibition on
regeneration from 0 to 5 km/h. These are specific clause findings, not a
blanket permission to install new firmware or new control logic.

The **2027 endurance and efficiency scoring formulas have not been verified**
for this implementation; do not carry the 2026 formulas above forward by
assumption. Confirm exact definitions, measurement and the applicable event
supplements before implementing rules or claiming compliance. Event-specific
endurance, autocross, acceleration and skidpad maps remain **planned**. The
unsupported low-speed regen transition remains a model and actuator-authority
question; the rule review does not establish that it is fixed.

## 6. Official 2026 benchmark context

The supplied [2026 Formula SAE Electric Michigan results](https://www.fsaeonline.com/CompResources/2026/07af50d8-cbb6-4b9b-aaf8-5ff6a7e44057/FSAE_2026_MI6_results.pdf)
are 2026 results. Its first page lists the top five **overall** teams as Oregon
State (895.5), Rochester Institute of Technology (856.7), Pittsburgh (807.2),
Carnegie Mellon (756.9) and Connecticut (756.8). Overall results include other
events; they are not the same ordering as endurance or efficiency alone.

The endurance table lists six leading classified finishers at 1,312.281-
1,442.381 seconds adjusted over 22 laps. The efficiency table lists Pittsburgh
at 3.263 kWh and 100 efficiency points over 22 laps. `Energy Used` is kWh;
the separate `Adjusted Energy (kg)` column is not vehicle mass. Some
nonfinishers may be efficiency-eligible under the applicable rules, so check
driver-change and official eligibility rather than applying an invented blanket
rule. The [SAE scales guidance](https://www.fsaeonline.com/Page.aspx?pageid=5bb75247-0771-4dff-8c1d-a8be19370191)
describes prepared vehicle mass without a driver and weight-balance measurements
with a driver; the PDF appendix is explicitly unvalidated and starred entries
have additional caveats.

As broad context, a separate extraction found the top quarter of eligible
timed entries at 3.697-3.948 s for acceleration, 4.782-5.088 s for skidpad,
and 43.937-45.809 s for autocross. These are event-specific times, not a single
vehicle's performance. UMD's listed results are 4.188 s, 5.445 s and 50.647 s
respectively; its endurance entry is a DNF after five laps, with no energy row.
The unvalidated appendix lists UMD at 208.7 kg, one motor and 450 V; driver
inclusion is not established by that row.

For several 22-lap entries, the separate extraction pairs the following **raw**
endurance times with the official `Energy Used` values. Do not compare these
raw times to adjusted standings without adding the reported penalties.

| Team | Raw endurance time (s) | Energy used (kWh) |
| --- | ---: | ---: |
| Oregon State | 1,308.281 | 5.302 |
| Cal Poly SLO | 1,392.927 | 4.669 |
| Kookmin | 1,412.029 | 5.203 |
| RIT | 1,415.128 | 4.749 |
| Pittsburgh | 1,434.223 | 3.263 |

Use these results to identify plausible orders of magnitude only after matching
event distance, layout, start, car/driver mass, penalties, completion and meter
boundary. The flying-start development lap and the real endurance event are not matched.
Audit initial/terminal kinetic energy, accessory/inverter/motor losses, regen,
drag and rolling work, state of charge and gross versus net energy before
interpreting the current power difference. Do not fit the model to the table.
The five official raw-time/energy pairs above imply roughly 8.190-14.590 kW
mean electrical power over the reported duration. Their distance, layout,
start, car, conditions and meter boundary are not matched to the simulator,
so they are an audit prompt, not proof that a particular coefficient is wrong.

## 7. Usability and roadmap

- Complete a qualified local Run/progress/Stop/Close path and a truthful replay;
  record which interactions have actually been tested in a browser or desktop
  window. A saved-results viewer is not evidence that an interactive Run works.
- Export precise machine-readable results and a human-readable table of time,
  net energy, points or an explicit unscorable reason, coverage and failures.
  Display values to three decimals while retaining full internal precision;
  flag differences below display resolution.
- Add a replay G-G plot with clearly defined longitudinal/lateral acceleration,
  units and frame. Show separate steering command, tire heading, vehicle-body
  heading and velocity direction; do not label all arrows simply "steering."
- Preserve line, car, source, controller, rule edition, evidence and failure
  identities in each replay. Avoid claiming calibration or a winner before
  applicable coverage, verified scoring and convergence evidence.
- Consider research on controlled simulation and noisy measurements,
  four-motor yaw allocation and energy/thermal management, preserving the
  assumptions of each study. Examples include the [Oregon State project](https://projects.engineering.oregonstate.edu/projects/?id=GMVCjfIJkNCIQcHN),
  [UC Irvine thesis](https://escholarship.org/uc/item/7997f1xq),
  [Politecnico di Torino thesis](https://webthesis.biblio.polito.it/12157/),
  and [energy/thermal controller paper](https://arxiv.org/abs/2412.15379).
  [Carnegie Mellon Racing's PiDAQ](https://github.com/carnegiemellonracing/PiDAQ)
  is a historical 2024/2025 data-acquisition reference, not evidence of a 2026
  race controller. These are research ideas or historical studies, not proof of
  any team's 2026 race configuration. Public funding does not by itself make
  technical data open.

## 8. Provenance boundary

The links above identify public sources and the repository versions they
describe. A published research paper or public race result does not license
private tire data, team telemetry, supplier files, or another contributor's
work. Preserve each source's attribution and rights, and use separately
authorized data for calibration or vehicle validation.
