# Bounded full-simulator comparison specification

Status: **proposed; no cases executed**. These are synthetic verification cases,
not car predictions. The ceilings below are proposed limits for separate future
runs, subject to review and stricter applicable resource limits.

## Admission and receipts for every future case

Before a launch, identify the exact installed tool version, binary and dependency
hashes and review its license. The candidate engines must actually support the
specified forces and boundary conditions in the selected builds. If not, record
the case as blocked rather than substitute a different physical model.

Run one case at a time with at most one solver CPU thread plus necessary
monitoring, no GPU, no network and a fresh output directory. Require reviewed
process ownership, monitoring, cancellation, deadlines and cleanup. Where a
solver runs under WSL or another host, establish observation, accounting,
revocation and cleanup for its descendants; a launcher exit alone is not proof.
On admission loss, nonfinite data, timeout, memory violation, failed cleanup or
missing receipt, stop the owned work, record failure or uncertainty, and skip
remaining cases. Do not restart automatically or reset the budget. Deadlines
define acceptance limits; they are not a hard-real-time guarantee that the
operating system will finish teardown. Missing or late cleanup observations leave
cleanup uncertain.

Before running, bind source commit, dirty status, OS and runtime, solver version
and binary/dependency hashes, model/mesh/config/input hashes, topology, units,
frame, integration method, solver tolerances, thread count, exact command and
working directory. Afterward preserve raw stdout/stderr, exit/timeout, owned
process identities and observed cleanup, actual wall/CPU/peak memory, outputs,
convergence history and result hashes. Hashes prove integrity, not physical
truth or authorship. Pin and review the concrete solver input files before
execution; this specification does not claim those files already exist.

## M0: Chrono versus MuJoCo, one-degree-of-freedom oscillator

Purpose: independently check a common multibody force/integration boundary.
This is a new tiny engine fixture, **not** the existing Chrono sedan study, a
vehicle suspension benchmark, a tire test or a repeat of prior 93 tests, 57
vectors, six replays or runner mocks.

| Item | Frozen synthetic value |
| --- | --- |
| State | One body constrained to translation along +Z; no rotation, contacts, tires or actuators; gravity disabled |
| Mass | `m = 300 kg`; passive linear spring `k = 30000 N/m`, damper `c = 1800 N s/m`; fixed zero-rest displacement |
| Initial condition | `x(0) = 0.020 m`, `v(0) = 0 m/s` |
| Dynamics | `m*x'' + c*x' + k*x = 0`; spring and damper force applied exactly once |
| Duration / observation | `2.000 s`; samples at `0, 0.020, ..., 2.000 s` (101 samples) |
| Plant time steps | `0.004`, `0.002`, `0.001 s` (500, 1000, 2000 steps); preserve the same initial state and sample times |
| Runs | Two engines x three step sizes = six independent runs; no sweep or rerun in this budget |

The analytic displacement oracle is
`x(t) = 0.020 exp(-3 t) [cos(sqrt(91) t) + 3/sqrt(91) sin(sqrt(91) t)]`;
velocity is `v(t) = -(2/sqrt(91)) exp(-3 t) sin(sqrt(91) t)` m/s.
Initial mechanical energy is 6 J and ideal energy decreases by
`integral(c*v^2 dt)`. Exact sampled time values must be generated independently
of the engine under test. Record the implemented joint/spring/damper definition
and integrator/solver settings; do not compare two unrelated vehicle fixtures.

Proposed acceptance, to be frozen before case execution:

* Every sample is finite, clocks match to `1e-9 s`, exactly 101 observations
  occur, and no additional physical force or contact is active.
* At the finest step, each engine's maximum absolute sampled displacement
  error is at most `0.0003 m` and velocity error at most `0.005 m/s` against the
  analytic solution. Between engines, maxima are at most `0.0006 m` and
  `0.010 m/s` respectively. These are engineering screening thresholds, not
  measured uncertainty or accuracy guarantees for a car.
* Report all three errors and their ratios, plus energy and integrated damping
  work. Refinement should reduce error unless all compared errors are below a
  declared `1e-8 m` displacement or `1e-7 m/s` velocity noise floor; otherwise
  label convergence unresolved rather than fitting an order. No sampled energy
  may exceed its 6 J initial value by more than `0.05 J`; investigate any
  larger growth. Report energy-balance residual and its refinement separately.

