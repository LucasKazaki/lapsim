# Formula ladder, Formula E and Formula Student: consolidated findings

Consolidated 11 October 2026 from the 10 October research round. Source identifiers S01-S50 refer to the preserved [50-source catalogue](formula_racing_research_catalogue_2026-10-10.md), which includes URLs, evidence dates, access status and limitations. This page preserves the team-level conclusions and practical implications; it is not a new audit of each rulebook or repository.

## 1. Data acquisition differs between championships

F2/F3 technical regulations constrain additional sensors, logging and transmission from the moving car. Extensive recorded data does not imply a general-purpose live radio stream. F4 is a regional framework with multiple chassis/electronics generations rather than one universal team software installation. Formula E's controlled data provisions and central championship/broadcast systems must also be distinguished from each team's private engineering system. [S01-S07, S21-S24, S37]

Before adapting a design, identify its championship, season, chassis, electronic topology and allowed interfaces. An FIA logger-channel requirement does not make the referenced DBC or the teams' recordings publicly available. Formula E Season 12 and Season 13 are different technical regimes. In particular, the earlier research found conditional traction-control provisions rather than a universal yes/no rule. Recheck the applicable Formula SAE rulebook before selecting a vehicle-control feature; this research is not a current rules-compliance certificate. [S01-S05]

## 2. F2/F3 organization map

These are organizations reviewed across F2/F3, not an assertion that each appears in every series or season.

| Organization | Evidence retained | What is not established |
|---|---|---|
| PREMA | Operational Dynisma DMG-1; driver/setup development and real vehicle controls/software in HIL. [S08] | Public physics, controller source or calibration. |
| Hitech | Dynisma DMG-1 across junior-formula development. [S09] | Full tyre/model/telemetry software stack. |
| Rodin Motorsport | March 2026 centre: DMG-1, static simulators, common vehicle-model and data workflows across offline/online use. [S10] | Customer-owned model and measurements. |
| Invicta | AVL simulation support and transmission/differential test-bed characterization. [S11] | Released measured component maps. |
| AIX Racing | AVL VSM RACE identified by the supplier. [S11] | Public calibration or independent performance benchmark. |
| DAMS | January 2024 Sim Racing Studio collaboration described as in development. [S12] | Current production deployment or engineering physics engine. |
| Campos Racing | Academy simulator preparation. [S13] | A named full data/solver suite. |
| Trident | Simulator preparation spanning several formula programs. [S14] | Current solver, tyre model and telemetry architecture. |
| Van Amersfoort Racing | Firsthand driver account of pre-event simulation and feedback. [S15] | Product identification; the retained interview is not a primary technical specification. |
| ART Grand Prix | No defensible current named performance-software deployment established in the review. | Absence of evidence must not be turned into an absent capability. |
| MP Motorsport | Same research gap. | No inferred vendor from the common chassis or other teams. |

F2's official specification identifies Marelli electronics/data acquisition, but that does not establish a universal analysis front end across these organizations. Do not write that all teams use WinTAX, ATLAS or Pi Toolbox without team-specific evidence. [S06]

**Transfer to LapSim:** PREMA supports the value of controller-in-the-loop testing; Rodin supports model and analysis reuse; Invicta shows why measured subsystem characterization can be useful before a complete car test. These are workflow precedents, not instructions to copy proprietary models or buy the same hardware.

## 3. F4 and adjacent single-seaters

### Official F4 U.S. data-share lead

The official competitor portal links a fastest-lap data share. The earlier review followed the directory through Racing America -> F4 US -> 2026 -> VIR and verified three `.stf` filenames for qualifying and two races. Their exact names and folder are preserved in the catalogue. This is stronger than a vendor claim because actual file listings were observed, but the binaries were **not decoded**, channel coverage was not established, and anonymous access/reuse rights were not independently tested. [S16-S18]

Use this lead for an import experiment only after checking permissions and supported tools. It is not yet a validated Python dataset, and an unrelated F4 car cannot calibrate the Formula Student EV's powertrain.

