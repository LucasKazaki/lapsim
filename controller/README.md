# ENME408 Terps Racing EV — torque control

Status: executable host reference with source-to-command replay, not a registered/running vehicle controller. See [TC-03A: control pipeline and team review](research/TC-03A-control-pipeline-review.md) for the current implementation, commands, expected fixture results, and hardware gaps. Portfolio rank: **2**, behind Sports LM and ahead of DZYNE/RSC2. Owner direction: September 30, 2026; coordination issue: LucasKazaki/lucas-agent-studio #61. Proposed runtime project ID: `enme408-torque-control`; reuse an existing matching registration instead of making a duplicate.

## Scope and retained constraints

Help Lucas understand, research, implement in simulation, test and explain an electronic differential / wheel-torque-control system. Support actual ENME408 deliverables and maintain evidence useful for advisor updates and a possible later master's proposal. Do not invent assignment deadlines or claim a master's project is approved.

User-provided context identifies the target as the **2027-28 car**, distinct from the team's current **2026-27 build**, with an existing **STM32F405 on a custom PCB**, no Teensy migration, and **U.S. Formula SAE Electric only**. The AWD/four-motor concept remains subject to actual team interface and hardware confirmation before control implementation. These constraints are not an independently inspected schematic, firmware specification or proof of available sensors.

Autonomous perception, localization, path planning, steering and driving are deferred. Do not launch an autonomy loop or let autonomy literature displace torque-control work. A later owner decision can extend the project without replacing its torque-control evidence.

## First bounded work packets

The latest host prototype adds a [portable C result contract and final gate,
with compiled Python parity](research/TC-03B-portable-c-parity.md). It explicitly
versions the shared numerical accumulation policy and preserves the original
Python-only review checkpoint. It is not target firmware or a measured MCU result.

The next portable step implements the normalized fixed-period clock owner and
composes it before the native gate; see [TC-03C](research/TC-03C-portable-clock.md)
for the frozen semantics, uint64 domain and reproducible parity scope.

[TC-03D](research/TC-03D-portable-pedal-adapters.md) adds native trust predicates
and pedal-latch adapter metadata around the external base guard. It does not
port the base guard/slew or independently authorize a torque command.

[TC-03E](research/TC-03E-cortex-m4-object-feasibility.md) records an object-only
Cortex-M4 cross-build of those unchanged C sources under two candidate ABIs.
It retains software binary64 dependencies, section/stack metadata and the
original metadata-reader failure. No firmware fit or target timing is claimed.

[TC-03F](research/TC-03F-base-command-guard.md) adds the actual portable base
guard owner for the supported offline record domain, including ordered
validation, latch progression and upward-only slew. Its C-generated proposals
are compared through the existing native pedal, clock and final gates. The
allocator and offline orchestration remain external; this new unit is outside
the historical Cortex-M4 object cohort.

[TC-03G](research/TC-03G-base-guard-object-annex.md) separately cross-compiles
that unchanged guard unit as four Cortex-M4 objects. Both candidate ABIs retain
software double-precision and external contract dependencies. The original
three-unit object experiment remains unchanged; neither experiment links or
executes target firmware.

[TC-03H](research/TC-03H-portable-allocator.md) adds the actual fixed-size C
candidate allocator and a five-unit offline proposed-command path. It preserves
the source's ordered water filling and epsilon/status quirks, including raw
candidates that the unchanged downstream contract must reject. Supported-domain
parity does not establish physical input provenance or target operation.

### TC-00 — Requirements and interface evidence

Produce a compact evidence register separating confirmed team data, user statements, assumptions and unresolved questions. Inventory actual allowed repository/source and assignment documents before writing implementation. Capture motor/inverter count and interfaces, CAN messages and units, torque/speed/sign limits, pedal/brake inputs, wheel-speed/steering/IMU availability, sample times, watchdogs, shutdown ownership, MCU firmware/build constraints, logging, and test access. Unknowns remain unknown. Verify relevant current official U.S. FSAE rules and version before making compliance claims. Obtain deadlines from actual course materials, not memory.

Acceptance: one requirements/interface table with provenance and car-year labels; a data-gap list that does not block independent research; a conservative baseline proposal; one next executable simulation task. No guessed CAN IDs, sensor availability or competition limits.

### TC-01 — Conservative baseline and offline simulator

After required interfaces and assumptions are explicit, build the smallest deterministic, parameterized torque-allocation simulation around a clearly declared total driver request and per-wheel limits. Separate basic electronic-differential behavior from traction control and yaw-moment torque vectoring. Start with a bounded equal-allocation/reference controller and add complexity only for a testable benefit. Keep units, coordinate/sign conventions, sample period, saturation and failure behavior explicit. Unknown vehicle parameters are scenario ranges, not measured facts.

Acceptance: reproducible simulation, ordinary and adversarial fixtures, documented limitations, baseline outputs and a keep/revert rule. Synthetic results are not road/track performance or vehicle safety certification.

### TC-02 — Faults, logging and embedded feasibility

Develop a reviewable fault-state and command-validation design; deterministic replay tests; a logging schema; and an STM32F405 resource/timing measurement plan. Cover stale/missing/conflicting inputs, wheel-speed disagreement, brake/throttle plausibility, communication loss, non-finite values, saturation/rate limits, sign/unit errors, restart and watchdog behavior. Derive real acceptance limits from approved team requirements. Do not let a simulation bypass independent shutdown/safety systems.

Acceptance: testable fault transitions, negative tests, instrumentation and a team-review checklist. Actual MCU timing, bus behavior and hardware-in-loop results require measured receipts.

### TC-03 — Team-reviewed bench handoff and course evidence

After review, prepare build instructions, interface contracts, offline/bench procedures, test matrix and rollback for the team's authorized implementer. Package concise technical explanations, sourced calculations and figures for Lucas to understand and adapt to course requirements. Keep his own contribution, proposed research, implemented work and measured results distinct.

Acceptance: reviewers can reproduce the offline baseline and identify exactly what remains unverified before any bench/vehicle use. This charter does not authorize flashing firmware, actuating a vehicle, disabling safety checks, purchasing hardware, contacting teammates or submitting assignments.

## Research and execution workflow

Use current original papers, official STM32 documentation and official FSAE sources. Track publication/version/access dates, task relevance and assumptions. Prefer one useful artifact or resolved implementation question over repeated broad surveys. Continue source analysis, simulation and tests when a hardware response is missing; park only the dependent task. Do not upload protected team/company data or secrets to public services.

Company Runtime is the sole local scheduler/executor. Cloud research can maintain scoped GitHub work and portable sandbox tests; it does not establish AI-PC access. Native work must bind actual registered project/executor/task/run identities and retain commands, environment, exit codes and source/artifact hashes. Keep independent review, merge and deployment gates. All vehicle-affecting changes remain proposals until the appropriate team approvals and staged verification are actually obtained.
