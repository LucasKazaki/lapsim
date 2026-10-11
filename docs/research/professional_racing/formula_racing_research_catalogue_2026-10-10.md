# Formula racing data and simulation: research catalogue

Research date: 10 October 2026. Context: ENME408 LapSim and EV torque control.

## Scope and evidence boundaries

This catalogue preserves primary rulebooks, team and supplier disclosures, original research, and publicly accessible project repositories. It is not an exhaustive inventory of confidential systems or every regional F4 entrant. Formula E team coverage refers to the 2025/26 Season 12 grid, with later Gen4 technology announcements dated separately. ART, MP Motorsport, Andretti Formula E and CUPRA KIRO had no defensible named current performance-software deployment established in this review; that is a research gap, not evidence of absent capability.

A deployed product, an announced contract, a historical case study, a job requirement, public source code and an actual measurement dataset are different kinds of evidence. Partner performance claims are not independent validation. Repository listings and documentation were inspected; no firmware was compiled, controller was validated, or simulator benchmark was run. No private team datasets were accessed. Publicly linked Drive directories were listed through an authenticated connector; unrestricted anonymous access was not separately tested.

## Highest-priority resources for this project

- Waterloo CAN logs and UBC firmware for signal definitions, replay, testing, and embedded/desktop boundaries.
- F4 U.S. fastest-lap data share for a concrete race-log ingestion and driver-analysis exercise, after decoding and permissions review.
- TUMFTM and OpenLAP for inspectable numerical formulations and comparison baselines.
- Penske/AVL, Rodin, PREMA, Nissan and Jaguar TCS for workflow patterns rather than purchasing their simulator hardware.
- Institution-authorized TTC access for tire-model identification; keep restricted measurements outside public Git history.

## Important distinctions

Logging is not radio telemetry. Simulation-generated channels are not physical measurements. A motion simulator supplier does not necessarily supply the vehicle physics. A DBC mentioned by regulations is not automatically public. AWD does not automatically provide four independently commandable wheel torques. Matching one lap time does not establish correct tire forces, electrical losses, transient dynamics or controller behavior.

## F4 U.S. sample inventory verified during this review

The official portal led to Racing America Data Share, then F4 US Data Share, then 2026, then VIR. The VIR folder listed the following binary files. Their contents and channels were not decoded:

```text
FASTLAP-car27-F4-Q-VIR-2026-09-18-18-52-27.stf
FASTLAP-car17-F4-R1-VIR-2026-09-19-15-02-15.stf
FASTLAP-car27-F4-R2-VIR-2026-09-20-12-32-11.stf
```

Folder: https://drive.google.com/drive/folders/13jNF6nfwtqUoOoI2IF_pHms026iJ29z-

## Source register

### S01. FIA Formula 2, 2026 technical regulations Issue 3

**Area:** Regulations  
**Evidence/status:** Current rule text, 23 February 2026

Permitted sensors, ECU logging, transmission restrictions and controlled technical documentation.

**Limit:** A rulebook is not access to teams’ logged channels or software.

Source: https://api.fia.com/system/files/documents/2026_fia_formula_2_technical_regulations_-_issue_3_-_2026.02.23.pdf

### S02. FIA Formula 3, 2026 technical regulations Issue 3

**Area:** Regulations  
**Evidence/status:** Current rule text, 23 February 2026

Standardized car electronics and regulated data collection.

**Limit:** Read series-specific exceptions; do not generalize from F1 telemetry.

Source: https://www.fia.com/system/files/documents/2026_fia_formula_3_technical_regulations_-_issue_3_-_2026.02.23.pdf

### S03. FIA Formula 4, 2026 technical regulations

**Area:** Regulations  
**Evidence/status:** 2026 framework, official championship-hosted copy

ECU/logger provisions, allowed chassis sensors and electrical interfaces.

**Limit:** Regional regulations and chassis generations still matter.

Source: https://www.f4-cez.com/wp-content/uploads/2026/03/2026-FIA-Formula-4-Technical-Regulations.pdf

### S04. Formula E Season 12 technical regulations

**Area:** Regulations  
**Evidence/status:** 2025/26 rule text

FIA logger signals, CAN interface, controlled telemetry and conditional traction-control permissions.

