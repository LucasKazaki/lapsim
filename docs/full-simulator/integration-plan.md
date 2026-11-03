# Full EV simulator: source-backed integration plan

Date: 2026-11-03. Status: design and literature assessment. The comparative
mechanics and CFD fixtures described here are **proposed and untested**; no
new simulation or numerical benchmark was run for this plan.

## Decision and existing capability

Start the detailed mechanics track with **Chrono::Vehicle**, because an actual
optional adapter and historical Windows native evidence already exist. Evaluate
**MuJoCo** against it on a shared synthetic mechanics fixture before investing
in a second vehicle adapter. For air, keep the CFD solve offline and compare
**OpenFOAM Foundation** and **SU2** on a shared analytical fluid fixture before
selecting either for a car map. Investigate **FluidX3D** only as a later
GPU/lattice-Boltzmann candidate, subject to its license, tool availability,
resource admission and the same verification standard. This is a prioritization,
not a benchmark ranking.

At public main snapshot `feed2e37f8114ec2a3ed836a8ab780d22078da91`,
the project's `src/lapsim/dynamics/native_plant.py` defines explicit plant
ownership, SI units, a right-handed X-forward/Y-left/Z-up world frame, FL/FR/
RL/RR wheel order and independent observation clocks. The adjacent
`chrono_vehicle.py` instantiates a headless CPU Chrono 10 synthetic sedan with
double-wishbone axles, Pac02 tires, shaft-clutch brakes and a rear driveshaft
through an open differential. `suspension_study.py` already owns the separate
plant, controller and logging clocks. It uses a normalized steering request and
one held driveshaft torque; it is **not** an independent-wheel EV controller,
battery, motor, regenerative-braking system, or CFD plant. Its force cache has
a separate source timestamp and is applied with a one-plant-step delay. No
fast-model, electrical or controller force is automatically coupled into it.

The project's historical [native study](../chrono_suspension_study.md)
and [evidence register](../research/chrono_backend.md)
report earlier real CPU runs on a synthetic passenger-sized fixture, including
an example gravity-load and plant-step comparison. Those are historical tests
of the named sources, not a current run, a Formula-car calibration, or a real
lap-time prediction. The source records instantaneous normal-speed Pac02 slip,
a separate low-speed tire clock, limited tire coefficients, rigid chassis and
links, flat road and no aerodynamic forces. A tire model name or a more complex
engine does not establish accurate tire forces.

The ordinary distance-domain vehicle uses per-cell, quasi-static component
models; the separate four-wheel time-domain experiment has planar state and
air-relative wind. Neither solves a 3-D fluid field. The project handoff names
six-component CFD maps, ride-height feedback, vertical road/contact dynamics,
and temperature-dependent limits as future work requiring data. More track
distance cells, more CFD volume cells, and a shorter dynamics time step are
three different refinements; one cannot substitute for the others.

## Candidate comparison