### Practical instrumentation and support

The F4 rules expose a constrained instrumentation philosophy rather than unlimited sensors. The Autotecnica Motori interview describes post-session downloads and supplier analysis of engine operation. Maffi Racing's job description names WinTAX familiarity, but a hiring requirement remains weaker than an installed-system case study. [S03, S19, S20]

Ligier JS F422 and French F4 material demonstrate why platform and championship context must be retained. The French academy structure is not identical to independent teams in every F4 series. USF Pro 2000's Tatuus IP-22 page is an additional named-electronics reference, not FIA F3 documentation. [S21-S23]

**Transfer to LapSim:** distinguish safety/control channels from optional development measurements. Produce a repeatable post-run health report before attributing a pace difference to torque allocation. Preserve unavailable channels as unavailable instead of synthesizing a plausible trace.

## 4. Formula E team map

This table retains the **2025/26 Season 12** organization coverage, with later announcements dated separately. It must not be used as an automatically current Season 13 roster. [S24]

| Organization | Publicly named technology or method | Status and boundary |
|---|---|---|
| Jaguar TCS Racing | TCS Virtual Vehicle Validation Model, V3M. [S26] | Repeated virtual braking/setup tests without occupying a driver for every run. Headless testing is not autonomous racing. |
| Nissan | Dynisma DMG-1. [S25] | Installed/operational by December 2025; setup, software, powertrain and energy-management uses disclosed. |
| Porsche | Ansys Maxwell and Twin Builder. [S27, S28] | Detailed 2022 powertrain case plus later partnership context; exact current versions/maps remain private. |
| DS PENSKE / Penske AUTOSPORT | AVL VSM RACE; Ansible Motion multi-simulator arrangement. [S29] | Model reuse and energy-management development; see additional report N20 for concrete installation dates. |
| Citroen Racing | Relevant group-level Stellantis/Dynisma DMG-1 agreement. [S30] | January 2026 announcement does not prove an independent identical Citroen installation. |
| Mahindra | Cruden Panthera, team vehicle model, actual ECU/controls. [S31] | Historical concrete integration example; unchanged 2026 installation not established. |
| Envision Racing | Sand Technologies analysis automation; Dynisma DMG-1 agreement. [S32, S33] | Analysis described in 2025; 2026 simulator target date is not commissioning confirmation. |
| Lola Yamaha ABT | Ansible Motion Delta T1 Sport for Formula E/Gen4 and wider work. [S34] | May 2026 announcement described future delivery. |
| Andretti Formula E | No defensible current named team-level performance-software deployment established. | A powertrain relationship does not establish a complete shared software stack. |
| CUPRA KIRO | Same research gap. | Do not infer the supplier's complete model/compute environment. |

### What these examples teach

**Energy and dynamics should be coupled.** Penske/AVL and Porsche/Ansys describe workflows that connect vehicle behavior to electrical powertrain/energy questions. A future LapSim model should account for torque-speed feasibility, conversion losses, pack limits, regeneration and thermal state where supported by evidence. A constant efficiency can remain an explicitly labeled baseline; it should not quietly stand in for a validated loss map. [S27-S29]

**Automate experiments before building a sophisticated cockpit.** Jaguar's repeated virtual tests demonstrate a useful split between batch evaluation and human driving. Reserve DIL for questions involving driver interaction and subjective response. Deterministic parameter sweeps and fault scenarios should not require a person to drive every test. [S26]

**Reuse models across execution modes.** Mahindra's case explicitly connects an existing vehicle model to a real-time environment with actual controls. Nissan and Penske provide related examples of simulation supporting both development and preparation. This argues for compatible interfaces between our spatial lap solver, transient controller tests, replay and a future driver simulator, not a separate game physics implementation. [S25, S29, S31]

