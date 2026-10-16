# STM32F405 development, digital target and processor-in-the-loop

16 October 2026. **Generic virtual bench implemented; physical E11–E12 work remains unvalidated.** [Work plan](../ENME408_IMPLEMENTATION_PLAN.md) · [controller contract](controller_testing_contract.md) · [issue #19](https://github.com/LucasKazaki/lapsim/issues/19).

A generic F405 bench image, startup, linker script, bounded USART protocol and
QEMU host backend now execute the same five C owners against known vectors and
the common PC plant. See [the executable lab guide](closed_loop_lab.md) and
[wire contract](stm32_bench_protocol_v1.md). The remaining path below retains
the distinction between virtual execution, custom-board work and physical PIL.

## 1. Recommendation

Keep the controller core portable and test it on the PC first. Add a linked, bench-only MCU adapter and a bounded emulator experiment. Then run the same controller on an explicitly selected, isolated STM32 while the vehicle remains simulated on the PC. A complete digital twin of the custom PCB is not a prerequisite for useful controller experiments.

The recorded platform is STM32F405/custom PCB. Exact suffix/revision, schematic, pinout, power arrangement, clocks, startup/bootloader, current firmware/toolchain and available connectors are not yet supplied. Do not select those by guessing. A generic/emulated F405 target must be labeled separately from the team board. There is no need to change the project to Teensy.

## 2. Evidence levels

| Level | What actually executes | Claim allowed | Claim not established |
|---|---|---|---|
| Model/reference | Python controller and synthetic plant | Algorithm/scenario behavior within model assumptions | C implementation or target execution |
| Native SIL | Compiled C core on host and PC plant | Host implementation/reference comparison | STM32 instructions, peripherals or deadlines |
| ARM build | Linked MCU bench image, or explicitly only objects | Build/link evidence for declared target/ABI | Execution, complete resource fit from isolated objects, timing |
| Emulated target | MCU firmware on an identified emulator/platform model | Executed instruction/interface behavior within modeled support | Exact PCB behavior, physical CAN/USB or cycle-accurate timing |
| Lockstep PIL | Real STM32 controller; PC waits and advances simulated plant | Real-device functional execution with recorded logical inputs | Hard real-time HIL, inverter operation or physical car validation |
| Real-time isolated HIL | Target plus controlled timed plant/I/O bench | Measured timing/transport behavior within that bench | General safety certification or vehicle performance without additional evidence |

The existing [Studio #77](https://github.com/LucasKazaki/lucas-agent-studio/pull/77) native replay and [#78](https://github.com/LucasKazaki/lucas-agent-studio/pull/78) object evidence are upstream inputs to E02, not completed PIL. Import their source/contracts and preserve historical receipts. Extend rather than rebrand them.

## 3. Toolchain and linked firmware

Official ST documentation identifies the F405-family Cortex-M4 with a **single-precision FPU** [S1]. Current binary64 controller arithmetic may require software support for double operations. Do not replace it with float32 to claim a faster port without explicit numeric-contract changes, reference tests and boundary/fault analysis. Record ABI, floating-point mode, compiler and optimization flags; avoid unreviewed fast-math transformations.

Provide a reproducible build preset using an explicitly pinned toolchain. ST's STM32CubeCLT and STM32CubeProgrammer are official command-line-oriented options [S2,S3]; the team may already have another supported toolchain. Retain IDE project files when useful, but the build must not depend on one person's GUI workspace.

Recommended tree after E02, subject to existing imported layout:

```text
controller/                  canonical imported core, reference tests and provenance
firmware/bench/              linked bench harness; no live actuator transmission
firmware/boards/             approved or explicitly generic target definitions
firmware/toolchains/         pinned build configuration and installation notes
emulation/                  platform scripts, coverage table and smoke scenarios
src/lapsim/...              host backend adapter alongside existing runner code
```

These are target locations, not files claimed to exist today. Keep platform I/O outside the numerical core. No heap allocation or unbounded work in the control step without a documented reason/resource contract. Audit startup, linker script, vector table, runtime helpers, libraries and memory placement. Preserve `.elf`, link map, section sizes, compiler flags, source hashes and warnings for a reviewed build. Compiler-local stack frames are not a whole-system stack bound, and an object file is not a linked firmware image.

A bench build exposes controller request/reply only. Do not link the team's live CAN torque-output path into it by default. Board-specific initialization must have reviewed pins/clocks/power assumptions. A generic emulator build may replace unsupported platform I/O at the adapter boundary, but must use the same controller core and identify those substitutions.

## 4. Digital-target options and their limits

### QEMU: bounded initial F405 experiment

The upstream STM32 documentation accessed October 16 lists `netduinoplus2` and `olimex-stm32-h405`, both described with STM32F405RGT6. It documents USART/timer and limited RCC support but lists CAN, USB OTG, DMA, watchdog and other peripherals as missing [S4]. This is **not** a ready digital copy of the team's custom board.

The cited page is the QEMU development manual, identifying itself as 11.1.50 when accessed. The agent must select and record an installed released version/commit, run its machine listing and check that the intended model/features actually exist. Do not assume development documentation exactly matches an older binary.

First experiment: link a minimal bench image, start it on the supported model, exchange fixed test vectors over a supported serial/semihosting interface, and compare controller results/state with the host reference. Add reset and malformed-frame tests. Only then attach the PC plant. Any semihosting/serial shortcut is an explicit bench transport, not simulated ADC/CAN/USB validation. Do not patch missing peripherals to return successful values merely to make production startup appear supported.

Acceptance: exact emulator version/platform description/firmware hashes, actual command/output logs, executed tests, unsupported-peripheral list and no claim of real-time deadline evidence. A file that compiles but never boots is not an emulation pass.

### Renode: alternative after a platform audit

Renode has STM32F4 Discovery platform examples and host UART integration [S5,S6]. A Discovery example is not proof of custom-F405 equivalence. UART socket bridging can support a host adapter; its PTY integration is explicitly Linux/macOS only. SocketCAN integration is documented as Linux-only [S7]. Do not build a Windows-first promise around a Linux-only bridge.

Evaluate one small scenario, document exact peripheral coverage/version and choose one maintained emulator path. Do not maintain two large emulators or attempt a complete PCB reconstruction before native SIL works. Emulator models are development tools; neither their CPU settings nor wall-clock speed establish target WCET.

## 5. Real board connection: two separate paths

Programming/debugging and simulation data transport are different interfaces:

```text
PC -- USB --> ST-LINK -- SWD --> verified STM32 board      (program/debug)
PC -- USB serial bridge --> board UART                    (bench data)
                 OR
PC -- native USB CDC --> board firmware                   (only if supported/wired)
```

ST-LINK variants such as STLINK-V3MINIE expose SWD and a virtual COM interface to a target UART [S8]. This is a capability reference, not a purchasing requirement or proof that the available team probe supports VCP. A bare USB cable connected to a custom PCB does not automatically provide flashing and serial data. Native USB CDC requires supported board wiring, clocks, firmware and enumeration; SWD normally needs an appropriate probe and verified connector.

Before a physical connection, the team must supply/confirm the target board ID, MCU suffix, schematic/connector pinout, voltage/reference and grounding, power method, reset/boot handling, accessible SWD/UART or USB routing, and an authorized firmware/restore path. Follow board/probe instructions; do not infer wire colors or use an unverified power pin. Keep the board off the vehicle with inverter/traction connections physically absent for this bench. No HV system is needed.

Software should list candidates read-only and require an explicit device/port and mode selection. `Connect`, `Build`, `Flash` and `Run PIL` are distinct actions. Do not auto-flash on clone, startup, USB insertion or normal tests. Flashing requires explicit authorization for that verified board/image; do not erase an unknown team controller or alter option bytes as a workaround.

## 6. Proposed bench protocol

Design and test the framing before implementing target I/O. This is a bench protocol, not an invented team CAN DBC.

Handshake identifies protocol/schema version, firmware/core build hash, numeric contract, supported message sizes, board/backend capability and a fresh session/epoch. Refuse incompatible versions or unrecognized firmware identity. A hash identifies an artifact; it is not authentication of an untrusted device.

Messages contain an explicit bounded payload length, type/version, sequence number, session ID, logical tick/time base, validity/freshness fields and integrity check. Define byte order, integer ranges and numeric encoding; never transmit compiler-native C struct padding. Freeze golden encoded packets on both implementations. Start with a simple bounded binary format or another explicitly specified encoding; do not introduce an unbounded parser on the MCU for convenience.

Requests carry the normalized sensor/demand snapshot and explicit simulation timing. Replies carry the echoed sequence/epoch, controller status, proposed and accepted command, reasons/latch/recovery state and optional target execution timing. Preserve the existing core ABI through an adapter. Reject duplicate, old, reordered, truncated, oversized, malformed or incompatible messages under a declared policy. CRC checks detect accidental corruption, not malicious sender identity.

Use lockstep initially: the host sends tick N, receives and validates reply N, applies it only to the simulated plant, then advances. A timeout pauses/aborts the experiment and records the failure; it must not silently reuse a stale nonzero command or switch to Python. A reconnect starts a new session with an explicit controller-state reset/reinitialization policy. Keep simulation logical time, MCU monotonic time and host wall time separate.

Opening a serial port may affect reset-control lines on some adapters; make line behavior explicit and test the actual device. Test target reset during a step, device removal, wrong port/device, blocked reads, host cancellation and cleanup. Bound I/O buffers and waits. Do not run this on the UI event loop.

For the first physical fixture, keep all outputs as data returned to the PC. A propulsion inhibit has a defined controller/runner response but does not imply a universal whole-vehicle safe state or erase independent friction braking.

## 7. Timing and later CAN/HIL

Lockstep tests can be slower than real time and remain useful functional evidence. For real-time tests, separately measure controller execution, communication latency, deadline misses, interrupt interference and jitter against team-derived requirements. Do not choose a board period solely from a host throughput benchmark. A serial round-trip distribution is not WCET.

Later isolated CAN work requires real DBC/IDs, bitrate, transceivers, power/termination, clocks, message ownership, watchdog/freshness rules, fault handling and a reviewed bench. Internal/silent loopback checks do not validate the external bus, arbitration, ACK, wiring or inverter interpretation. Review the exact silicon reference manual/errata and firmware driver behavior before relying on hardware timestamps or retransmission; do not assume retransmission makes an old torque request fresh. This plan does not approve normal-mode vehicle CAN transmission.

Keep separate acceptance records for native SIL, emulator, actual PIL, target timing and external CAN/HIL. Mocked drivers can verify host error handling but do not satisfy physical test rows.

## 8. Definition of done and current blockers

Software work possible now: migrate the controller, define/test the host backend/protocol, create a generic linked bench configuration, audit an emulator's supported peripherals, and run synthetic host/reference experiments.

Blocked until board/interface evidence exists: claim of a team-board build, verified wiring/power, flashing that board, native USB availability, actual target execution/timing and CAN integration. Record these blockers in issue #19; do not mark the entire software project blocked.

PIL completion requires an actual board run with source/image/device identity, input/reply logs, unchanged logical scenario, reference comparison, fault/reset/timeout cases, timing labels and no physical actuator connection. Real-time HIL is a later gate.

## 9. Primary sources, accessed 16 October 2026

- **S1:** [ST STM32F405RG product documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f405rg.html): family core/FPU and SWD/UART/USB capability. The RG example is not a confirmed team part suffix.
- **S2:** [ST STM32CubeCLT](https://www.st.com/en/development-tools/stm32cubeclt.html): official command-line toolset entrypoint. Pin the actual installed version and licenses.
- **S3:** [ST STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html): official programming tool. Programming and simulator transport remain separate.
- **S4:** [QEMU STM32 board documentation](https://www.qemu.org/docs/master/system/arm/stm32.html): supported model names and explicit missing-device list; development-manual caveat above.
- **S5:** [Renode STM32F4 Discovery platform](https://github.com/renode/renode/blob/master/platforms/boards/stm32f4_discovery.repl) and [example script](https://github.com/renode/renode/blob/master/scripts/single-node/stm32f4_discovery.resc): starting references requiring exact platform/version review.
- **S6:** [Renode UART host integration](https://renode.readthedocs.io/en/latest/host-integration/uart.html): socket/PTY integration and platform restrictions.
- **S7:** [Renode CAN host integration](https://renode.readthedocs.io/en/latest/host-integration/can.html): Linux-only SocketCAN bridge; not custom-board validation.
- **S8:** [STLINK-V3MINIE documentation](https://www.st.com/en/development-tools/stlink-v3minie.html): SWD/programming and virtual COM-to-UART capability.

These sources support tool capability, not a claim that any tool was installed or hardware test performed for this handoff. Vendor toolchains/binaries should be obtained under their licenses rather than copied into Git without a redistribution review.