| Candidate | Useful capability | Material limits / decision |
| --- | --- | --- |
| [Chrono::Vehicle 10 tire models](https://api.projectchrono.org/10.0.0/wheeled_tire.html), [suspension subsystem](https://api.projectchrono.org/10.0.0/group__vehicle__wheeled__suspension.html) | Vehicle-specific multibody suspensions and rigid, handling and finite-element tire families. Existing source and historical Windows receipt make it the lowest-integration-risk mechanics starting point. | The installed project's Pac02 implementation and assets have narrower behavior than a generic manual description. FEA tire availability in upstream documentation does not prove the local Python build supports it, nor provide a fitted tire. Keep exact binary/asset identity and per-wheel force clocks. |
| [MuJoCo](https://mujoco.readthedocs.io/en/stable/computation/index.html), [extension interface](https://mujoco.readthedocs.io/en/stable/programming/extension.html) | General multibody, joints, actuators and soft contact; an independent engine for a small controlled comparison. | A generic contact model does not supply a calibrated racing tire, a differential or the existing vehicle assembly. Equivalent suspension, wheel and tire forces would require explicit adapters, parameter matching and verification. Its repository states Apache-2.0; record the exact selected release and dependency notices. Availability on this PC is unknown. |
| [OpenFOAM Foundation](https://openfoam.org/download/), [v13 snappyHexMesh source](https://cpp.openfoam.org/v13/snappyHexMesh_8C_source.html) | Finite-volume CFD, meshing and a broad external-aero workflow; useful candidate for moving-ground and geometry studies after verification. | Foundation and OpenCFD releases are distinct distributions; pin one and check its actual solver and boundary-condition syntax. Foundation v14's documented Windows route is WSL, whose process lifetime and accounting cannot be assumed to follow a Windows Job Object. GPLv3 and redistribution need review. Presence on this PC is unknown. |
| [SU2](https://github.com/su2code/SU2), [incompressible RANS example](https://su2code.github.io/tutorials/Inc_Turbulent_NACA0012/), [periodic-flow options](https://su2code.github.io/tutorials/Inc_Streamwise_Periodic/) | Incompressible/compressible CFD and an independent comparison; published periodic and airfoil examples supply well-described starting points. | A different discretization and setup may produce different results even with the same mesh. The repository identifies LGPL-2.1; pin release, build and dependencies. The cited tutorial versions do not prove a local installation. |
| [FluidX3D](https://github.com/ProjectPhysX/FluidX3D), [license](https://github.com/ProjectPhysX/FluidX3D/blob/master/LICENSE.md) | Lattice-Boltzmann candidate using OpenCL, relevant to future high-cell-count GPU experiments. | Its own current license is source-available and non-commercial, not an open-source license; use and redistribution conditions must be assessed for this project. No speed, memory, calibration or hardware-compatibility claim is made. It is not in the first benchmark budget. |

The linked mesher source is Foundation v13 and illustrates a capability, not a
claim about installed v14. No tool above should be installed on the strength of
this plan. Choose concrete versions after an environment inventory and review
of any installation that becomes necessary.

## Data record: 2025 observations

The 2025 as-built car and the proposed four-independent-motor AWD fixture are
separate configuration identities. Public benchmark appendix entries are
unvalidated; private photo-derived observations are omitted from this public
plan. No unverified photo description establishes current motor topology,
steering, brakes, tire parameters or calibration.

Request from the team, when available and with appropriate data permissions: versioned
CAD and coordinate convention; wheelbase/tracks/CG and sprung/unsprung masses
and inertias; suspension hardpoints, spring/damper curves and measured travel;
verified steering geometry; tire identity and authorized force/combined-slip
test data; driveline BOM/topology, motor, gear/chain ratios and efficiencies;
brake circuit and force characterization; surveyed road; body and underbody CAD;
wind-tunnel or track measurements with uncertainty; and data-sharing rights.
Until then all car values and tire parameters in new fixtures must be labeled
synthetic, including any assumptions pending team tire data. Do not apply the
provisional 2027-28 ratio to the 2025 car.

## Integration boundaries and ordered milestones

1. **Establish comparable fixtures.** After the execution blocker is resolved,
   use the bounded mechanics and laminar-flow contracts in
   [comparison-spec.md](comparison-spec.md). Freeze inputs, source and tool
   hashes, clocks, settings, resources, errors and outputs before each run.
   Compare each engine with the same analytical answer before comparing engines
   to each other. A successful analytical fixture is software verification, not
   validation of a vehicle or its aero.
2. **Grow the native plant only in a separate workspace.** Keep one engine as
   the physical-state owner and a versioned, immutable command/observation
   interface. Add explicit capability declarations for wheel torque versus
   driveshaft torque, brake actuation and unavailable channels; reject an
   unsupported topology instead of silently mapping it. Keep steering request
   separate from measured road-wheel angles; preserve held controller commands,
   force-source/geometry timestamps and independent controller, plant and
   logging clocks. Add suspension/contact and wheel balance checks before any
   longer scenario. Production integration and controller/policy changes
   require separate review.
3. **Build a frozen offline aero dataset.** First use a public, reproducible
   generic geometry. Record surface and volume mesh hashes, mesh quality,
   boundary-layer treatment, turbulence and wall models, fluid properties,
   domain, moving-ground and wheel assumptions, solver settings, convergence,
   force/moment reference origin, uncertainty and mesh-family identities.
   Progress from the analytical fixture to a public external-flow comparison,
   then only to authorized car geometry. Never treat prettier streamlines or
   cell count as evidence of accuracy. Prefer at least three systematically
   refined grids where feasible; report non-monotonic or unconverged results
   instead of forcing a convergence estimate. [NASA grid-convergence guidance](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html).
4. **Exchange a map, not live CFD, initially.** A versioned map should declare
   aerodynamic force and moment axes, reference area and length, force/moment
   origin, air density, geometry/mesh/solver identity, domain of validity and
   uncertainty, along with vehicle-relative airspeed and yaw and the tested
   ride-height/pitch/roll operating point. For body-to-world rotation `R_wb`,
   relative vehicle-through-air velocity is `R_wb^T (v_CG_world - v_air_world)`;
   dynamic pressure is `0.5 rho |v_rel|^2`. Transfer moment from a reference
   point to the CG using `M_CG = M_ref + (r_ref - r_CG) x F`, in one frame.
   Account for force and moment once in the physical-state owner's equations.
   Outside the tabulated domain, report unavailable and require an explicit
   model choice; do not silently extrapolate or swap models. Preserve the raw
   CFD cases and do not call the map measured car data.
5. **Only then expand fidelity.** Validate steering and suspension kinematics,
   normal loads and contact, braking/drive, transient tire response, and energy
   accounting in short isolated scenarios. Add 3-D road, flexible structures,
   thermal effects or coupled/transient CFD only when their inputs, convergence
   and incremental value justify them. Hold out independent team data for
   validation; tuning and validation on the same run are different claims.

## Status and source identity

The engine comparisons and full-simulator integration in this document are
planned work. No comparative mechanics or fluid run was performed for this
proposal. A passing synthetic benchmark would verify only its stated case; it
would not establish vehicle calibration or lap-time accuracy. Existing native
receipts remain historical evidence of their named source and fixture.

The existing Chrono source, study, documentation and tests were compared with
public `main` at commit `feed2e37f8114ec2a3ed836a8ab780d22078da91` on
2026-11-03. Sixteen relevant Git blobs matched the isolated research snapshot;
later changes must be checked against the actual selected revision. Key public
blob identities are:

| Existing repository file | Git blob SHA-1 |
| --- | --- |
| `src/lapsim/dynamics/native_plant.py` | `a1ac894325fe2d4a9c4e0461c93853dde9c9225a` |
| `src/lapsim/dynamics/chrono_vehicle.py` | `08301e5a56db2e1299405f98e110219a3b5c02a1` |
| `src/lapsim/experiments/suspension_study.py` | `d656b849e1cf6d82ab3fbdb85edb9d633c5d14a2` |
| `docs/chrono_suspension_study.md` | `60a7448c20f10b83493b69efc33eb3b820320c98` |
| `docs/research/chrono_backend.md` | `b71c8f89e424ff513e268b866fc1cc63de3c2c13` |

External links above are primary project or agency sources consulted on
2026-11-03; they describe capabilities, not local execution.