**AWD is not a motor topology.** Four-wheel drive may use different motor and differential arrangements. The Terps controller interface must reflect verified independently commandable actuators, not another series' AWD label. Neither professional series rules nor their power limits become Formula SAE requirements by analogy.

### Public Formula E methods and central analytics

Michelin/Canopy's technical article links CFD-derived aerodynamic behavior, energy-limited lap optimization and correlation with measured behavior. Its methodological value does not imply unrestricted access to the underlying team measurements. The useful experiment pair is minimum lap time at a fixed energy budget versus reduced energy for an acceptable pace. [S35, S36]

Formula E's Google Cloud account describes championship-level timing/telemetry ingestion and human-approved broadcast insights using services including Pub/Sub and AlloyDB. It is not a public team telemetry API or an onboard control architecture. A language model should not be inserted into the hard-real-time torque loop on the strength of a broadcast-analysis example. [S37]

## 5. Formula Student/SAE Electric resources with inspectable material

| Resource | Accessible material | First useful experiment | Reuse or validation boundary |
|---|---|---|---|
| Waterloo CAN logs | Raw/parsed organization, DBC and parsing/plotting scripts. [S39] | Decode an authorized sample; preserve timestamps, units, missingness and message identity. | Reuse license and calibration need checking; do not vendor the dataset automatically. |
| Waterloo cell tests | CSV collection described as cell-tester data. [S40] | Inventory units, cell identity and test metadata before fitting. | No assumption of identical cells or test conditions to Terps. |
| UBC Formula Electric firmware | STM32 code, CAN definitions and native test infrastructure; Apache-2.0 reported in the reviewed repository. [S38] | Study separation of controller logic from hardware interfaces. | Review dependencies/license and hardware assumptions; no safety approval or build performed here. |
| OpenLAP | MATLAB lap/drag/vehicle/track modules; GPL-3.0. [S42] | Define a matched simple vehicle and compare numerical formulation. | Do not assume example F1/FSAE parameters are authentic; review copyleft implications before copying code. |
| TUMFTM trajectory optimization | Python minimum-time work with optional electrical, energy and thermal models; LGPL-3.0. [S43, S44] | Compare energy-constrained formulations on a deliberately simplified common test. | Research assumptions and dependencies must be reproduced; not a Terps calibration. |
| MathWorks Formula Student vehicle | Simscape multibody/electrical configurations and maneuvers. [S45] | Use an independent maneuver model to challenge assumptions. | Commercial dependencies and model licensing still apply. |
| CTU torque-vectoring thesis | Model-based slip/torque control and described simulation/vehicle tests. [S46] | Extract assumptions, control objectives and validation method. | A thesis is not turnkey safety-reviewed firmware. |
| FSAE Tire Test Consortium | Member-access measured tyre data. [S48] | Check authorized UMD access; fit and validate only within covered conditions. | Restricted data must remain outside this public repository. |

Waterloo's public organization and dSPACE student case studies are additional discovery sources, not blanket approval of every repository or hardware architecture. [S41, S47]

Cosworth Pi Toolbox and its iRacing integration are useful references for synchronized trace comparison, mathematical channels and debriefing. Feature tiers, exports and supported formats need checking. Consumer simulator traces can exercise an importer, but cannot validate physical Formula Student behavior. [S49, S50]

## 6. Recommended use order

1. Review UBC's testable embedded architecture and Waterloo's documented decoding workflow without copying restricted or unlicensed material.
2. Inventory an authorized F4 data sample and compare analysis interfaces; do not assume its channel coverage beforehand.
3. Define matched, simplified numerical experiments for OpenLAP/TUM/Simscape rather than comparing unmatched headline lap times.
4. Use reviewed Terps measurements and authorized tyre data for calibration and chronological holdout validation.
5. Apply the professional workflow precedents through the repository-specific [development roadmap](lapsim_development_roadmap.md).

This sequence is an engineering recommendation. No external controller was compiled, dataset decoded, third-party simulator benchmarked, or physical vehicle validated in this research upload.
