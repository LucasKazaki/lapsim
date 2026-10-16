# TC-03A - team evidence packet and source-specific patch gate

Status: portable evidence/handoff reference only. Target remains the 2027-28 Terps Racing EV torque-control project. No vehicle-specific torque, CAN, watchdog, timing, motor/inverter, sensor, firmware, HIL or rule-compliance value is asserted by this packet.

## Decision

The next safe step is evidence collection, not a more detailed controller model. A source-specific STM32 instrumentation patch should not be prepared until the exact firmware build can be identified and reproduced without flashing a vehicle.

TC-02C captured many useful board/firmware fields, but it did not make the build command and working directory explicit readiness gates. TC-03A adds a separate, backward-compatible request schema named enme408-team-evidence-request/v1. The previous evidence schema remains untouched.

The new readiness gate requires evidence for:

- exact STM32F405 part number, package and board revision;
- firmware repository/reference and exact revision;
- build working directory and exact build-only command;
- toolchain, compiler version and linker script;
- verified SYSCLK, HCLK, APB1 and APB2 values plus their configuration source;
- startup/system-init/reset-cause ownership files;
- watchdog ownership;
- logging sink and timestamp source;
- CAN message-map reference;
- the actual control-path files; and
- at least one attributable team/build/schematic/manual source.

Optional fields remain optional. A packet can be structurally valid while incomplete. The validator returns every missing readiness item instead of inventing defaults.

## Why these fields gate the patch

A build command and exact source revision are needed to show that an instrumentation-only candidate still builds from the same code base. Clock evidence is needed before converting raw counter differences into time. Startup/reset ownership is needed before proposing reset-cause capture. CAN ownership and the message-map source are needed before any receive-age or error-state hook is placed. Logging ownership is needed before selecting where measurements can be retained.

No acceptance threshold is created here. The packet says when there is enough evidence to write a source-specific build-only patch, not when the resulting controller is safe or competition-ready.

## Current primary-source boundary

ST currently lists RM0090 V22.0 for the STM32F405/415 family, updated 28 May 2026, PM0214 V11.0 updated 27 February 2025, and ES0182 V19.0 updated 19 July 2026:
https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html

These family documents identify available MCU mechanisms but do not identify the Terps Racing package, board wiring, firmware clock tree, CAN use or debug configuration.

SAE's official 15 September 2026 announcement says the 2027 Formula SAE Rules are published and that Formula SAE Electric is scheduled for 1-5 June 2027:
https://www.fsaeonline.com/cdsweb/app/NewsItem.aspx?NewsItemID=219f84d4-72a6-4672-9125-7f69d790ae3a

The July 2026 public-comment draft explicitly says it is a draft and may differ from the final rules. Do not use draft clauses as final compliance evidence. The final rule body was not retrieved in this pass, so rule_compliance_verified must remain false.

## Portable verification

Environment: Python 3.13.5, Linux x86_64, standard library only.

Commands:

    python -m unittest -v test_team_evidence_packet.py
    python -m py_compile team_evidence_packet.py test_team_evidence_packet.py

Observed: 15/15 tests passed, 0 failed, 0 skipped; py_compile exited 0.

Coverage includes an intentionally empty valid template, a fully synthetic readiness example, build-command and MCU-part gating, rejection of zero/boolean clock values, zero CAN bitrate, duplicate CAN names and control files, malformed source SHA, unsupported source kinds, positive hardware/rules/threshold claims, wrong target car, unknown fields and JSON round trip.

The tests are portable checks of the evidence contract only. No STM32 build, firmware execution, CAN/HIL/vehicle test or native Agent Studio project execution occurred.

## Team/local-worker handoff

Populate team_evidence_request.example.json from actual team files and observations. Prefer source hashes for firmware/build outputs/schematics when permitted. Do not copy secrets or unrelated private data into the packet.

Once the validator reports ready_for_source_specific_patch=true, the next bounded task is TC-03B: reproduce the untouched firmware build at the bound revision, then prepare an instrumentation-only candidate behind a compile-time option that is off by default. Compare build result, warnings, code/data size and exact diff. Do not flash hardware, change CAN timing, change watchdog configuration or define vehicle acceptance thresholds in that task.
