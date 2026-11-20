# Light WASD and standing 75 m gearbox-efficiency experiment

This source-only experiment bundle contains the actual project Light physics, keyboard and bounded drive adapter, and standing-start drag producer and independent replay code. It is intended for the existing lapsim project. It is not a new hardware controller, an owner/admission grant, or a claim of completed driving or vehicle calibration.

## Layout

- `manual/`: keyboard input/event handling, focus-loss pause, reset, bounded actual Light drive adapter and tests. The display uses a generated stadium layout, not a Michigan course map.
- `drag96/` and `drag91/`: separate source families with exact public synthetic input pins and matched full-pedal forward 75 m difficulty. The sole physical profile change is `actuation.gear_efficiency` from `0.96` to `0.91`; the unchanged motor conversion (0.95), inverter (0.97), battery (80 kW, 377 V), current, starting energy, tire and geometry assumptions remain active. Source request/identity metadata differs intentionally.
- `validate_public.py`: dependency-free source/readback and fixed-state validation. Run with Python 3.12+ using `python -I -S -B validate_public.py manual`, then `drag96`, then `drag91`. The manual case also runs the keyboard routing/cancellation tests without creating a window. These operations have zero physics ticks; they never create an owner, attach a native Job, observe the desktop or run a drag replay.
- `REMOTE_MAIN_READBACK.json`: read-only public path inventory, not a commit/push receipt.
- `PUBLIC_FILE_MANIFEST.json`: relative export paths and SHA-256/size, with provenance for copied and explicitly transformed source.

## Public assumptions, not private vehicle data

All input JSON files are newly generated or limited to the numerical **synthetic model assumptions** used in this experiment. They contain no original team dyno logs, workbook, measured track imagery or coordinates, saved driver, personal file paths, process data, credential, private source input blobs or raw run trace. The closed stadium was newly generated; the cone layout is a simple illustrative straight-lane fixture. The 272.2 kg model, 3.455:1 single-motor LSD, 220 Nm/275 A hypothesis, 5500 RPM cutoff, tire/thermal/aero values and efficiency settings are declared modeling assumptions, not vehicle specifications or calibration. `historical_case_data.json` is a small generated compatibility fixture, not an actual historical run. Gate class names preserve the project's existing implementation names; their public synthetic course pins and labels are deliberately rebound.

## WASD and timing

The existing keyboard view consumes `run(geometry, initial, exchange)` where `exchange` belongs to an **authorized bounded local owner**. The actual `DemoPlant` adapter retains its owner-check callback, 1 ms Light integration, finite budget, parking boundary/cone contacts, steering slew and controlled reset. W/Up = throttle, S/Down = brake, A/Left and D/Right = steering, Space = drive/pause, R = reset. Focus loss inhibits drive, drops held commands and requires explicit resume. The original scripted physical checks are included as `manual/src/test_drive.py`, for use only with a legitimate guarded exchange. No fake owner or unguarded local launcher is supplied.

Drive timing uses a modeled rectangle at rest with its foremost point 0.30 m behind gate 0 and the finish gate 75 m away. Equal rear wheel-side request = 500 N·m each, no front drive, steering or braking; pack starts at 9 MJ. Stop at the first accepted tick crossing the finish or the bounded 8000-tick horizon. Compute gate time and speed consistently by existing interpolation. For both arms report launch-to-first-accepted-finish-endpoint pack energy delta; if reporting gate-to-gate energy, interpolate both energy endpoints and label that separate metric. Preserve the 10 ms sampled limit flags and 1 ms pack-energy endpoint distinctions. Do not compare an incomplete or model-refused branch to a valid finish as a successful lap.

The drag producer still requires a genuine supervised child owner; `drag_verify.py` is the original independent all-tick replay implementation, not a looser alternative. The original host-specific parent/bootstrap, authorization, resource/session/lease policy and private `GO` files are intentionally **not exported**. To run the public synthetic experiment, an execution owner must register these exact new source/data identities through the normal reviewed source-family and fresh finite approval procedure, retain its original idle/session/guard, one-owner and cleanup checks, and invoke the existing producer and two full replays. Nothing here authorizes replacing, weakening, fabricating or bypassing that route. These source-only files do not establish runtime playability or 75 m numerical parity.

## Exact prior internal benchmark reproduction

The previous model's reported drag time, live driving traces and current held-out/course results cannot be exactly reconstructed from this public package. Exact reproduction would require the separately authorized whole input bytes for the intended source family, including the original course/cones, full model and historical fixture provenance, matching runtime owner and a fresh admitted run/replay. The public synthetic configuration preserves the numerical physics values used for the clear fixed-speed check but is intentionally not that original source/mission identity. Never relabel the generated stadium as Michigan or a benchmark calibration.

## Third-party and licensing

No bundled third-party native libraries, FileLock distribution or user files are copied into this export. The public validation paths use Python's standard library; the UI uses Tk when present. Some reused full-project utility modules have optional workbook-loading dependencies for unrelated modes, not these tests. This bundle does not grant a new third-party or project license; existing repository owner licensing terms apply. Review license and any new integration dependency before adding it to a distribution.
