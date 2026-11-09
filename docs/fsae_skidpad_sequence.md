# Ordered Formula SAE skidpad candidate

`lapsim.events.skidpad_sequence` implements a separate ordinary prescribed-path
event: enter, right circle untimed, right circle timed, left circle untimed, left
circle timed, then exit in the original forward direction. The vehicle is reset
once at the start. Its battery, speed and component state continue through every
phase. The existing `simulate_skidpad` API remains a single-circle study.

The 2026 rules and 2027 V1 rules, sections D.10.1–D.10.4, specify 18.25 m between
circle centres, 15.25 m inner diameter, 21.25 m outer diameter and a 3 m lane.
The candidate chooses the midpoint radius of 9.125 m for its nominal route; that
is a modeling choice, not a mandated racing line. Entry and exit lengths are
explicit scenario inputs because this unit does not invent their dimensions.
The central tangent is `(0, 0)`, the entry and exit point along `+x`, and the left
circle lies toward `+y`. Four separate circle segments preserve the repeated
physical positions as distinct ordered stations and phase cell ranges.

Sources supplied by the independent rules research:

- [2026 Formula SAE rules](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=7de1794b-82d2-4ccd-ad4d-92fd2745bb89)
- [2027 Formula SAE rules V1](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38)

The implementation worker's direct web-tool read of both supplied URLs returned
an internal access error. It did not independently retrieve the PDF bytes; the
facts above use the coordinating rules worker's verified report. No PDF hashes,
current event eligibility or measured course geometry are invented.

## Use

```python
from lapsim import ConstantControlsProfile, Controls
from lapsim.events.skidpad_sequence import (
    SkidpadSequenceConfig,
    simulate_skidpad_sequence,
    standard_skidpad_sequence,
)
from vehicle_model import Vehicle

course = standard_skidpad_sequence(
    entry_length_m=2.0,  # Explicit example scenario, not an official dimension
    exit_length_m=3.0,
    maximum_cell_length_m=0.5,
)
result = simulate_skidpad_sequence(
    Vehicle(), course,
    ConstantControlsProfile(Controls(motor_torque_request_nm=5.0)),
    config=SkidpadSequenceConfig(
        starting_speed_mps=5.0,
        maximum_driving_time_s=120.0,
        cone_count=0,
        cone_penalty_policy="fsae_2027_v1_rulebook",
    ),
)
print(result.to_dict())
```

The route is bounded to 5,000 cells. Each circle receives at least four cells;
finer resolution remains a caller choice requiring convergence assessment.
The example uses the ordinary repository vehicle and scalar torque request. It
does not select any of the seven portable AWD policies or establish actual car
calibration. Geometry and full course hashes retain exact generated values;
no rounding or cross-platform hash equivalence is introduced. Retain the exact
course artifact for a later shared-input comparison.

This generated nominal course is not yet a shared canonical imported artifact.
Identical construction inputs have not been shown to produce identical raw
geometry hashes on Windows and Linux; library-math differences may change the
last coordinate bits. No cross-platform identity equivalence is claimed.

The result retains the complete event configuration, including starting speed
and maximum driving time. It does not bind arbitrary vehicle or control-profile
configuration, so these outputs alone do not establish a matched policy or car
comparison. Those identities need a separate reviewed campaign contract.

## Timing and cone penalties

The unpenalized time is the mean of the second right and second left circle
durations. Entry, both untimed circles and exit remain in total elapsed time and
energy, but are excluded from that mean. Timing uses retained cell boundaries,
not nearest-position matching at the central crossing.

No average is accepted unless the full numerical route, including exit,
completes. The existing runner records a sample before some post-step failure
checks, so observed phase endpoints alone do not establish an accepted run.
Partial telemetry and observed phase durations remain available on failure.

Choose a cone policy explicitly:

| Policy | Added after averaging the timed circles |
| --- | --- |
| `fsae_2026_rulebook` | 0.125 seconds per declared cone |
| `fsae_2027_v1_rulebook` | 0.125 seconds per declared cone |
| `fsae_2026_event_handbook` | 0.25 seconds per declared cone |
| `None` | Preserve the raw mean and cone count; corrected time remains unset |

