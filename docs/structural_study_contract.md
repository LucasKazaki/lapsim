# E15 circular component study — acceptance contract

Frozen 16 October 2026 before implementation, after main `cb45a338` reproduced
the integrated bicycle/controller baseline. Question: how do declared isotropic
material and circular-section geometry change a component's compliance, stress,
mass and inertia under the same externally imposed loads?

The smallest model is a uniform solid/hollow circular cantilever, local x along
its undeformed centroid, y along tip force, z completing a right-handed frame.
The root x=0 is fully clamped. A tip force Fy and tip torque Mx act at x=L.
Euler–Bernoulli bending and Saint-Venant circular torsion are linear and static;
there is no gravity/body load, shear deformation, warping restraint, joint,
suspension, buckling, fatigue, weld, composite or chassis assembly model.

SI ownership: versioned material cards own density rho, Young's modulus E,
Poisson ratio nu and illustrative tensile yield. G=E/[2(1+nu)] assumes isotropy.
Every property has nominal/lower/upper values with explicit synthetic provenance;
the intervals are independent engineering assumptions, not confidence intervals
or certified alloy allowables. Geometry cards own L, outside and inside diameter
and their bounds. Enforce lower OD > upper ID, L>0, ID>=0, E/rho/yield>0,
-1<nu<0.5. Reject bool, NaN, infinity, unknown keys/versions and extreme scales
outside the declared numerical domain. No default card represents team hardware.

Use factored annular expressions A=pi(Do-Di)(Do+Di)/4,
I=pi(Do-Di)(Do+Di)(Do²+Di²)/64, J=2I. Compute signed deflection
Fy L³/(3EI), tip slope Fy L²/(2EI), twist Mx L/(GJ), stiffness
3EI/L³ and GJ/L. Report torsional N m/rad and N m/degree separately.
Root outer-surface maxima are |Fy|L Ro/I and |Mx|Ro/J; report the conservative
combined maximum sqrt(sigma²+3tau²) and illustrative yield/stress ratio (null
for zero stress). Loads, rather than displacement, are prescribed: changing E
alone must change deflection but leave stresses unchanged.

Mass=rho A L; centroidal Ix=m(Ro²+Ri²)/2,
Iy=Iz=m[3(Ro²+Ri²)+L²]/12. Recompute all values after every material/geometry
change. A/B uses the same loads; default geometry is fixed. An edited B geometry
is explicitly a manual geometry change, never an optimization claim.

Evaluate 128 independent interval corners for conservative output ranges.
Keep signed results and label bounds as sensitivity envelopes. Domain warnings
use every corner: L/Do>=20, |deflection|/L<=0.05, absolute slope/twist<=0.1 rad,
and combined stress below the declared illustrative yield. A flagged result
remains inspectable but is unsuitable for linear-domain ranking. These checks
are model limits, not structural approval or a factor-of-safety certification.

Reuse the existing canonical JSON/content IDs, runtime/source provenance and
strict JSON decoder. A separate structural record freezes complete cards, load,
boundary/frame/units, analytic backend/version, source hashes, nominal results,
intervals, 41 shape samples and validity. Replay checks its content ID and all
metadata and recomputed results (relative 1e-10; zero and integers exact); source
agreement is reported separately. It never mutates a vehicle configuration.
Limit imports to 256 KiB and bounded, finite structures. Saving is explicit.

Acceptance: independent hand calculations; solid/hollow and zero/reversed
loads; material-only stress invariance; mass/inertia geometry scaling; modulus,
length, load and diameter scaling; interval coverage including interior samples;
invalid and adversarial records; actual desktop calculate/export/import/replay;
optional headless FE comparison at multiple meshes with actual solver identity,
input/output hashes and discrepancy retained. No optional solver is required at
startup. Ordinary runtime introduces no specialist dependency.

FE receipt repair acceptance (16 October, PR67 review): retain each attempted
solve's actual exit code, timeout state and log hash. A failed process, timeout
or unreadable result must still produce a summary with explicit passed/failed/
skipped counts before returning failure. Stop after that case and mark remaining
cases unstarted; a null exit code must never imply a successful solve.

Tool decision and primary references (accessed 2026-10-16):

- [MIT structural mechanics worked examples](https://ocw.mit.edu/courses/2-080j-structural-mechanics-fall-2013/d822a94a5e00663ee03a4909086181bb_MIT2_080JF13_ProbSet_10_Sol.pdf):
  beam stiffness and circular torsion provide independent equation references.
- [Chrono VEHICLE](https://api.projectchrono.org/manual_vehicle.html),
  [FEA 10.0](https://api.projectchrono.org/10.0.0/manual_fea.html),
  [installation](https://api.projectchrono.org/10.0.0/module_vehicle_installation.html),
  [license](https://github.com/projectchrono/chrono/blob/10.0.0/LICENSE): BSD-3-Clause;
  C++/CMake modules and optional visualization, Windows/headless capable. Useful
  later for suspension/assemblies; not installed or benchmarked in this slice.
- [CalculiX](https://www.calculix.de/) and [author downloads](https://www.dhondt.de/):
  2.23, GPL v2 or later, separate headless ccx and graphical cgx, Windows/Linux.
  Select optional project-local ccx as an independent beam benchmark; do not
  redistribute it or add it to startup. Its FE beam includes shear effects, so
  discrepancies with Euler–Bernoulli require interpretation, not tolerance tuning.
- [OpenModelica FMI/TLM](https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/fmitlm.html)
  could not be fetched in this check; [license](https://openmodelica.org/useresresources/license/)
  describes OSMC-PL/AGPL alternatives. Windows compiler installation and exported
  model binaries add burden; no installation, execution or coupling claimed.
- [FMI](https://fmi-standard.org/): current interface 3.0.2, XML/C/binary container
  with command-line reference tools. It is an exchange boundary, not a structural
  solver. No FMU importer/exporter or FMI runtime is selected or benchmarked.

Analytic default is selected because its equations and domains are inspectable,
portable and already supported by the project runtime. Specialist integrations
require their own small execution benchmark before becoming dependencies.

Review correction, 16 October: the original universal 1e-12 absolute replay
tolerance admitted zero in place of a valid thin section's 3.94e-16 m4 second
moment. Tighten absolute tolerance to zero for every floating field; retain
relative 1e-10 for nonzero values and compare zero and integer fields exactly.
This protects tiny inertia and load-response values without changing equations,
model records or accepted results. Preserve the thin-section and tiny-load
counterexamples and verify legitimately saved earlier records still replay.
