# Rear-drive control study

This lab executes the imported ENME408 controller against the existing
four-wheel dynamic plant. It assumes two independent rear actuators. That is
a synthetic experiment, not confirmation of the current car's motor count.
New basic sessions still use the separate dynamic bicycle; prescribed-path
lap records keep their own solver.

## Run and compare

After the documented repository setup, open the desktop **Four-wheel lab →
Controlled A/B study**, or the browser **Torque control** page. Choose Launch,
Corner exit, Split grip, Rear actuator loss, Near-empty pack, Full-pack braking,
Pedal overlap, Stale sensors, Delayed and reordered, or Controller restart.
Run the matched comparison. Both strategies share driver inputs, plant,
sensor realization, clocks and physical limits. Only allocation strategy changes.
Default launch may produce identical outcomes; traction limiting is not assumed
to improve every metric. Inspect distance/speed together with slip, energy,
unmet command and the raw driver/contact-force proxy error. Unmet propulsion
and rejected regeneration have separate nonnegative command-stage magnitudes
and time integrals; rejection is measured before actuator response lag. Actual
torque, contact forces and pack energy remain separately recorded. Raw eligible
regeneration is derived from the last causally available measured driver sample
before enable/validity/freshness supervision, so rejected stale/invalid/disabled
requests remain inspectable while guarded and limited commands stay zero.

Desktop and browser can save comparison JSON and open it for checked replay.
Both stored runs execute again before the imported result appears. Imported
controls are read-only; **New preset** begins a new editable comparison.
Browser CSV exports sampled results for both strategies. Inspect JSON for
controller events, rejected sensor arrivals, raw candidates and fault reasons.
Desktop cancellation also interrupts checked imports at a plant boundary,
between the two stored runs, or during result verification. A cancelled import
discards its partial or queued result, leaves Save and Inspect unavailable,
and permits another load or a fresh run. The replay Python APIs accept the same
optional cancellation callback as execution; saved schemas and numeric checks
are unchanged. Editing a new preset clears its old result. Desktop calculation
runs in a worker; Tk rendering stays on Tk's
own thread. Browser calculation runs in a Python Web Worker, requires the pinned
scientific-runtime CDN on first use and executes the Python backend only.

Headless Python commands from the checkout:

```text
python -m lapsim.experiments.control_study --case split_grip --output comparison.json
python -m lapsim.experiments.control_study --replay comparison.json
python -m lapsim.experiments.closed_loop --output launch.json
python -m lapsim.experiments.closed_loop --replay launch.json
```

Use a new output path to retain previous evidence. The paired CLI defaults to
one second; UI studies allow 0.1–2 seconds. The lower-level runner has an explicit
four-second/work-budget ceiling. Saved scenarios contain all SI parameters,
integer clocks, source identities, model/profile/topology/backend IDs and solver
policy. Replay checks the numeric record and reports source-identity agreement
separately. JSON content hashes detect accidental edits; they do not authenticate
a publisher.

Both headless CLIs bound the actual file read (20 MB for a single run/scenario,
40 MB for a comparison), including files that grow after selection. Output
uses a unique sibling temporary file and atomic replacement; a partial write
or failed replacement preserves the previous destination and removes the
temporary file. Concurrent writers use separate temporaries. A filesystem may
refuse an overlapping replacement, which is reported as an error while a
complete saved record remains. Replay output cannot alias its input, including
through a hard link.

## What the loop calculates

At each integer boundary the runner applies reset, samples sensors, delivers due
messages in arrival order, rejects invalid epochs/duplicates/out-of-order data,
then calls the controller once when due. It holds that command through pure RK4
plant stages. Logging never advances controller or plant state. The controller
receives its declared sampled body velocity, yaw, wheel speeds and driver inputs;
it receives no true road grip, tire loads, tire force or plant object.

The Python adapter incrementally executes the original allocator, command guard,
trusted pedal-clear, fault/recovery and clock owners. Equal split uses the same
bounded allocator as the traction strategy. Traction limiting estimates wheel
slip from available sensors and reduces each rear wheel's allocation capacity;
there is no yaw allocator in this first study.

The actuator applies motor peak/current/speed limits, inverter current, gearing
and direction-dependent losses, availability, shared pack voltage/current/power,
remaining energy and regeneration headroom. Lag and slew are explicit states.
The ideal constant-voltage pack is not a thermal/electrochemical battery model.
The supervisor's final inhibit resets abstract actuator response memory immediately;
ordinary valid commands retain lag. Friction brakes remain independently available.
Full-pack braking therefore cannot silently credit regenerative energy.

The plant integrates wheel rotation and slip: applied torque divided by radius
is not achieved tire force during wheel acceleration. The energy ledger and
driver/contact proxy-error integrals use the same RK stages as the physical
states. No post-solve SOC clipping is used. Wheel/reflected motor inertia is
owned once by the wheel-inertia parameters. See the frozen
[execution contract](closed_loop_execution_contract.md) and
[four-wheel model](four_wheel_dynamics.md) for equations, units and limitations.

Solver policy 2 resolves braked-wheel stops with bounded adaptive RK trials,
an explicit <=1e-9 rad/s stop event and separately recorded remaining kinetic
energy. The controller/sensor/logging clocks do not advance during trials.
The exact accepted launch from source `85076f1` remains a regression fixture;
the repaired near-stop counterexample has an energy-refinement test. Current
closed-loop records use v3, which adds separate rejected-regeneration accounting
and verified native build/toolchain identity. Earlier unreleased development v1/v2 records explicitly
require their recorded source; the separate legacy lap/bicycle schemas retain
their existing replay paths.