**Limit:** An FIA DBC referenced in regulations is not necessarily publicly downloadable.

Source: https://www.fia.com/system/files/documents/2025-2026_season_12_formula_e_techregs_wmsc_10.06.2025_eng_fr_marked_up_rev_05.06.25_0.pdf

### S05. Formula E Season 13 technical regulations

**Area:** Regulations  
**Evidence/status:** Gen4 rule text, 30 September 2026

Updated electronics, logging and transmission requirements.

**Limit:** Do not silently mix these requirements with Season 12.

Source: https://www.fia.com/system/files/documents/2026-2027_season_13_formula_e_techregs_wmsc_30.09.2026_eng_fr_v20.pdf

### S06. F2 car and engine

**Area:** Common hardware  
**Evidence/status:** Official series specification

Marelli electronics/data acquisition description.

**Limit:** Does not establish the analysis application used by every team.

Source: https://www.fiaformula2.com/en/information/the-car-and-engine-f2.14LCsEEMG9yyx5DkhcN1J8

### S07. F3 car and engine

**Area:** Common hardware  
**Evidence/status:** Official series specification

Shared car specification and equipment context.

**Limit:** A common chassis does not imply identical team models.

Source: https://www.fiaformula3.com/en/information/the-car-and-engine-f3.5tGE8Qr5FdTJJwaUN0YbWq

### S08. PREMA / Dynisma

**Area:** F2/F3 teams  
**Evidence/status:** Operational deployment; June 2025 disclosure

DMG-1 development workflow, driver preparation and HIL with real vehicle controls/software.

**Limit:** No public vehicle-model source code or calibration.

Source: https://www.dynisma.com/news/dynisma-simulator-technology-supports-prema-racing-in-driver-and-car-development

### S09. Hitech / Dynisma

**Area:** F2/F3 teams  
**Evidence/status:** Deployment described February 2024

DMG-1 simulator across junior-formula programs.

**Limit:** Motion platform is not a complete disclosure of the physics stack.

Source: https://www.dynisma.com/news/hitech-gp-shares-insights-into-how-brand-new-f1-grade-simulator-is-helping-team-prepare-for-upcoming-season

### S10. Rodin / Dynisma

**Area:** F2/F3 teams  
**Evidence/status:** Operational centre, 4 March 2026

DMG-1 plus static simulators; shared vehicle models and analysis between offline and online workflows.

**Limit:** Private models and data.

Source: https://www.dynisma.com/news/dynisma-dmg-1-powers-rodin-motorsports-new-driver-performance-centre

### S11. Invicta and AIX / AVL

**Area:** F2/F3 teams  
**Evidence/status:** Supplier deployment descriptions

Invicta simulation and transmission test-bed work; AIX use of VSM RACE.

**Limit:** Supplier performance claims are not independent benchmarks.

Source: https://www.avlracetech.com/

### S12. DAMS / Sim Racing Studio

**Area:** F2/F3 teams  
**Evidence/status:** Historical proposed collaboration, January 2024

Driver-training simulator software announcement.

**Limit:** Announcement says partnership was in process; not proof of current production physics software.

Source: https://www.simracingstudio.com/post/the-official-simulator-software-of-dams-f2-team

### S13. Campos Racing academy

**Area:** F2/F3 teams  
**Evidence/status:** Team disclosure

Simulator-based driver-development activity.

**Limit:** No defensible current named solver/data platform established.

Source: https://camposracing.com/academy

### S14. Trident

**Area:** F2/F3 teams  
**Evidence/status:** Team disclosure

Simulator preparation for multiple formula programs.

**Limit:** Underlying software and telemetry architecture undisclosed.

Source: https://www.tridentmotorsport.com/en/team-trident/

### S15. Van Amersfoort Racing

**Area:** F2/F3 teams  
**Evidence/status:** Firsthand driver interview, June 2025

Pre-event simulator preparation and feedback.

**Limit:** Interview evidence, not vendor identification or released data.

Source: https://www.pitdebrief.com/post/van-amersfoort-racing-drivers-on-the-crucial-role-of-simulator-work-in-modern-f3-racing/

### S16. F4 U.S. competitor portal

**Area:** F4 and regional  
**Evidence/status:** Official live resource directory

