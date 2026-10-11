# F1 telemetry, software, and simulation: consolidated research

Updated 11 October 2026. This consolidates the first F1 research round and additional public disclosures. All 11 organizations from the 2026 review are retained. It is an evidence map, not an inventory of confidential systems. Historical deployments, installed systems, pilots and group-wide partnerships have different evidential value.

See [evidence/access boundaries](evidence_and_access.md), the [Formula E and junior-formula report](formula_ladder_and_electric.md), and the [repository-specific roadmap](lapsim_development_roadmap.md).

## 1. Car data: control, live transmission, and the complete record

The central architectural distinction is between local real-time control, selected live radio telemetry and the more complete onboard record. Sensors and subsystem controllers feed vehicle networks. Onboard control must not depend on a remote analyst or internet connection. Live data supports immediate engineering decisions; subsequent garage offload supports replay, diagnosis and model correlation. Motion Applied describes the live/full-log distinction and wired Ethernet offload. [F01-F03]

Publicly discussed measurement domains include wheel speeds, driver inputs, inertial motion, suspension/ride height, brake and hydraulic pressures, electrical states, power-unit operation, temperatures, structural loads and aerodynamic development instrumentation. Exact channel dictionaries, filtering, rates, sensor locations and radio priorities remain private. Physical sensors, measured channels, computed channels, samples per second, radio throughput and weekend storage totals are not interchangeable quantities. [F01, F03]

Motion Applied identifies TAG-700 as the 2026 F1 Standard ECU and names ATLAS, System Monitor, vTAG and its Simulink-integrated Motion Control Toolbox in the supported toolchain. Multicore processing, CAN FD interfaces and encrypted onboard logging are disclosed specifications. A common ECU does not imply identical team models or analytics. Motion Applied, formerly McLaren Applied, must not be conflated with McLaren Racing's entire software estate. [F02-F03]

ATLAS documentation describes live/post-run analysis and derived channels. A virtual sensor is a model estimate, not an independent physical observation. vTAG is a PC-hosted ECU representation for software-oriented testing, not proof that physical hardware meets its timing requirements. Product latency and sample-rate headlines must not be extrapolated into whole-system performance. In particular, TAG-700's 800 ksps terminology is not a universal sensor rate or an established aggregate radio throughput. [F03-F04]

A proposed transferable pipeline is:

```text
raw timestamped signals -> decoded/calibrated channels -> quality checks
                                     |-> selected live monitoring
                                     |-> complete session replay
                                     |-> model/measurement residuals
                                     `-> versioned parameter or test revision