Per run: capture `t0` before setup, stop work by `t0+90 s`, and complete cleanup
by the earlier of 30 s after the first stop/error or `t0+120 s`; maximum observed
owned-process-tree working set 512 MiB, subject to any stricter applicable limit.
Six individually admitted runs total at most 720 s within their own envelopes;
there is no automatic batch or carry-over. Fail acceptance and mark cleanup
uncertain if teardown cannot be confirmed inside its deadline. These are abort
ceilings, not predictions.

## M1: Chrono versus MuJoCo, two-mass vertical response

Conditional on successful M0 and a new accepted budget: compare a synthetic
quarter-car-like two-degree-of-freedom assembly. It is an independent fixture,
not the existing sedan or a full tire/contact test. The lower spring is bilateral
and can pull; it represents a linear tire stiffness for this mathematical case
only, not a unilateral contact law.

Use gravity-free displacement from a synthetic equilibrium, initial positions
and velocities zero, sprung mass `m_s = 75 kg`, unsprung mass `m_u = 15 kg`,
suspension `k_s = 15000 N/m`, `c_s = 900 N s/m`, and road spring/damper
`k_t = 150000 N/m`, `c_t = 150 N s/m`. With up positive and prescribed road
height `r(t)`, the common equations are:

```text
m_s z_s'' = -k_s (z_s-z_u) - c_s (z_s'-z_u')
m_u z_u'' =  k_s (z_s-z_u) + c_s (z_s'-z_u')
             - k_t (z_u-r) - c_t (z_u'-r')
```

Set `r=0` until `0.2 s`; for `0.2 < t < 0.4 s`, use
`r=0.01 [1-cos(pi (t-0.2)/0.2)] m`; from `0.4 s` onward use `r=0.02 m`.
Supply the exact derivative `r'` to the road damper, and the same prescribed
motion to both engines. No extra gravity, contact, actuator or duplicate spring
force may be active. If an engine cannot realize those equations, record a
blocker rather than substitute a contact model.

Run each engine at plant steps `0.001`, `0.0005` and `0.00025 s` for `2.000 s`
(2,000, 4,000 and 8,000 steps), observing every `0.010 s` (201 observations).
An independent reference must solve the stated linear equations piecewise, for
example by a reviewed matrix-exponential solution with the sinusoidal forcing
augmented as state; it must not call either engine under test. Freeze that
reference implementation and inputs before execution. On the finest step,
require maximum sampled errors `|z_s-z_s_ref| <= 0.0003 m` and
`|z_u-z_u_ref| <= 0.0005 m` for each engine; the respective cross-engine
differences must be `<= 0.0006 m` and `<= 0.001 m`. Report velocities,
suspension and road forces, and all three step errors. Expect refinement to
reduce error or label it unresolved, with the same `1e-8 m` displacement
noise floor as M0. These are proposed screening thresholds, not car tolerances.

For the mechanical ledger, define `F_t = k_t(r-z_u) + c_t(r'-z_u')` and
`E = 0.5 m_s z_s'^2 + 0.5 m_u z_u'^2 + 0.5 k_s(z_s-z_u)^2 +
0.5 k_t(z_u-r)^2`. Compare `Delta E` with the integral of
`F_t r' - c_s(z_s'-z_u')^2 - c_t(z_u'-r')^2`, including integration error;
report its residual and refinement, without clipping or resetting state. This
fixture does not establish tire friction, steering, torque split or road-holding.

This is six additional independent runs. Each has the M0 per-run deadline,
cleanup and 512 MiB ceilings; total admitted elapsed budget is at most 720 s.
The separate M1 budget cannot be used until M0 and its receipts are accepted.

## F0: OpenFOAM versus SU2, laminar periodic channel

Purpose: compare two incompressible solvers and three spatial resolutions against
fully developed planar Poiseuille flow. This is deliberately not external
car aero, turbulent RANS, a lap simulation or physical car validation.

