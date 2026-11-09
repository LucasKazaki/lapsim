# Course catalog search

The ordinary controller-search CLI can select any of the nine shipped course
bundles by catalog ID. It validates the existing catalog and bundle geometry
before creating output. Unknown or conflicting selections are rejected.

This is the synthetic ordinary tournament backend. Its controller philosophies
are `fixed`, `traction`, `yaw_pi` and `tire_reserve`. They are not aliases for the
portable seven-policy AWD registry. There is no native admission, exact-runtime
qualification or official event scoring supplied by this command.

## One course

This example prepares an actual FSI search checkpoint with **zero rollouts**:

```text
python -m lapsim.experiments.controller_tournament --course-id amz_fssim_fsi_approx --laps 1 --population 4 --generations 1 --maximum-new-runs 0 --wall-seconds 30 --output work/catalog-selection-check
```

Replace the ID with another entry from `configs/courses/catalog.json` to select
that exact bundle. The normal single-course checkpoint/replay format is unchanged.
Existing CLI defaults remain stadium, ten laps and the original search settings.
Catalog selection cannot be combined with `--course` or `--course-bundle`.

## All nine courses

```text
python -m lapsim.experiments.controller_tournament --all-courses --laps 1 --population 4 --generations 1 --maximum-new-runs 216 --wall-seconds 600 --output work/catalog-batch-1
```

Use a fresh output directory. This creates one `catalog-search.json` index and
separate search/checkpoint/replay directories for courses that start. Every selected course
appears in the index, including failed, paused and unrun courses. Catalog labels,
descriptions, approximation classes, provenance and canonical bundle/specification
hashes remain attached. No cross-course winner or official points are produced.

The **one shared** run cap applies to the whole batch. A slot is reserved and the
index saved before a rollout call. Failed or uncertain calls consume that slot;
there are no automatic retries or refunds. The wall budget is checked at rollout
boundaries and before calling a rollout. It is cooperative: one in-flight rollout
and subsequent file finalization can exceed the requested wall time. It is not an
OS deadline, ownership lease or resource guard. Wall time must be 1–900 seconds.
The run cap must be an explicit nonnegative integer within the selected searches'
declared conservative total; zero creates an unrun metadata index only.

All-course mode requires explicit one-lap selection. The existing search chooses
its long-course horizon for bundles over 400 m. It preserves each course's own
training/held-out separation and retains returned invalid numerical outcomes.
It does not treat an unfinished rollout or an ineligible candidate as a lap.
An unexpected exception stops the batch, preserves existing child files and the
failure index when writing remains possible, then propagates the exception.

Unrun rows have `checkpoint_runs=0`. For started courses it is a returned
search-state count, or `null` when a child did not return and the batch has not
read back its checkpoint. A failed child's older
replay may be stale. File presence and local counts do not authenticate outputs
or prove crash/power-loss durability.

## Continuation and limits

The all-course batch is **fresh-only** and rejects `--resume`. A paused child's
existing ordinary checkpoint can separately be resumed with `--course-id`,
matching search arguments and `--resume` under an explicitly chosen new invocation
budget. That is not continuation of the old batch budget; it does not update the
old batch index or authorize retrying an uncertain failed call. Preserve the
original index as the snapshot of that invocation.

The ordinary resume contract compares specification and its declared source
hashes. Stored runtime information remains descriptive; this command does not
establish dev23's exact-environment admission contract. Do not update source in an
active study, relabel old checkpoints with new source, or merge numerical results
across backends/environments without their applicable compatibility evidence.

The ordered skidpad sequence is an open, separate development event. It is
explicitly unsupported by this closed-course batch runner. The seven-policy
portable backend, real-car parameters, calibrated track boundaries and hardware
actions remain separate requirements. Completion of a search is not validation
of a car, course survey, native launcher or tournament qualification.
