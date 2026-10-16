# One-repository release and reproducibility contract

16 October 2026. **Proposed acceptance contract; not proof that a new release exists.** See [E01/E02/E05/E09/E14](../ENME408_IMPLEMENTATION_PLAN.md) and [issue #19](https://github.com/LucasKazaki/lapsim/issues/19).

## 1. Three distinct supported experiences

1. **Recipient:** download an identified `LapSim-Windows-x64.zip` from this repository's GitHub Releases, extract it and run `LapSim.exe`. No Python, compiler, API key, second repository or private bundle is needed for the public synthetic demonstration.
2. **Developer:** clone this repository, run one documented bootstrap entrypoint, then use the same physics/controller code and scenarios. State prerequisite Python/Tk and platform requirements before the command. First-time dependency installation may require network access.
3. **Embedded developer:** opt into compiler/emulator/board tooling. The ordinary application remains usable when those optional dependencies or hardware are absent. Programming a board is a separate explicit action.

Existing source startup is `setup_lapsim.cmd` followed by `launch_lapsim.cmd` on Windows; setup currently creates a virtual environment, installs dependencies and checks Tk/resources. Existing portable build and frozen self-test instructions are in [release.md](release.md). These are starting mechanisms, not evidence that a release ZIP is already published. The October 16 review found no published GitHub Release. Refresh before changing that statement.

Do not confuse the browser simulator with a fully offline package: its scientific runtime currently loads on first use. An offline desktop release is the first offline deliverable. An offline browser edition requires its own runtime licensing, vendoring, caching and acceptance work.

## 2. One-command bootstrap target

Proposed command interface, **not available merely because documented here**:

```text
python scripts/bootstrap.py --launch
python scripts/bootstrap.py --check
python scripts/bootstrap.py --extras controller-dev
```

The implementer may select another concise interface if it preserves these behaviors and updates all docs/tests. Use the script's own location to find the checkout, not the caller's working directory.

Requirements:

- Validate supported OS/architecture/interpreter and Tk/display availability. A platform-specific missing prerequisite gets an actionable error, not a false success.
- Create or validate a project-local environment. Never delete an existing environment, overwrite profiles/runs, edit global PATH, install as administrator or change machine security policy without explicit user action.
- Use a tested dependency/constraint strategy per supported Python/platform. Distinguish a flexible source-install range from the exact reproducible release-build lock. Do not promise that one wheel lock supports every OS and interpreter.
- Re-running is safe; a failed setup returns nonzero and does not leave a success marker. Use timeouts and checked subprocess return codes. Avoid shell interpolation of user-supplied paths.
- Verify public resources and run a small headless synthetic smoke test before launch; separately check Tk for desktop launch. Do not require the long full test suite every time a teammate opens the app.
- Expose environment, resource, controller-backend and version diagnostics. Do not silently fall back from C to Python while claiming native execution.
- Keep optional private evidence, MF4 tooling, native compiler, emulator, USB and CAN dependencies separate. Public synthetic startup must not probe hardware or open serial/CAN ports.
- Windows paths with spaces/non-ASCII names, a directory outside the checkout as CWD, interrupted install, read-only resource paths and absent internet after successful installation need tests.
- Document Windows as the first EXE target. Linux/macOS source/headless/UI support must be listed as tested, experimental or unsupported with actual evidence; never call a Windows EXE cross-platform.

An editor/IDE is optional. Firmware compilation must eventually have a reproducible CLI route; CubeIDE can supplement it.

## 3. Package contents and ownership

Retain the existing Windows packaging machinery rather than introducing a second packager. Required contents for an integrated team release:

- `LapSim.exe` and any approved native controller libraries needed by the selected default backend. A DLL must be built from the recorded source for the intended architecture; do not load an arbitrary library from the working directory.
- Public synthetic vehicle/scenario/course fixtures, model/controller contracts and schema versions. Package-resource lookup must work without the original checkout.
- Offline team guide, controller/STM32 plans, flow map and relevant source snapshot. Source links in the offline map must resolve locally and survive the EXE's temporary extraction cleanup.
- `build-info.json` identifying source commit, clean/dirty status, tool/dependency versions, architecture and build configuration; checksums; license/notices; verification receipt; known limitations.
- Compact reproducible reference/controller tests or a documented source package containing them. Development compilers need not be inside the recipient ZIP.

Private evidence remains opt-in outside Git. Preserve `LAPSIM_DATA_BUNDLE` with user-controlled paths; remove reliance on Lucas-specific default directories from the mandatory demo. A source bundle that is missing should remove only source-dependent choices, not crash startup.

Store writable profiles, course imports, logs and runs in a platform-appropriate user-data directory, not next to a frozen binary or inside bundled resources. Upgrades must preserve them. Show the effective data directory in diagnostics.

## 4. Publication policy

Build a versioned release from an identified reviewed commit/tag. Required CI results must correspond to the release candidate source. Preserve main/PR ancestry; do not generate a release from a dirty personal checkout.

Publish the actual ZIP, source identity, checksums and concise release notes to this repository. Distinguish source code archives, CI artifacts and user-downloadable releases. Use a prerelease label while synthetic/experimental boundaries remain. Do not auto-increment a semantic version or call the software production-ready without review.

The GitHub README and START-HERE must link to the actual artifact once it exists. Until then, advertise the source route/build instructions rather than a nonexistent EXE. Show source SHA/version in the desktop, browser, torque viewer and exported record. The separately hosted browser site must be rebuilt or clearly labeled stale; do not assume a main merge updates it.

Review project licensing and third-party redistribution, including the existing team/upstream source, Python/native dependencies, firmware headers and toolchain notices. Do not invent a license decision for the owner. Unsigned executables must be labeled; never tell recipients to disable antivirus, SmartScreen or organizational controls. Checksums support integrity comparison but do not independently authenticate a publisher.

## 5. Reproducibility repairs required before an integrated release

### Effective configuration and geometry

Use a shared UI-independent resolver for profile/model/topology, units, constraints, course identity and effective integration grid. See E05 for the concrete browser/desktop mismatch. A parity test must invoke both real adapters; calling the browser's helper twice is insufficient.

Assert source/effective geometry hashes, per-cell distances/curvature/stations and initial conditions first. Then compare outputs under declared tolerances. Preserve coherent arcs and the documented fused-track exception. Saved records must retain effective inputs, not just UI labels that later resolve differently.

### Replay and software identity

Record model version, controller source/backend, config/schema hashes, dependency environment, seed, algorithm/settings, sensor/controller/plant periods, initial states and result status. Distinguish content integrity from execution provenance: a correct hash does not prove a controller was executed.

Retain original imported receipts as immutable historical artifacts. For fresh runs, capture actual executable/library identities and commands. Do not rewrite failure receipts into successful ones or relabel Python decisions as native output.

### Historical validation reports

Audit every runnable command in the current team/release/validation docs against real paths. Fix or archive references to the absent `scripts/validate_first_endurance_lap.py`; inspect the current `analysis/endurance/` pipeline. Mark old brake-free or uncalibrated reports with date/model/input identity. Regenerate current evidence only with its required authorized data and disclose missing channels/inputs.

## 6. Acceptance matrix

| ID | Execute, do not merely inspect | Evidence |
|---|---|---|
| REL-01 | Fresh clone of this repo only; Studio directory unavailable | Bootstrap log and independent synthetic run |
| REL-02 | Fresh Windows user/VM without Python/compiler; download, extract and run the actual release | EXE checksum, OS/architecture, startup and frozen self-test result |
| REL-03 | Launch from a path with spaces/non-ASCII and unrelated CWD | Successful resource lookup, saved record and replay |
| REL-04 | No private bundle, credentials, API access or board connected | Baseline still works and hardware remains unopened |
| REL-05 | Internet disconnected after package download | Desktop demo/map/records work; browser dependency limits are honestly documented |
| REL-06 | Desktop and browser resolve matched synthetic/imported scenarios | Same effective inputs/grids and bounded numerical differences |
| REL-07 | Host reference/native backend comparison from this clone | Actual compile/load identity, outputs and fault-state comparison |
| REL-08 | Missing optional compiler/serial driver/emulator | Clear capability status; ordinary UI is not broken |
| REL-09 | Corrupted/unsupported/oversized run file and interrupted run | Safe rejection or explicit partial record; no stale result presented as current |
| REL-10 | Upgrade/relaunch with existing user profiles/runs | User data retained and schema migrations/unsupported versions explicit |
| REL-11 | Default basic model and source/profile labels | Synthetic bicycle selected for new basic dynamics sessions; old records retain original models |
| REL-12 | Link/source inventory, dependency/secret/licensing and manual UI checks | Reports with scope, unresolved items and reviewer identity |

The existing `scripts/check_all.py` isolates test modules; preserve that approach where Tk/native state makes it necessary. Existing `--self-test` uses a GUI-subsystem executable, so retain the documented Windows wait/exit-status procedure. A spawned process or absent crash dialog is not a completed passing test.

A release can claim only the matrix rows actually executed on its exact artifact. Hardware absence is an explicit limitation, not a green PIL/HIL check.