| Item | Frozen synthetic value |
| --- | --- |
| Geometry | 2-D channel `0 <= x <= L = 0.5 m`, `0 <= y <= H = 1 m`; unit depth for flux/forces |
| Fluid | constant `rho = 1 kg/m^3`, dynamic viscosity `mu = 0.1 Pa s`; incompressible Newtonian laminar flow; no energy equation |
| Boundaries | no-slip walls at `y=0,H`; translationally periodic x pair; constant driving pressure drop `Delta p = 0.6 Pa` over `L` |
| Equivalent driving | constant acceleration `+1.2 m/s^2` with periodic reduced pressure; pressure reference arbitrary. Use equivalent forcing exactly once, not both pressure drop and body force |
| Analytical answer | `u(y) = 6 Ubar (y/H)(1-y/H)`, `Ubar = 1 m/s`, `u_max = 1.5 m/s`, `v = 0`, `|tau_wall| = 0.6 Pa`, mass flux per unit depth `1 kg/(m s)`, `Re_H = 10` |
| Grids | Common structured quads with `(Nx,Ny) = (16,32), (32,64), (64,128)` = 512, 2048, 8192 2-D cells. Nest nodes and use the same physical boundaries. For OpenFOAM use one spanwise cell and empty front/back; for SU2 use 2-D. Preserve each solver's native control-volume interpretation. |
| Runs | Two solvers x three grids = six independent runs; no turbulence, car CAD or GPU run in this budget |

Use SU2's documented streamwise pressure-drop facility only if the selected
release supports it with its laminar incompressible solver; establish the
equivalent OpenFOAM forcing in the selected Foundation release. The SU2
[periodicity documentation](https://su2code.github.io/tutorials/Inc_Streamwise_Periodic/)
describes the pressure-drop option; its illustrated turbulent pin-fin case is
not this analytical fixture. Preserve the exact selected-release configuration,
pressure units and conversions. Independently verify that the realized driving
term has the stated sign and magnitude. Label this implementation mapping
unverified until reviewed; if unavailable, stop rather than comparing different
boundary conditions.

For each grid, record residual histories using each solver's own normalization,
integrated mass flux at the periodic pair, wall shear and streamwise velocity at
the nine fixed locations `x=L/2`, `y/H=0.1,...,0.9`; use a declared,
consistent interpolation or cell-average projection and independently evaluate
the analytical result at those same supports. Include the projection's error
in the convergence assessment. Require `|Q_outward_left + Q_outward_right|`
`<= 1e-6 kg/(m s)` per unit depth and changes in mean flux and wall shear
`<= 0.1%` over the last
100 solver iterations after at least 100 iterations. Record residuals and ensure
each final normalized residual `R_f <= max(1e-12, 1e-6 R_0)` using that
solver's documented normalization. If a solver
does not expose a comparable metric, identify it and keep convergence pending;
do not translate residual magnitudes between solvers.

On the fine grid, require maximum absolute pointwise velocity error `<= 0.01 m/s`,
mean-flux error `<= 1%` and each wall-shear magnitude error `<= 2%` against
the analytic solution. Report errors and changes on all three grids and their
cross-solver difference. If errors are not decreasing and above a declared
numerical floor, or iteration convergence is not demonstrated, mark mesh
convergence unresolved. Do not infer an order or extrapolate from only two
grids or from non-monotonic results. Thresholds are proposed screening targets.

Per run: capture `t0` before setup, stop work by `t0+150 s` and complete cleanup
by the earlier of 30 s after the first stop/error or `t0+180 s`; maximum observed
owned-process-tree working set 1 GiB or the stricter applicable ceiling. Six
separate admissions total at most 1080 s within their own envelopes. If a mesh
cannot converge in budget, retain the failure and stop; do not enlarge the
budget silently. For a future 3-D volume mesh, halving uniform cell size in
all three directions gives approximately eight times as many cells before
boundary and meshing effects; memory and solve time must be measured for the
actual solver, fields and hardware rather than inferred from that multiplier.

## Next comparison after F0, outside this budget

Once F0 and its resource receipts are accepted, propose a separate, explicitly
admitted external-flow comparison based on a publicly documented geometry such
as the [SU2 incompressible NACA 0012 tutorial](https://su2code.github.io/tutorials/Inc_Turbulent_NACA0012/).
Freeze the identical geometry, Reynolds number, freestream, turbulence and wall
model, domain, reference area/length, boundary conditions and three mesh levels
for both solvers; check compatibility and data rights first. Compare coefficients,
pressure distribution, residuals and mesh sensitivity against independently
sourced reference data and stated uncertainty. The published tutorial's own
settings are a reference, not evidence that its exact grids, numerical model or
local tools match the other solver. A wing section is not a complete car.