Fastest-lap sharing link, regulations, technical bulletins and supporting documents.

**Limit:** Shared logs are not equivalent to complete team datasets; file contents were not decoded.

Source: https://www.f4uschampionship.com/pages/competitor-portal

### S17. Racing America data-share root

**Area:** F4 and regional  
**Evidence/status:** Officially linked folder; directory listing verified

Contains F4 US, FR and JFC data-share directories.

**Limit:** Authenticated listing succeeded; anonymous access and reuse rights were not independently established.

Source: https://drive.google.com/drive/folders/16JxP6e3_fO1AY_I86q1w3WH4dwjZlVsg

### S18. F4 US data-share folder

**Area:** F4 and regional  
**Evidence/status:** Directory listing verified

Year folders including 2026; sampled 2026 VIR directory contains qualifying/R1/R2 FASTLAP .stf files.

**Limit:** Binary data not opened or exported; actual channel coverage is unverified.

Source: https://drive.google.com/drive/folders/1PCqcZCtvj0BQ7KnQnZtZ-FDU9rW4Zfg6

### S19. F4 CEZ / Autotecnica Motori

**Area:** F4 and regional  
**Evidence/status:** Official interview, August 2024

Post-session data downloads and engine-support analysis.

**Limit:** Regulated supplier diagnostics, not unrestricted team telemetry.

Source: https://www.f4-cez.com/behind-the-scenes-how-marco-ianniello-keeps-formula-4-cars-in-top-shape/

### S20. Maffi Racing

**Area:** F4 and regional  
**Evidence/status:** Recruitment evidence

F4 mechanic role lists WinTAX familiarity.

**Limit:** Skill requirement is weaker evidence than a deployed-system case study.

Source: https://www.maffiracing.ch/jobs-f4-first-mechanic

### S21. Ligier JS F422

**Area:** F4 and regional  
**Evidence/status:** Manufacturer specification

Alternative F4 chassis and regional platform context.

**Limit:** Do not assume Tatuus equipment across every F4 championship.

Source: https://ligierautomotive.com/en/vehicles/single-seaters/ligier-js-f422/

### S22. French F4 2026

**Area:** F4 and regional  
**Evidence/status:** Manufacturer/series description

FFSA Academy field using Ligier JS F422.

**Limit:** Centralized academy structure differs from independent-team championships.

Source: https://ligierautomotive.com/en/news/f4-france-a-record-32-car-ligier-js-f422-grid-kicks-off-the-2026-season/

### S23. USF Pro 2000 Tatuus IP-22

**Area:** Other single-seaters  
**Evidence/status:** Official vehicle specification

Named electronics/logger equipment and chassis interfaces.

**Limit:** USF ladder categories are not FIA F3; distinguish specifications and generations.

Source: https://www.usfpro2000.com/about/tatuus-ip-22

### S24. Season 12 team directory

**Area:** Formula E teams  
**Evidence/status:** Official championship roster reference

Team identity and championship context.

**Limit:** Season 13 entries and rebrandings are a separate roster.

Source: https://www.fiaformulae.com/en/teams

### S25. Nissan / Dynisma

**Area:** Formula E teams  
**Evidence/status:** Installed and operational, December 2025

DMG-1 for setup, control software, energy management and Gen4 development.

**Limit:** Private vehicle models and measured telemetry not supplied.

Source: https://www.dynisma.com/news/nissan-formula-e-team-completes-installation-of-dynisma-dmg-1-simulator-ahead-of-season-12

### S26. Jaguar TCS / V3M

**Area:** Formula E teams  
**Evidence/status:** Partner-described operational workflow

Automated driverless execution of repeated virtual braking/setup tests.

**Limit:** Headless simulation is not autonomous racing or a released software package.

Source: https://www.tcs.com/who-we-are/sports-sponsorships/jaguar-tcs-racing-formula-for

### S27. Porsche / Ansys

**Area:** Formula E teams  
**Evidence/status:** Detailed historical case study, 2022

Maxwell motor analysis and Twin Builder powertrain/system simulation.

**Limit:** Exact current software versions and team loss maps are not public.

Source: https://ansys.synopsys.com/advantage-magazine/volume-xvi-issue-1-2022/tag-heuer-porsche-formula-e-team-optimizes-its-powertrain-dynamics-with-ansys-simulation-software

