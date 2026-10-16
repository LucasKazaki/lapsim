# LapSim public synthetic demonstration

This guide applies to the public `LapSim-Windows-x64.zip` artifact. The public
artifact is a source-available, synthetic-data-only demonstration. Read the
root `LICENSE`, `LICENSE_SCOPE.md`, and `NOTICE` before using, modifying, or
sharing it.

## What is included

- The simulator application and replaceable component-model architecture.
- Analytic synthetic courses generated from straight and circular segments.
- The synthetic four-wheel dynamics laboratory and pose preview.
- The offline simulator map, equations, source references, and curated source
  snapshot.
- Project and third-party notices, build identity, hashes, and frozen self-test
  evidence.

The public artifact does not include team telemetry, measured or reconstructed
track data, calibrations, fitted parameters, vehicle-specific configurations,
CAN material, firmware, CAD, vendor files, or historical validation reports.
UMD users need separate authorization and access-controlled storage for any of
those materials.

## Run a repeatable demonstration

1. Extract the ZIP and launch `LapSim.exe` on Windows x64.
2. Select **Synthetic loop · AI demo** and **Centerline (default)**.
3. Use the built-in Prius benchmark, leave **Cell size (max)** at **1 m**, leave
   assumed road grip at **100%**, and set driver request to **80%**.
4. Run one lap. Confirm the completion status before using time or energy.
5. Open the Analysis and Driver views, then inspect **Saved run details**. A
   saved record identifies the inputs, synthetic source course, solver grid,
   controls, completion state, and aligned telemetry.
6. Optionally select **AI racing line (experimental)** on the same synthetic
   course. Treat a path comparison as a model experiment, not a real-car gain.
7. Open **Simulator map** to inspect equations, variables, architecture, and
   source references.

## Interpretation limits

The main lap solver follows prescribed curvature. It does not prove that a real
vehicle followed an integrated pose, cleared cones, met a rule set, or achieved
an observed lap time. The four-wheel and pose-preview tools are separate
synthetic models. A passing software test establishes only the behavior checked
by that test; it does not establish vehicle safety, competition legality,
physical validation, or permission to publish excluded data.

The public artifact is intended for portfolio evaluation, permitted UMD
education, and the other uses expressly granted by LSCRL-1.0. Another student
vehicle competition program may not use Covered Material or generated results
for Competition Use.

## Evidence and rebuilding

- `portable-self-test.json` must report `"frozen": true` and
  `"course_synthetic": true`.
- `checksums.json` identifies the executable.
- `build-info.json` identifies the curated source snapshot and dependencies.
- [Release and rebuild instructions](release.md) describe the public-data gate,
  reproducible build procedure, and acceptance checks.
- [Architecture](architecture.md) describes package boundaries and state flow.
- [Extending models](extending_models.md) describes component replacement.
