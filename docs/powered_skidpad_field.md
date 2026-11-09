# Four-controller powered skidpad development field

The field command composes the real powered skidpad sessions in fixed order:
`fixed`, `traction`, `yaw_pi`, `tire_reserve`. It does not route skidpad through
the closed-course genetic search or alias these four controllers to AWD7.

```sh
<installed-python> -I -B -m lapsim.events.powered_skidpad_field \
  --entry-length-m 5 --exit-length-m 5 \
  --maximum-ticks 10000 --maximum-work 200000 \
  --total-step-budget 40000 --wall-seconds 120 --chunk-steps 100 \
  --output <new-absolute-external-directory>
```

From this source checkout use `PYTHONPATH=src python -m ...` instead. An
installation needs the exact successor source containing this module; frozen
dev27-r02 wheels do not contain it. No interpreter, dependency installation,
native worker, original guard or authenticated admission is supplied by the
command. The source uses the existing synthetic RWD fixture, not a team-car
mapping. This is a development event field, not native tournament qualification.

Every cell gets a fresh complete state and independent controller memory.
Before any numerical step, the command compares canonical bindings with only
the controller excluded, then compares the complete initial states. Course,
vehicle, driver, pack, source/runtime record and per-cell limits must match.

## Bounds and outcomes

Both aggregate limits are explicit. A dispatch reserves at most 100 intervals
before execution and persists its reservation. Unused reservations, including
a cell completing partway through a chunk, are never refunded. Accepted steps
and attempted intervals are reported separately; a rejected interval consumes
an attempt. Per-cell tick and numerical-work caps remain unchanged.

Wall time is checked between chunks and after reservation I/O. It is a
cooperative dispatch limit, not an OS deadline covering an in-flight integrator,
publication or cleanup. A genuine native invocation still requires its original
supervision, finite allocation and cleanup contracts.

`field-index.json` preserves every cell in fixed order: completed, failed,
paused or unrun. No incomplete average is promoted to a score. The index has
no winner, official points or qualification authority. A terminal failed cell
is retained before a different controller can run; it is never retried. An
unexpected execution exception stops subsequent cells. Publication errors
propagate and also prevent further execution.

If an aggregate limit pauses a nonterminal cell, its **real** checkpoint status
stays `running`; the outer cell/index says `paused_aggregate_budget` or
`paused_wall_budget`. The command does not forge an early per-cell terminal
budget status. Aggregate continuation is unsupported and resume arguments are
rejected. A child checkpoint is inspectable data and does not grant native
continuation authority or an automatic extension of the field allocation.

## Files

- `plan.json`, `common-binding.json` and `initial-state.json` retain the initial
  field and matched inputs.
- `reservations/` contains create-only reservations made before dispatch.
- `cells/<controller>/` retains the existing binding/checkpoint/result/files
  schemas used by the single-cell command.
- `field-index.json` records final or paused field outcomes and pins each
  published cell inventory.

Files are create-only and existing output is refused. There is no claimed
power-loss durability or original owned-output retention proof. If the process
stops before final publication, retained partial files and reservations do not
mean success; the command will not resume or overwrite that directory.

Exit 0 means all four development cells completed their model gates. Exit 3
retains a paused/failed/interrupted field, and exit 2 reports invalid inputs or
publication failure. None of these statuses establishes an official result.

The individual numerical sessions, gate measurement limits and immutable
checkpoint rules are described in [the single-cell guide](powered_skidpad.md).

## Installed acceptance, 2026-11-08

The command above completed all four cells using the frozen `.4` wheel in a
clean Linux/CPython 3.12.14 environment, from outside the checkout. Whole-process
time was 105.307 s; the field's own clock measured 102.584 s against its 120 s
cooperative limit. All 16601 attempted intervals were accepted, with 16800
reserved intervals. The 199 unused reservations were not refunded.

Every numerical/controller/gate/checkpoint field, excluding the intentionally
different source binding, exactly matched that controller's earlier individual
run. Original source hashes and binding checks were not weakened. All six
model gates completed per cell; no winner was emitted. `traction` and
`tire_reserve` had identical trajectories in this fixture, so it does not show
an additional reserve-clipping effect or qualify another performance regime.

See [the pinned field evidence](evidence/powered-skidpad-four-controller-20261108.json).
The tested runtime is commit `ca75c1ea0617a21c7cad5d7e4c5096c6ebe2819a`, wheel
SHA256 `c502f65512f32e067652757a64c23ce11c5541e1244661fc5cbf19e5de1b5dc4`.
Subsequent evidence-document changes do not replace that tested wheel.