### S28. Porsche / Ansys current partnership

**Area:** Formula E teams  
**Evidence/status:** Current supplier relationship

Official powertrain simulation partnership context.

**Limit:** Partnership does not prove every historical tool/version remains unchanged.

Source: https://ansys.synopsys.com/campaigns/porsche

### S29. Penske AUTOSPORT / AVL and Ansible Motion

**Area:** Formula E teams  
**Evidence/status:** Operational models; May 2025 announcement

VSM RACE, linked multi-driver simulations and energy-management development.

**Limit:** No released optimization algorithms or calibration.

Source: https://www.avl.com/en-de/press/press-release/avl-racetech-and-penske-autosport-formula-e-announce-official-partnership-vehicle-simulation-software

### S30. Stellantis Motorsport / Dynisma

**Area:** Formula E teams  
**Evidence/status:** Announced January 2026

Group-level DMG-1 partnership spanning Formula E and other racing programs.

**Limit:** Not separate proof of an identical DS Penske and Citroen team installation.

Source: https://www.dynisma.com/news/dynisma-becomes-official-driving-simulator-partner-of-stellantis-motorsport

### S31. Mahindra / Cruden

**Area:** Formula E teams  
**Evidence/status:** Historical supplier case study

Panthera integrates Mahindra vehicle model and actual ECU/controls into DIL.

**Limit:** Current 2026 simulator replacement status not established.

Source: https://www.cruden.com/article/mahindra-racing-formula-e-team-seeks-competitive-advantage-with-cruden-simulator

### S32. Envision / Sand Technologies

**Area:** Formula E teams  
**Evidence/status:** Team announcement, April 2025

Bespoke race-data analysis automation.

**Limit:** No published independent accuracy benchmark or source code.

Source: https://envision-racing.prowly.com/396659-envision-racing-uses-ai-to-improve-performance-over-race-weekends

### S33. Envision / Dynisma

**Area:** Formula E teams  
**Evidence/status:** Announced April 2026

DMG-1 supply agreement with planned August installation.

**Limit:** Commissioning not independently verified in this review.

Source: https://www.dynisma.com/news/dynisma-to-supply-simulator-technology-to-envision-racing

### S34. Lola / Ansible Motion

**Area:** Formula E teams  
**Evidence/status:** Announced May 2026

First Delta T1 Sport unit for Formula E Gen4 and wider development.

**Limit:** Announcement describes future delivery; completion not established here.

Source: https://www.ansiblemotion.com/ansible-motion-automotive-driver-in-the-loop-simulation-news/delta-t1-sport-all-new-compact-dynamic-racing-simulator

### S35. Michelin/Canopy

**Area:** Formula E methods  
**Evidence/status:** Commercial product description

Optimal-control lap simulation and real-time model integration.

**Limit:** Product is proprietary; no attribution to an unnamed specific team.

Source: https://simulation.michelin.com/canopy

### S36. Canopy energy-management and overtaking research

**Area:** Formula E methods  
**Evidence/status:** Original technical article, July 2026

Energy-limited lap optimization and CFD-to-track correlation method.

**Limit:** Published methodology does not include unrestricted raw team data.

Source: https://simulation.michelin.com/canopy/technical-articles/dynamic-lap-for-energy-management-and-overtaking-in-formula-e

### S37. Championship broadcast / Google Cloud

**Area:** Formula E data infrastructure  
**Evidence/status:** Official architecture disclosure, December 2025

Telemetry/timing pipeline with Pub/Sub, AlloyDB and human-approved broadcast insights.

**Limit:** Central broadcast analytics is not team-controlled car telemetry or a public API.

Source: https://www.fiaformulae.com/en/news/races/under-the-hood-building-real-time-race-insights-with-gemini-and-google-cloud

### S38. UBC Formula Electric firmware

**Area:** Public Formula Student resources  
**Evidence/status:** Public source repository; Apache-2.0

STM32 firmware, CAN definitions, native tests and validation tools.

**Limit:** Not built or safety-certified in this review; inspect third-party licenses before integration.

Source: https://github.com/UBCFormulaElectric/Consolidated-Firmware

### S39. Waterloo CAN logs