The coordinating research found the 2026 handbook conflicts with the rulebook.
Selecting a policy records a calculation choice and does not resolve official
precedence. The exact handbook document identity was not supplied to this unit;
its policy is explicitly labeled rather than assigned an invented URL or hash.
Cone counts are caller declarations, not detected or authenticated incidents.
The one-million-cone input cap is a software bound, not an event rule.

An optional `declared_dnf_reason` retains an externally reported disqualification
without discarding the raw run. It prevents a corrected result. The simulator
does not infer official off-course status from a wheel crossing an assumed edge.
It reports no official points or ranking and does not implement the event's
driver/run allocation or team-best-run selection. Those require independently
qualified runs, selected rules and real event data.

## Integration boundary

This is an event/course candidate within the ordinary `python-lapsim` source.
It is not appended to the nine closed `CourseBundle` catalog entries: their
closed single-winding contract cannot represent this open four-circle route.
The portable light tournament's FSI one-lap worker and physical gate remain
unchanged. A later admitted skidpad worker needs phase-aware checkpoints,
ordered physical gates, course/source/environment identity and the original
native admission, containment, budget and cleanup chain. No tournament command,
qualification receipt, hardware action or end-to-end launch is supplied here.

The focused tests distinguish deterministic telemetry doubles from one actual
ordinary prescribed-path numerical run. Neither is native Windows or portable
AWD tournament acceptance.

## Existing skidpad command

The existing analysis command has an explicit ordered-sequence mode. Its old
circle defaults and imported `run()` / `standard_skidpad_circle()` helpers are
unchanged. For a new sequence run from a source checkout:

```text
python analysis/events/skidpad_points.py --sequence --entry-length-m 2 --exit-length-m 3 --starting-speed-mps 5 --cell-length-m 0.5 --cone-penalty-policy raw-only --output-dir ../ev-results/skidpad-001
```

The entry/exit distances in this example are scenario choices. `raw-only` is an
explicit choice to retain the unpenalized mean without a corrected time. Choose
one of the three labeled penalty policies above when a specific calculation is
wanted. The default starting speed remains 9 m/s for compatibility with the old
command; the example explicitly selects 5 m/s. A numerically invalid run is
retained rather than retuned or retried automatically.

Sequence mode requires a new output directory outside the source or installed
resource tree. It cannot write within the selected input-data directory. It
saves the full course geometry, request, resolved vehicle manifest, result and
aligned telemetry CSV; a final index records their raw sizes and SHA256 values.
Files are create-only. Errors leave partial files in place without a final
index, and no cross-platform crash durability or native cleanup is certified.
If the post-run vehicle snapshot differs or is unavailable, returned raw results
and telemetry are still saved with that failure explicitly recorded; the command
exits 2 and makes no matched-input claim. An index certifies completed local file
writes, not a successful or qualified run.
JSON files are bounded to 4 MiB, telemetry CSV to 64 MiB and total output to
80 MiB. Exit status is 0 for a completed development run, 3 for numerical
incompletion or a caller-declared DNF, and 2 for command/input/output errors.

The default profile is the public `repository_baseline`. Select another public
profile with `--vehicle-profile prius_2026_le`. Both public selections use an
explicit empty intake when no data directory is supplied; neither searches an
ambient private bundle. A source-backed profile such as
`trev5_working_geometry` requires an explicit `--data-dir` pointing to its
validated local intake. Missing profiles or data produce an error with no
substitute vehicle. Profile limitations and inherited assumptions remain in the
actual `ResolvedManifest`; data hashes do not authenticate private evidence.

`ResolvedManifest.with_run_context()` retains the exact course, scenario and
constant control declaration. The existing supported vehicle serializer checks
constructor configuration equality before and after the run. This is not
continuous observation or complete loaded-source/runtime authentication. The
event replaces the declared control's steering field with track-derived steering;
the constant profile supplies the longitudinal requests. This override is retained
in the control description rather than represented as zero applied steering. The
generic event result's vehicle/control identity limitations remain visible;
the outer CLI record supplies local input provenance, not admission for a
matched seven-policy campaign. It never calls the endurance points formatter.

An ordinary installed wheel carries this analysis script under
`lapsim.resources.repository_root()`. The package owner verifies that bundled
path and `build-info.json` during installed testing; this command does not add
a new package entrypoint or infer checkout identity from ambient Git.
