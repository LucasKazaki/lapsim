# Provisional drivetrain and STM32F405 virtual bench — 27 October 2026

This E10 readiness pass starts from merged main
`a37f8b82dba3b105fd85a3f4e834584345d8141f`. It reuses the existing deterministic
controller and bench firmware. It does not replace the frozen GPU search,
recalibrate the car, or publish new website data.

## The 2027–2028 gear ratio

[The versioned partial specification](../configs/team_specs/team-2027-2028-provisional-v1.json)
records Lucas's team update at 04:19 UTC: **tentative 12.48:1**. The model
interprets reduction as motor revolutions per driven-wheel revolution. The team
must confirm that this is the total reduction across all stages.

Motor base/maximum speed, vehicle top speed, gear efficiency and topology are
explicitly unknown (`null`). This partial specification is **not a runnable
vehicle profile**. It rejects invented values in these unknown fields. The
existing synthetic vehicle profiles and searched controllers retain **4:1**;
their optimality for the provisional ratio has not been established.

The production actuator uses `omega_motor = ratio * omega_wheel`. For positive
wheel torque, `T_motor = T_wheel / (ratio * efficiency)`; for regeneration,
`T_motor = T_wheel * efficiency / ratio`. Commands and speeds at this boundary
are wheel-side N·m and rad/s. The single-motor open differential, spool and
independent-motor architectures remain distinct.

## Inspect or reproduce the ratio-only diagnostic

Use an already provisioned project Python environment from the checkout root.
An uninstalled checkout needs `PYTHONPATH=src`; no installer or download is
invoked by these commands.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m lapsim.torque_configurator.team_spec
python -m lapsim.torque_configurator.team_spec `
  --synthetic-base configs/torque_profiles/synthetic-four-awd-v1.json `
  --assume-synthetic-unknowns --actuation-probe `
  --output-dir work/ratio-demo-new
```

The second command requires an explicit acknowledgement of synthetic assumptions.
It creates a new directory containing `profile.json`, `source-spec.json`,
`provenance.json` and `diagnostics.json`. Existing output directories are refused.
The new full profile is simulation-ready synthetic data, while its source team
specification remains incomplete. Every non-ratio parameter is inherited from
the named synthetic donor and recorded as an assumption. Profile/source hashes
identify the exact inputs; no historical file is edited.

The bounded diagnostic calls the real `constrain_actuation` function, keeping
wheel speed, commands, SOC and topology matched. It checks these relationships:

| Probe | Expected effect of changing 4 to 12.48 |
| --- | --- |
| Unsaturated propulsion and regeneration at 10 rad/s | Same requested wheel torque is feasible; motor speed rises by 3.12 and motor torque/current falls. Equal wheel outputs are legitimate. |
| Very large request at zero wheel speed | Synthetic current/torque constraints bind; achievable wheel torque rises by 3.12. |
| 60 rad/s wheel speed | The donor's assumed motor maximum speed cuts off the higher-ratio case. This is not a real-car top-speed estimate. |

These checks do not predict lap time or thermal performance. No new full-lap
campaign was run for the provisional hardware.

## The C programming and virtual target path

The shared portable C owners are under
[`controller/reference/native`](../controller/reference/native). Their contract,
clock, pedal, guard and allocator modules are compiled for both the host library
and the ARM image. [`native_controller.py`](../src/lapsim/experiments/native_controller.py)
and [`stm32_backend.py`](../src/lapsim/experiments/stm32_backend.py) adapt them to
the existing simulator controller interface. They retain requested, guarded and
achieved output/fault state; there is no silent emulator-to-Python fallback.

The bench entry point is [`firmware/bench/main.c`](../firmware/bench/main.c), with
explicit startup and linker files in the same folder. Its generic F405 QEMU
target exchanges bounded, CRC-checked, sequenced binary64 frames through emulated
USART1. A fresh session, validated firmware/build identity and fixed policy
handshake are required. Returned wheel torque is data for the PC plant;
it is **not an inverter/CAN command**.

Current bench parameters are synthetic reference values:

| Setting | Value and boundary |
| --- | --- |
| Controller period | 10 integer ms; controller clock is separate from plant substeps |
| Maximum sample age | 50 ms in this firmware; incompatible adapter settings are rejected |
| Command rise limit | 8,000 N·m/s on the wheel-command guard |
| Pedal overlap trip / clear | 0.25 / 0.05 normalized pedal thresholds |
| Recovery requirement | Two healthy observations after inhibition |
| Numeric contract | Binary64, ordinary nearest rounding, retained subnormals, no fast math; ARM soft ABI |