## Native C against the same PC plant

An optional GCC/Clang-compatible host compiler builds all five unchanged C owners.
The new runtime builder preserves a compiler launcher's final filename and
retains the command, source hashes, compiler version and binary hash:

```text
python -m lapsim.experiments.native_controller --cc gcc --output-dir work/native-attempt-1
python -m lapsim.experiments.closed_loop --backend native_c --native-library work/native-attempt-1/lapsim_controller.dll --output native-launch.json
python -m lapsim.experiments.closed_loop --replay native-launch.json --native-library work/native-attempt-1/lapsim_controller.dll
```

The library suffix is `.dll` on Windows and `.so` on other supported hosts.
Use the builder's actual returned filename. Native results come from C owners;
Python does not supply their numeric outputs. Artifact identity is checked on
replay. Keep the builder's adjacent `build.json` with the library when copying
it. Loading verifies its binary hash, complete current C/header hashes and frozen
numeric/compiler recipe before native execution. Compiler invocation/version,
arguments and source hashes are bound into the recorded native build identity.
This receipt is reproducibility evidence, not a signed attestation. A missing
compiler/library/receipt fails explicitly. The ordinary desktop and
browser demo does not require a native compiler.

## Virtual STM32F405

The bench-only firmware links those same five C owners with vector table,
startup, linker script and a bounded emulated USART1 adapter. Binary64 arithmetic
uses software floating point (`-mfloat-abi=soft`); the F405's single-precision FPU
does not silently change the numerical contract. The generic QEMU
`netduinoplus2` board is not the team's custom PCB.

Qualified local tool versions: GNU Arm Embedded **12.3.Rel1 / GCC 12.3.1** and
Windows QEMU **11.1.0** (publisher build
`v11.1.0-12130-ge470268ff4`). Install/extract optional tools locally under their
licenses; they are not bundled with the basic demo. CI separately installs the
pinned Ubuntu QEMU package `1:8.2.2+ds-0ubuntu1.18`; its actual boot/vector/plant
result must pass before that route is called qualified. Both emulator version
and executable hash are recorded. Research reference:
[Ubuntu package](https://packages.ubuntu.com/noble-updates/qemu-system-arm).

```text
python scripts/build_stm32_bench.py --toolchain-dir PATH_TO_GNU_ARM_12_3 --output-dir work/firmware-attempt-1
python quality/run_stm32_bench.py --qemu PATH_TO_QEMU_SYSTEM_ARM --elf work/firmware-attempt-1/lapsim-f405-bench.elf --output-dir work/virtual-attempt-1
python -m lapsim.experiments.closed_loop --backend qemu_stm32f405 --qemu PATH_TO_QEMU_SYSTEM_ARM --firmware work/firmware-attempt-1/lapsim-f405-bench.elf --output virtual-launch.json
python -m lapsim.experiments.closed_loop --replay virtual-launch.json --qemu PATH_TO_QEMU_SYSTEM_ARM --firmware work/firmware-attempt-1/lapsim-f405-bench.elf
```

The build CLI anchors a relative toolchain path to the caller's directory while
preserving its invocation spelling, including an existing Windows 8.3 short
path. A deeply nested canonical Windows path can exceed GNU's internal header
lookup path limit even when the header exists. Passing the existing short path
avoids that failure; the receipt retains the invoked compiler path and hashes
the same executable. No toolchain copy or system-wide short-name setting is
required. The canonical long-path spelling can still fail in that toolchain.

These commands open only owned emulator standard pipes. They do not enumerate,
connect to or flash physical hardware. Commands are bounded by a versioned frame,
session/sequence, little-endian binary64 payload, CRC32 and whole-frame timeout.
The binary frame is carried as lowercase hexadecimal with per-character credit:
a retained Windows reproduction showed raw carriage-return bytes stalled the
uncredited stdio adapter. This transport repair leaves controller arithmetic
unchanged. A failed transaction closes the target and never returns a Python
fallback or stale command. See [protocol v1](stm32_bench_protocol_v1.md).

The build retains ELF/map, section sizes, compiler output and source/build hashes.
Actual validation retains known vectors, boot/version identity, UART transcript,
common-PC-plant comparisons and fault injections. The 8 KiB stack reservation is
a linker region, not a measured whole-system stack proof. Emulator speed is not
STM32 worst-case execution time.

| Interface / claim | Evidence and limit |
| --- | --- |
| Cortex-M4 / generic F405 image | Actual instruction execution and known-vector comparison |
| USART1 | Explicit generic QEMU data adapter, no production pin/baud/interface claim |
| Clock / reset | Software controller clock and protocol session/reset tests; no PCB clock verification |
| CAN, USB OTG, DMA, watchdogs | No implementation or success claim; QEMU support is incomplete |
| Physical PIL / SWD | Not performed; no physical backend is enabled |
| Production torque / safety / calibration | Unavailable; synthetic software experiments only |

Primary sources accessed 16 October 2026:
[QEMU STM32 models](https://www.qemu.org/docs/master/system/arm/stm32.html),
[QEMU board source](https://github.com/qemu/qemu/blob/v11.1.0/hw/arm/netduinoplus2.c),
[USART model source](https://github.com/qemu/qemu/blob/v11.1.0/hw/char/stm32f2xx_usart.c),
[QEMU downloads](https://www.qemu.org/download/),
[Windows publisher](https://qemu.weilnetz.de/w64/), and
[GNU Arm 12.3.Rel1](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads/12-3-rel1).
QEMU master documentation identifies a development revision; the installed
release's actual machine list, executable identity and boot tests provide the
execution evidence.
