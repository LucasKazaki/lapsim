# Circular component materials study

E15 is a static, standalone component benchmark. The root of a uniform circular
cantilever is fully clamped; a transverse tip force and axial tip torque act on
its free end. The two material cards are synthetic examples, not certified
alloys, composite laminates, team measurements or design allowables.

On desktop select **Four-wheel lab → Component materials → Calculate A/B**.
The view shows signed bending deflection and torsional rotation, nominal mass,
centroidal inertia, stiffness and combined root stress. It evaluates the same
loads for both cards. Different B outside diameter explicitly selects a manual
geometry change; no optimizer is implemented. A calculation updates all supported
mass and inertia terms. Changed or invalid input clears the previous result.
The **New study** action unlocks inputs after opening a saved comparison.

The dimension-bounds control adds independent ±1 mm span and ±0.1 mm diameter
intervals around entered dimensions. Material property bounds are always
included. The analytic API also accepts versioned custom material/geometry
cards with explicit provenance and intervals. Results contain all 128 interval
corners' extrema and the input cards; intervals are sensitivity envelopes, not
probabilities. The defaults assume the material reference-temperature domain
(273–333 K); temperature-dependent behavior is unavailable.

With A=pi(Do²-Di²)/4, I=pi(Do⁴-Di⁴)/64 and J=2I, the solver uses:

| Quantity | Equation / units |
| --- | --- |
| Isotropic shear modulus | G=E/[2(1+nu)], Pa |
| Tip bending | delta=Fy L³/(3EI), m; slope=Fy L²/(2EI), rad |
| Tip torsion | phi=Mx L/(GJ), rad |
| Component stiffness | Kb=3EI/L³, N/m; Kt=GJ/L, N m/rad |
| Per-degree torsion stiffness | Kt(degree)=Kt(radian) pi/180, N m/degree |
| Root stress maxima | sigma=abs(Fy)L Ro/I; tau=abs(Mx)Ro/J; VM=sqrt(sigma²+3tau²), Pa |
| Mass and centroid inertia | m=rho A L; Ix=m(Ro²+Ri²)/2; Iy=Iz=m[3(Ro²+Ri²)+L²]/12 |

Load control explains why a material-only E change changes deflection but leaves
stress unchanged. Component stiffness depends on both material and geometry.
Assembled chassis torsional stiffness also depends on the structure, joints and
boundary conditions; this study does not estimate it. There is no stiffness to
lap-time multiplier or tested reduced-order mapping into the vehicle plant.

Warnings cover insufficient slenderness (L/Do<20), deflection/L>0.05, slope/twist
over 0.1 rad and stress above an illustrative yield assumption at any interval
corner. Flagged results stay inspectable but cannot support linear-domain
ranking. There is no shear-deformation, buckling, fatigue, weld, joint,
suspension or composite model. An illustrative yield ratio is not approval.

## Reproduce and share

```text
python -m lapsim.experiments.component_study --output component.json
python -m lapsim.experiments.component_study --replay component.json
python -m lapsim.experiments.component_study --material synthetic_dense_v1 --output dense.json
python -m lapsim.experiments.component_study --comparison --output comparison.json
python -m lapsim.experiments.component_study --replay comparison.json
python -m pytest tests/test_component_study.py -q
```

Desktop saves `lapsim.component-comparison.v1` containing two complete
`lapsim.component-study.v1` runs. Each run has canonical configuration/content
IDs, source/runtime identity, cards, SI frame/boundary, analytic backend and
version, validity, shape and interval results. The shared decoder rejects
duplicate keys/nonfinite JSON and imports are capped at 256 KiB. Replay verifies
both numerical results and model metadata before displaying an imported record;
source agreement is reported separately. The CLI can create a single run or the
same paired comparison, and its replay command accepts either format. File reads
are bounded before decoding, including files that grow during the read.
Nonzero replayed values use relative tolerance 1e-10 with no absolute floor;
zero values and integers match exactly. This prevents small section moments
or tiny load responses from being replaced by zero during checked replay.
CLI replay output must be a separate file; resolved-path and hard-link aliases
of the input are rejected before writing so the saved evidence is preserved.
Malformed numeric results, including integers outside the floating range, are
rejected before comparison. Derived quantities must also remain finite; loads
so small that an illustrative yield ratio overflows fail explicitly. CLI failures
return an error without a traceback or a partial verification file.
The Python API exposes `run_component_comparison` and `replay_component_comparison`.

## Actual optional finite-element benchmark

The project-local Windows **CalculiX 2.23 ccx_static.exe** was executed on
2026-10-16. Downloaded from the author's
[Windows archive](https://www.dhondt.de/calculix_2.23_4win.zip), archive SHA256
`87fc4e1721df37370ec67d0a244bb14f9bf804b0a95df49e2ae7369d30ec72e8`,
executable SHA256
`e18360eb32a5cd48f91a212c57069212cd8e27d2f798a599a78106bd0b3ecc1f`.
It is an optional external GPL solver and is not bundled, required at startup,
or invoked when a teammate calculates an analytic study.

The benchmark generates B32R PIPE elements with radius 0.0125 m, wall 0.002 m,
span 0.6 m, clamped root, Fy=100 N and Mx=0. It runs both materials on 4, 8,
16, 32, 64 and 128 elements, checks actual completion and parses the tip
displacement from each `.dat`. At 128 elements the light/dense relative
differences from Euler–Bernoulli are **0.07731% / 0.03905%**, decreasing from
3.3825% / 2.7391% on four elements. This is an observed refinement comparison,
not an exact formulation equivalence or a torsion/material correlation.
The FE beam expands into solid elements and includes shear. Complete measured
values and input/output/log hashes are in
[the compact receipt](evidence/e15-calculix-refinement.json).

```text
python quality/run_component_fe.py --ccx PATH_TO_CALCULIX_2.23 --output work/new-fe-run
python quality/run_component_runtime.py
```

Use a fresh output directory for each FE run. No solver download or installation
is automatic. The Windows distribution returns 201 for its successful `-v`
query; that is retained explicitly, while every actual solve must return zero,
write results and report completion. The author documentation was downloaded
and checked for PIPE radius/thickness conventions. See the
[frozen contract and dependency assessment](structural_study_contract.md) for
Chrono, CalculiX, OpenModelica and FMI decisions and primary references.