The C bench supports **propulsive reference control**. Negative drive requests
are outside its accepted contract. The tournament's regenerative and genetic
policies remain simulation code; they have not been ported to this firmware.
Changing a Python vehicle gear ratio does not reprogram an inverter or calibrate
this controller. See the [STM32 development boundary](stm32_development_path.md)
before any later board work.

## Reproduce the bounded build and run checks

This pass found and reused installed tools; it installed nothing:
host MinGW GCC 12.1.0, Arm GNU 12.3.Rel1 / GCC 12.3.1, and QEMU 11.1.0.
Executable hashes and privacy-safe receipts are in the
[acceptance evidence](evidence/ev-readiness-20261027.json).

Select the actual installed paths on the machine before running. The ARM build
requires the declared GNU version; QEMU must support `netduinoplus2`.
The guide deliberately does not depend on another checkout's absolute location.

```powershell
$PythonExe = (Get-Command python).Source
$HostCompiler = 'C:\path\to\gcc.exe'
$ArmToolchain = 'C:\path\to\arm-gnu-toolchain-12.3.rel1'
$Qemu = 'C:\path\to\qemu-system-arm.exe'

scripts/run_ev_readiness_guarded.ps1 -Phase host-build -Attempt morning `
  -PythonExe $PythonExe -HostCompiler $HostCompiler
scripts/run_ev_readiness_guarded.ps1 -Phase arm-build -Attempt morning `
  -PythonExe $PythonExe -ArmToolchain $ArmToolchain
scripts/run_ev_readiness_guarded.ps1 -Phase virtual-check -Attempt morning `
  -PythonExe $PythonExe -Qemu $Qemu `
  -Firmware work/ev-readiness-20261027/arm-build-morning/lapsim-f405-bench.elf
scripts/run_ev_readiness_guarded.ps1 -Phase tests -Attempt morning `
  -PythonExe $PythonExe -HostCompiler $HostCompiler
scripts/run_ev_readiness_guarded.ps1 -Phase package-check -Attempt morning `
  -PythonExe $PythonExe
```

Run phases serially. Each requires a new attempt name and preserves stdout,
stderr and a guard receipt under `work/ev-readiness-20261027`. The short CPU
bench admits only with 8 GiB commit reserve plus a 0.75 GiB allowance, checks
the unchanged 8 GiB floor and a 180-second phase limit, and can stop only its
owned process tree. Heavy simulation/GPU admission remains in its original
launcher with its original reserve/allowance. Do not use this short bench guard
to launch tournaments. Coordinate with other project jobs before execution.

`package-check` performs a setuptools `build_py` resource bundle, not a Windows
installer or frozen executable release. Its allowlist now includes all four
synthetic configurator profiles and the provisional partial specification.
An isolated import of the actual copied package was checked separately, with
the source checkout excluded from `sys.path`.

## What actually passed and what remains

The machine linked the ARM ELF and booted it in QEMU, rather than treating a
host C test as emulation. Measured evidence includes:

- Host DLL build and ARM Cortex-M4 link: exit 0, warning-as-error flags.
- Actual QEMU: 30 known vectors exactly matched Python reference output;
  launch and overlap PC-plant comparisons each matched 10 controller calls
  across 100 plant ticks. Maximum recorded energy residual was
  `2.83e-9 J`.
- Nine actual protocol/lifecycle fault cases passed, including stale sessions,
  duplicate sequence, malformed frames, process loss and explicit recovery.
- Focused regression counts, package checks, exact identities and resource
  minima are recorded in the evidence file. The Windows-only/POSIX-only scopes
  and the retained initial test-fixture correction are explicit there.

**Not established:** physical STM32 execution, target WCET/deadlines, a
peripheral-complete emulator, custom PCB startup/clocks/pinout, CAN/inverter
protocol, real vehicle calibration or firmware regeneration of searched policies.
No board, motor or vehicle was connected or flashed. Generic QEMU UART behavior
is not evidence for real CAN, DMA or interrupt behavior.

The next team inputs are the actual firmware project and board/clock/linker
definition, CAN/inverter message contract and units, torque/sensor limits and
deadlines, motor maps/speed limits, gear efficiency, architecture and confirmation
of the total 12.48 reduction. Until then, the delivered guide and virtual bench
are reproducible development tools, not deployment-ready car firmware.

The frozen GPU results remain unchanged. No new search or GPU workload was
needed; the exclusive heavy slot was released for chess. Public website
publication remains on hold independently of this source PR.
