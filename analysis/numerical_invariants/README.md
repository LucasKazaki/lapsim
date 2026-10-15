# Spatial-cell numerical checks

A bounded eight-process CPU sweep found a valid cell that the timestep iteration
rejected: initial speed 42.5 m/s, a 50 m straight cell, and 100 N·m motor torque.
The iteration alternated between 1.2011222104 and 1.2017168365 seconds until its
50-iteration limit. The same failure occurred with a saturated torque request
and with the optional tire relaxation model: four reproducible cases.

`Vehicle.update_state()` now keeps its original fixed-point path and, after
nonconvergence, solves the same timestep consistency equation within the last
observed bracket. It recomputes the original residual before accepting the
result. A synthetic discontinuous tire test proves that narrowing a bracket
across a jump is insufficient: that cell is still rejected without state changes.
The force balance, constant-acceleration cell model, and physical impossibility
checks are retained. This does not establish a globally unique timestep or
validate a 50 m integration resolution for real tracks.

## Retained comparison

The [aggregate receipt](results/cell-sweep-2026-10-15.json) includes exact source,
protocol, and full-report hashes, outcomes, parameter dimensions, repaired cases,
resource measurements, test evidence, local-model review limitations, and the
next unresolved numerical question. Full reports and source snapshots remain
under the ignored `work/cell-sweep-*` directories in the originating checkout.

| Declared sweep | Traversable | Rejected | Invariant failures |
| --- | ---: | ---: | ---: |
| Original source, 2,160 cases | 1,444 | 716 | 0 |
| Repaired source, same 2,160 cases | 1,448 | 712 | 0 |
| Near-RPM neighborhood, 160 cases | 160 | 0 | 0 |

The 1,444 originally traversable cases retained identical final speeds. The
remaining 712 rejections are the declared controls being unable to leave rest
or stopping before the requested cell ends; none partially committed state.
Checks cover finite telemetry, exact distance, longitudinal force balance,
instantaneous discharge limits, terminal `P = VI`, inverter power conversion,
nonnegative wheel loads, and tire combined-force capacity.

The final 2,160-case sweep used eight worker processes, each with one native
BLAS/OpenMP thread. It took about 2.90 seconds elapsed and 11.98 worker CPU
seconds; maximum observed per-worker peak working set was 71,786,496 bytes.
The first baseline memory probe was unavailable and is retained as null; it
was corrected for subsequent runs. These figures describe actual bounded work,
not continuous full-device utilization.

The four new physical regressions failed on unchanged PR13 source. Repaired
checks passed 74 tests and 105 subtests, including battery/drivetrain neighbors,
generated numerical properties, and source-map freshness. Ruff's runtime gate
and broad checks on new Python files passed. Updated source-map descriptions
and function references were inspected in the browser.

## Local-model review and unresolved capacity boundary

The local Qwen review supplied hypotheses, not an acceptance verdict. No alleged
DC-clipping power deficit appeared in the declared sweep. Its negative-force
concern did not match the nonnegative propulsion caller. It also confused the
existing acceleration bracket with the proposed timestep bracket. Its useful
residual/continuity concern became the explicit post-root check and the
discontinuous-model rejection test.

Separately, 104 low-SOC cells would consume more Coulomb charge than remained
during the cell before the existing SOC clamp. The sweep records this as a
diagnostic outside the instantaneous-power checks; it is **not repaired here**.
A successor should define duration-aware charge availability and atomic
rejection/subdivision behavior. These software results do not establish
real-car accuracy, measured tire behavior, or torque-controller safety.

## Reproduce

Use the normal project environment, with `src` on `PYTHONPATH`, and a fresh
output directory for each run:

```powershell
$env:PYTHONPATH = (Resolve-Path src)
.venv\Scripts\python.exe analysis/numerical_invariants/sweep_cells.py --out work/cell-sweep-new --workers 8
.venv\Scripts\python.exe analysis/numerical_invariants/sweep_cells.py --out work/cell-sweep-rpm-new --workers 8 --family rpm
.venv\Scripts\python.exe -m pytest tests/test_timestep_convergence.py tests/test_state_update.py tests/test_spatial.py tests/test_drivetrain.py tests/test_ocv_pack_battery.py tests/test_simulator_flowchart.py quality/test_properties.py -q
```

The runner creates its protocol before measurements, refuses an existing
protocol path, bounds concurrency to at most eight, and preserves expected
rejections in the complete denominator. There are no hardware, network,
language-model, or GPU calls.