**Area:** Public Formula Student resources  
**Evidence/status:** Public repository and documented workflow

Raw/parsed test logs, 2024CAR.dbc and parsing/plotting scripts.

**Limit:** Top-level reuse license not confirmed; data completeness and calibration not audited.

Source: https://github.com/UWaterloo-Formula-Electric/CAN_logs

### S40. Waterloo cell-test data

**Area:** Public Formula Student resources  
**Evidence/status:** Public repository listing inspected

Large CSV collection described by team as 2024 cell-tester data.

**Limit:** Cell identification, calibration, provenance and reuse permissions need checking.

Source: https://github.com/UWaterloo-Formula-Electric/2024_CellData

### S41. Waterloo public organization

**Area:** Public Formula Student resources  
**Evidence/status:** Public source discovery

Firmware, telemetry-interface and CAN-graphing repositories.

**Limit:** Each repository requires its own maintenance and license review.

Source: https://github.com/UWaterloo-Formula-Electric

### S42. OpenLAP

**Area:** Public simulation code  
**Evidence/status:** Public MATLAB code; GPL-3.0

Lap, drag, vehicle and track modules with examples.

**Limit:** Example Formula 1/FSAE configurations are not verified professional-team parameter data.

Source: https://github.com/mc12027/OpenLAP-Lap-Time-Simulator

### S43. TUMFTM global race-trajectory optimization

**Area:** Public simulation code  
**Evidence/status:** Public Python code; LGPL-3.0

Minimum-time trajectory planning with optional electric powertrain, thermal and energy models.

**Limit:** Academic research environment; not run or calibrated to the Terps car here.

Source: https://github.com/TUMFTM/global_racetrajectory_optimization

### S44. Minimum Race-Time Planning-Strategy for an Autonomous Electric Racecar

**Area:** Public simulation research  
**Evidence/status:** Author-hosted research preprint, 2020

Inspectible EV race-time and energy-management methodology supporting TUM code.

**Limit:** Autonomous planning assumptions are not all needed for a driven FSAE car.

Source: https://arxiv.org/abs/2005.07127

### S45. MathWorks Formula Student Vehicle with Simscape

**Area:** Public simulation code  
**Evidence/status:** Public model repository

Multibody suspension, configurable electric powertrain and test maneuvers.

**Limit:** MATLAB/Simulink/Simscape dependencies and model license still apply.

Source: https://github.com/simscape/Formula-Student-Vehicle-Simscape

### S46. CTU slip-ratio control for torque vectoring

**Area:** Public research  
**Evidence/status:** University thesis record

Model-based rear-axle torque control with simulation and vehicle-test results described.

**Limit:** Public research is not permission to copy all thesis content or a turnkey controller.

Source: https://dspace.cvut.cz/handle/10467/83062

### S47. dSPACE Formula Student programs

**Area:** Student development hardware  
**Evidence/status:** Supplier case studies

Named student-team real-time control and simulation workflows.

**Limit:** Commercial hardware descriptions, not open controller implementations.

Source: https://www.dspace.com/en/inc/home/company/corporatecitizenship/formulastudent.cfm

### S48. FSAE Tire Test Consortium

**Area:** Restricted measurement data  
**Evidence/status:** Official access and data-license description

Measured tire forces/moments and operating-condition sweeps for member institutions.

**Limit:** Not open data; do not upload raw TTC files to a public repository.

Source: https://www.millikenresearch.com/fsaettc.html

### S49. Cosworth Pi Toolbox

**Area:** Analysis software  
**Evidence/status:** Current official product/download page

Time-synchronized analysis, derived channels and live/logged viewing; Lite edition described as free.

**Limit:** Feature tiers, supported file types and export permissions must be checked for the intended workflow.

Source: https://www.cosworth.com/motorsport/products/pi-toolbox/

### S50. iRacing / Cosworth Pi Toolbox

**Area:** Analysis workflow  
**Evidence/status:** Official joint integration announcement, November 2025

Simulated vehicle data can be reviewed in the professional analysis application.

**Limit:** Simulator-generated data does not validate a real Formula SAE vehicle model.

Source: https://www.iracing.com/cosworth-pi-toolbox-offers-more-data-real-time-telemetry-and-advanced-features-to-iracing-members/