```

This diagram is an engineering synthesis, not a published blueprint of every team's private system.

## 2. Simulation is a collection of connected models

| Layer | Engineering question | Public example |
|---|---|---|
| CAD/product lifecycle management | Which geometry, material and revision is being tested? | Red Bull: Siemens NX, Teamcenter, Fibersim. [F09] |
| CFD/wind tunnel | What aero/cooling loads occur over the operating envelope? | Red Bull/Ansys; McLaren/Cadence; Aston Martin tunnel instrumentation. [F08, F16, F32] |
| Structures/materials | What stiffness, impact and material behavior is acceptable? | Red Bull: LS-DYNA, Granta MI. [F08] |
| Vehicle/tyre dynamics | How do driver input, setup, tyre forces and loads produce motion? | Haas's in-house modeling and tyre-science account. [F25] |
| Powertrain/reduced-order models | What torque, energy and losses result, at a usable computational cost? | Red Bull Ford/Ansys xROM. [F10] |
| SIL/HIL | Does control software work against a plant and then actual interfaces? | Motion Applied toolchain; individual team details remain private. [F03] |
| Driver-in-the-loop | How does a driver interact with the virtual vehicle and controls? | Ferrari, Alpine, Mercedes, Cadillac. [F06, F19, F24, F39] |
| Dyno/test benches | Does measured subsystem behavior agree with predictions? | Audi integrated powertrain bench. [F35] |
| Strategy | How do uncertain race events and decisions change outcomes? | Red Bull/Oracle Monte Carlo workloads. [F07] |

A detailed offline model may supply maps or a reduced-order model for faster evaluation. The faster representation still needs a validity envelope and independent checks. A marketing claim about real-time speed does not establish suitability for a specific controller.

## 3. Team-by-team map

### Mercedes-AMG Petronas

Microsoft's January 2026 account names Azure/AKS, existing GitHub/Microsoft 365 workflows and a virtual-sensor pilot. Some compute expansion is described in future terms; not every proposed workload is proven deployed. TeamViewer describes simulator/race-weekend remote access. AMD's CFD case study documents a historical hardware upgrade, not the complete current cluster. [F05-F06]

Available evidence concerns infrastructure and workflows. Tyre/vehicle equations, estimator definitions, DIL details, setup optimization and channel schemas remain private. Team/supplier sensor and throughput figures are not independent benchmarks or proof of radio bandwidth.

**Application:** distinguish measured and estimated channels; keep deterministic local control separate from remote analysis and batch computing.

### Oracle Red Bull Racing

Public disclosures identify OCI strategy computing, an earlier containerized deployment with Kubernetes/Arm/RabbitMQ, Ansys CFD/LS-DYNA/Granta, and Siemens NX/Teamcenter/Fibersim. Red Bull Ford describes high-fidelity power-unit source simulations and an Ansys xROM reduced-order model. Hexagon documents component/assembly metrology, including inspection and statistical-analysis software. [F07-F11]

Oracle's large simulation counts and the reported approximately 1,000-times-real-time reduced model are supplier-reported workload claims. A strategy trial is not a high-fidelity dynamic lap, and unspecified horizons/counting conventions prevent direct comparison with LapSim.

Private material includes maps, calibrations, strategy objectives and current deployment internals. **Application:** version inputs and geometry, retain physical evidence, and compare accuracy/cost on matched experiments rather than headline simulation counts.

### Visa Cash App Racing Bulls

Confluent describes data streaming across track/factory contexts; RebelDot describes custom data and engineering systems. A shared Red Bull Ford power-unit ecosystem does not prove identical infrastructure to Red Bull Racing. [F13-F14]

These are integration disclosures, not released telemetry or tyre models. **Application:** establish a local session/event contract before adding distributed infrastructure. A student-scale implementation can exercise the same data boundary without enterprise-scale software.

### McLaren Racing, Formula 1

Dell's 2026 relationship covers engineering compute, storage and analytics. Cadence Fidelity is publicly associated with aerodynamic CFD workflows, while Stratasys supports prototyping/manufacturing. [F15-F16]

McLaren Automotive's simulator and McLaren Hypercar's 2026 Dynisma installation are different program-level disclosures. Neither identifies the F1 team's full DIL/vehicle-model stack. See the [additional report](additional_professional_teams.md) for the Hypercar installation.

Tyre, vehicle, strategy and detailed CFD models remain private. **Application:** preserve model/geometry revisions and separate compute procurement from physical-model validation.

### Scuderia Ferrari

HP engineering hardware and a Ferrari-wide AWS agreement are disclosed, but a broad agreement spanning road cars and racing does not prove every cloud service is used in the F1 car-development loop. [F17-F18]

**Added to the earlier findings:** Ferrari/Dynisma announced completion of a bespoke simulator in July 2021, followed by calibration and planned September use for 2022-car development. AWS's 2025 technical account describes production pit-stop analysis with correlated video/data and mentions prior virtual ground-speed sensing. These are specific applications missing from the earlier broad summary. [F19-F20]

The estimator, training data and error envelope remain private. Pit-stop analytics is not the embedded torque-control loop. **Application:** synchronize events and channels; validate inferred states against independent measurements before replacing sensors or using estimates as calibration truth.

### BWT Alpine

KX describes time-series analysis across track/test sources, and Cato describes connectivity/security. The earlier review retained Apex Ultra engineering-AI and SEALSQ hybrid quantum/classical initiatives as new or experimental announcements, not independently proven physical-model improvements. [F21-F23]

**Added evidence:** Dynisma's May 2026 account states Alpine's Enstone installation was completed in 2025. This fills the earlier named-DIL-supplier gap without exposing all models inside it. [F24]

**Application:** compare bench, simulation and track evidence through common contracts. Require residuals and independent checks for proposed calibration changes, including changes suggested by AI tools.

### TGR Haas

Haas describes mathematical modeling, vehicle dynamics, tyre science, bench validation and track correlation. Toyota support includes simulator/development activity. NeverMile's operational software role does not establish that it provides Haas's tyre or physics solver. [F25-F27]

A simulator target date alone is not commissioning evidence. Model equations and calibration remain private. **Application:** characterize available subsystems before full-car testing; use measured evidence to improve the model rather than assuming an expensive cockpit establishes fidelity.

### Williams

VAST Data supports data/compute-heavy engineering. Atlassian and the team's technical descriptions concern collaboration and custom lifecycle/data integrations. Acronis backup/recovery is retained as a historical deployment. These disclosures do not identify the current tyre law or full CFD/DIL/strategy stack. [F28-F30]

**Application:** preserve inputs, decisions, ownership and reproducible run manifests. A repository and private evidence store are appropriate first implementations; an enterprise storage estate is not a prerequisite.

### Aston Martin Aramco

CoreWeave compute, Arm-based tunnel instrumentation/edge processing and NetApp storage are publicly associated with engineering work. The tunnel account describes dense instrumentation on a scaled model; supplier data-volume gains are not independent proof of aero-map accuracy. [F31-F33]

Detailed CFD, tyre and DIL models remain private. **Application:** retain aero reference area, axes, ride-height/yaw coverage and provenance. More samples cannot correct an incorrectly defined coefficient or unsupported operating range.

### Audi / Sauber lineage

Audi describes Neuburg Mission Control and an integrated power-unit bench. An additional historical HPE case from November 2023 identifies a GreenLake HPC installation in Hinwil's wind-tunnel building for Sauber CFD. It fills a named-infrastructure gap, but does not prove Audi's complete 2026 architecture is unchanged. [F34-F36]

A cloud-style service model can describe physically on-site hardware. No defensible Ansible Motion attribution was established for Audi in this review. **Application:** specify physical deployment and timing, and validate interacting subsystems under controlled conditions.

### Cadillac Formula 1

IFS operational/engineering management and 3D Systems manufacturing were identified in the earlier review; neither is the car's physics solver. Added GM accounts describe post-event driver/simulator correlation in Charlotte and a virtual Grand Prix rehearsal during the June 2025 Spanish weekend. The rehearsal preceded Cadillac's F1 debut and was not telemetry from a Cadillac race entry in that event. [F37-F40]

**Application:** rehearse engineering procedures and preserve pre-test predictions alongside post-test evidence. A functioning rehearsal is not measured vehicle validation.

## 4. What is and is not available

The sources supply toolchain descriptions, product specifications, selected methods and case studies. They do not supply a complete team's tyre-force parameters, aero maps, production torque algorithms, channel dictionary, setup files or validation dataset. Team-specific analytical outputs and scientific uncertainty are substantially less public than supplier names.

The most actionable implementation resources remain student-team code/logs and research models in the [formula/electric report](formula_ladder_and_electric.md). Professional practice informs the architecture; reviewed Terps measurements must establish vehicle-specific accuracy.

## Sources

**Rechecked** means the supporting page or search extract was retrieved in the 11 October expansion. **Retained** means carried forward from the preceding F1 review, not a fresh assertion that a historical deployment is unchanged. Supplier press-release mirrors are labeled. Source identifiers are not a count of unique URLs; some entries contain multiple related pages. F12 is unused.

- **F01, retained:** Data movement: https://mclarenapplied.com/news/how-data-moves-in-motorsport/
- **F02, rechecked:** Motion Applied F1: https://www.motionapplied.com/markets/motorsport/formula-one/
- **F03, rechecked:** TAG-700 and toolchain: https://www.motionapplied.com/products/tag-700/
- **F04, retained:** ATLAS: https://www.motionapplied.com/products/atlas-analyse/
- **F05, rechecked, 22 January 2026:** Microsoft/Mercedes: https://news.microsoft.com/source/2026/01/22/microsoft-and-mercedes-amg-petronas-f1-team-unite-to-drive-innovation-from-factory-to-circuit/
- **F06, retained, mixed historical/operational:** TeamViewer: https://www.teamviewer.com/tw/success-stories/mercedes-f1-simulation/ ; AMD: https://www.amd.com/en/resources/case-studies/mercedes.html ; Microsoft engineering workflows: https://www.microsoft.com/en/customers/brand-collections/mercedes-f1-team-operations
- **F07, landing page rechecked; architecture retained:** Oracle: https://www.oracle.com/asean/redbullracing/ ; earlier architecture: https://blogs.oracle.com/cloud-infrastructure/oracle-red-bull-racing-increases-simulations-and-sharpens-decision-making-on-the-track-with-oracle-cloud-infrastructure
- **F08, retained, 2022 case:** Ansys/Red Bull: https://ansys.synopsys.com/news-center/press-releases/10-24-22-ansys-congratulates-oracle-red-bull-racing-team-on-constructors-championship-victory
- **F09, retained:** Siemens/Red Bull: https://news.siemens.com/en-us/siemens-oracle-red-bull-racing/
- **F10, retained:** Ford/Red Bull xROM: https://fromtheroad.ford.com/eur/en/articles/2026/ford-red-bull-f1-powertrain-innovation
- **F11, rechecked, 11 February 2026:** Hexagon/Red Bull Ford metrology: https://hexagon.com/company/newsroom/press-releases/2026/red-bull-ford-powertrains-uses-hexagon-technology-to-ensure-super-high-performance-of-its-first-ever-f1-powertrain
- **F13, retained, 2025 announcement:** Confluent/Racing Bulls: https://www.confluent.io/press-release/confluent-and-visa-cash-app-racing-bulls-partnership/
- **F14, retained:** RebelDot: https://www.rebeldot.com/case/visa-cash-app-racing-bulls
- **F15, retained:** McLaren/Dell: https://www.mclaren.com/racing/latest-news/2026/mclaren-racing-extends-relationship-with-dell-technologies/ ; Stratasys: https://www.mclaren.com/racing/partners/stratasys/
- **F16, retained:** Cadence/McLaren: https://www5.cadence.com/cfd-fidelity-mclaren-racing-cc-lp.html
- **F17, retained:** HP/Ferrari: https://www.hp.com/be-nl/partnerships/scuderia-ferrari-hp.html
- **F18, rechecked, June 2021, Ferrari-wide:** Ferrari: https://www.ferrari.com/en-BE/formula1/articles/aws-becomes-a-partner-of-scuderia-ferrari-mission-winnow ; AWS: https://press.aboutamazon.com/2021/6/ferrari-selects-aws-as-its-official-cloud-provider-to-power-innovation-on-the-road-and-track
- **F19, rechecked, 7 July 2021:** Ferrari/Dynisma: https://www.dynisma.com/news/dynisma-completes-scuderia-ferrari-mission-winnows-new-simulator
- **F20, rechecked, 2025 account of a 2024 production workflow:** AWS pit-stop analysis: https://aws.amazon.com/blogs/machine-learning/aws-machine-learning-supports-scuderia-ferrari-hp-pit-stop-analysis/
- **F21, retained:** KX/Alpine: https://kx.com/customer-stories/bwt-alpine-f1-team-drives-success-with-real-time-data-analytics/
- **F22, retained:** Cato/Alpine: https://www.catonetworks.com/customers/bwt-alpine-formula-one-team-built-network-behind-its-most-ambitious-season/
- **F23, retained, experimental/new announcements:** Apex Ultra: https://media.alpinecars.com/learning-faster-bwt-alpine-formula-one-team-names-apex-ultra-its-official-ai-for-engineering-partner/?lang=eng ; SEALSQ: https://media.alpinecars.com/bwt-alpine-formula-one-team-and-sealsq-advance-formula-ones-first-quantum-security-partnership-with-hybrid-quantum-classical-simulation/?lang=eng
- **F24, rechecked, 19 May 2026 disclosure of 2025 installation:** Alpine/Dynisma: https://www.dynisma.com/news/bwt-alpine-formula-one-team-installs-dynisma-simulator-technology
- **F25, retained:** Haas science: https://www.haasf1team.com/vehicle-performance-science
- **F26, retained, partnership/plans:** Toyota/Haas: https://www.haasf1team.com/partners/toyota-gazoo-racing
- **F27, retained, operations scope:** NeverMile/Haas: https://www.haasf1team.com/partners/nevermile
- **F28, retained:** Williams/VAST: https://www.williamsf1.com/partners/vast-data-v2
- **F29, retained:** Williams workflows: https://careers.williamsf1.com/blog/2025-7/how-innovation-shapes-f1-tech-jobs
- **F30, retained, historical:** Williams/Acronis: https://www.williamsf1.com/articles/e7f92327-251b-4102-9b61-9aeece20a280/williams-racing-and-acronis-announce-cyber-protection-partnership-extension
- **F31, retained, supplier release mirror:** CoreWeave/Aston Martin: https://br.advfn.com/noticias/PRNUS/2025/artigo/96110026
- **F32, retained:** Arm/Aston Martin: https://www.arm.com/zh-TW/company/arm-and-aston-martin-aramco-racing-wind-tunnel
- **F33, retained, supplier release mirror:** NetApp/Aston Martin: https://www.marketscreener.com/news/aston-martin-aramco-formula-one-team-now-fully-powered-by-netapp-storage-ce7d5adad189f12d
- **F34, retained:** Audi Mission Control: https://www.audif1.com/news/2026/all-for-one-khawla
- **F35, retained:** Audi test bench: https://www.audif1.com/news/2026/all-for-one-hakan
- **F36, rechecked, 15 November 2023, historical Sauber:** HPE: https://www.hpe.com/us/en/newsroom/press-release/2023/11/sauber-motorsport-ag-taps-hpe-greenlake-to-advance-formula-one-race-car-aerodynamics.html
- **F37, retained, supplier release mirror:** Cadillac/IFS: https://www.utusan.com.my/pr-newswire-en/2026/01/cadillac-formula-1-team-partners-with-ifs-ahead-of-the-teams-debut-season/
- **F38, retained, supplier release mirror:** Cadillac/3D Systems: https://www.marketscreener.com/news/new-cadillac-formula-1-team-deploys-3d-systems-sla-technology-to-achieve-2026-debut-ce7e50dddd8bf52c
- **F39, rechecked, June 2026:** GM/Cadillac correlation: https://news.gm.com/home.detail.html/Pages/topic/us/en/2026/jun/0603-cadillac-formula-1-team.html
- **F40, rechecked, November 2025 account of June rehearsal:** GM virtual Grand Prix: https://news.gm.com/home.detail.html/Pages/topic/us/en/2025/nov/1124-Spanish-Grand-Prix-Cadillac-Formula-1.html
