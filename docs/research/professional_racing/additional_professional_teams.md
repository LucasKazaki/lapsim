# Additional professional racing teams and engineering programs

Research expanded 11 October 2026. Coverage extends the F1, F2/F3/F4, Formula E and Formula Student work into IndyCar, WEC/IMSA prototypes, GT engineering and NASCAR. This is a selected evidence-backed inventory, not a claim to cover every professional entrant. A manufacturer facility may support several teams without revealing those teams' complete software stacks.

The principal transferable findings are synchronized simulation data, consistent vehicle/track models, hybrid control validation, post-test correlation, automated experiment pipelines, and configuration management. Motion hardware and cloud branding are not substitutes for calibrated models.

## 1. Honda Racing Corporation USA: IndyCar and multi-program DIL

Honda's 30 May 2024 release describes a new Indianapolis driver-in-the-loop simulator with multibody vehicle dynamics, approximately 2,000 available channels, up to 1.5 MB/s of generated data, and multiple camera views synchronized to the logs. Those figures describe the simulator, not a car-to-pit radio stream. Honda states that the facility can support multiple cars and series. [N01]

A September 2026 Ansible Motion account adds Delta S3 hardware, HRC-owned vehicle-model content and rFpro track/surface modeling. The separation matters: the motion platform, track renderer and proprietary tyre/aero model are not interchangeable parts of one publicly available game. [N02]

**Available:** descriptions of the measurement/visualization architecture and model ownership. **Not available:** actual HRC tyre maps, calibrated vehicle model, full logs or controller code.

**LapSim application:** put video markers, simulation states, driver inputs and controller commands on a shared clock. Use one provenance-tracked track representation across graphics and physical queries, with explicit transformations when representations differ. Do not assume that an attractive rendered kerb is represented in the physics model.

## 2. Cadillac Racing: Hertz Team JOTA and Wayne Taylor Racing

GM's 2 June 2026 Le Mans preparation account describes simulator work before and after events, car/tyre correlation, and technical exchange between the JOTA WEC and WTR IMSA programs. It also identifies changing track grip as difficult to reproduce and distinguishes aerodynamic package choices from mechanical setup. This is evidence of a learning loop, not a named public physics engine. [N03]

**Available:** an engineering account of preparation, correlation and cross-program learning. **Not available:** shared setup files, tyre data, homologation model or simulator source.

**LapSim application:** freeze a pre-test prediction, retain the measured result, and issue a separate post-test calibration revision. Never overwrite the prediction and then present the revised model as a successful forecast. Include road/grip uncertainty rather than fitting every discrepancy into the tyre coefficient.

## 3. Genesis Magma Racing: GMR-001 hybrid and braking development

Genesis/Hyundai's 2025 account documents work with Dynisma before full vehicle testing, including car/tyre modeling and hybrid MGU/braking software evaluation. Drivers and engineers used the supplier's facility while the team planned its own DMG-360XY installation at Le Castellet for early 2026. The article establishes supplier-facility testing; its target date alone does not prove commissioning of the team's own installation. [N04]

**Available:** a concrete pre-car development workflow. **Not available:** executable hybrid controller, calibration, or public measured validation results.

**LapSim application:** exercise torque commands, regeneration, hydraulic braking and energy limits together before connecting real hardware. A correct chassis force balance cannot establish that a requested motor torque is electrically or mechanically feasible.

## 4. McLaren Hypercar: a distinct program from McLaren F1

Dynisma's 21 July 2026 release explicitly reports a DMG-1 installed at the McLaren Technology Centre for the MCL-HY program, supporting vehicle development, driver preparation and engineering evaluation ahead of the 2027 WEC debut. This is an installed development facility for a future racing program, not evidence that the car had already raced in WEC or that McLaren F1 uses the same model. [N05]

**Available:** deployment and program-level use. **Not available:** car/tyre model, calibrated aero or telemetry archive.

**LapSim application:** distinguish development configuration, commissioning status and competition configuration in the source registry. A future-car model is useful while still clearly labeled provisional.

## 5. Toyota Motorsport / Toyota Gazoo Racing WEC

A dSPACE account dated September 2012 describes a Toyota Motorsport driving simulator using HIL technology and modular physical/controls functions, with models informed by testing. It is a useful historical example of separating subsystems and integrating them in real time. It does not establish Toyota's entire 2026 deployment. [N06]

Fujitsu's May 2023 announcement describes real-time analysis of onboard video for Toyota's WEC work, first used at Spa that April. This is an additional observational data source, not a replacement for physical measurements or a public car telemetry API. [N07]

**Available:** architecture and video-analysis use cases. **Not available:** current team model code or raw training/validation datasets.

**LapSim application:** isolate the control plant from visualization and analysis; keep video-derived or inferred events distinguishable from directly measured channels. Historical HIL is evidence of a workable method, not a requirement to buy the same hardware today.

## 6. Porsche Penske Motorsport: 963 preparation

Porsche's March 2024 account of a 963 test sequence includes simulator preparation before physical rollout and track testing. This supports DIL use for complex vehicle familiarization and preparation, but it does not name the simulator's complete physics stack or release the resulting data. [N08]

**LapSim application:** include procedural tests, display warnings, driver controls and mode transitions in future driver-in-the-loop work. The ability to drive a fast virtual lap does not prove correct startup, fault or braking procedures.

Do not conflate Porsche Penske Motorsport, Team Penske's NASCAR/IndyCar programs, and Penske AUTOSPORT's Formula E organization. Name similarity is not evidence that all use the same AVL, Siemens, or Ansible Motion deployment.

## 7. BMW M Motorsport: engineering data versus consumer simulation

BMW's 2022 iRacing collaboration describes sharing engineering information for the virtual M Hybrid V8. This is a concrete bridge between a manufacturer and a commercial simulator. It does not make the source CAD, track measurements, tyre parameters or calibration public or freely redistributable. A 2026 BMW academy account separately confirms use of a simulator configured as the M Hybrid V8. [N09, N10]

**Available:** collaboration and simulator-use accounts. **Not available:** an open BMW engineering data package. Historical RLL/WRT references must retain their program dates rather than implying an unchanged current roster.

**LapSim application:** distinguish a licensed consumer-simulation model from a transparent engineering reference. Consumer output can test data-analysis interfaces; it cannot establish measured Formula Student tyre or powertrain behavior.

## 8. Pratt Miller: multi-series simulation infrastructure

Pratt Miller announced acquisition of an AB Dynamics DIL system in August 2023, describing intended commissioning and its broader simulation experience across racing categories. That announcement is procurement evidence with a planned operational date; it is not an independent confirmation that every named customer program uses the same installed software. [N11]

**Available:** infrastructure strategy and multi-program experience. **Not available:** Corvette/customer-program models and calibrations.

**LapSim application:** preserve model adapters and ownership boundaries so one simulator framework can support several cars. Buy or build a motion system only after defining which driver-in-the-loop questions require its cues.

## 9. Ford Performance / Ford Chip Ganassi GT: historical Le Mans preparation

Ford's June 2016 account describes its racing simulator supporting Le Mans preparation. The case is retained as a historical example of driver/setup preparation; it does not describe a current Ford Chip Ganassi GT entry or a present-day software stack. [N12]

**LapSim application:** make scenario and procedure replay useful before pursuing a fully rendered racing game. Archive date-specific setup assumptions instead of silently carrying them into a new vehicle generation.

## 10. Hendrick Motorsports: aerodynamic and configuration automation

Siemens case studies describe NX/Teamcenter/Simcenter engineering workflows and STAR-CCM+ aerodynamic analysis at Hendrick. The aerodynamic case emphasizes automation of simulation preparation and operating-condition studies. Any quoted time savings are customer/supplier claims and do not establish a transferable accuracy or speed multiplier. Some case-study context is historical. [N13, N14]

**Available:** workflow and tool descriptions. **Not available:** a public NASCAR aerodynamic map, tyre model, setup optimizer or complete cluster configuration.

**LapSim application:** automate structured parameter sweeps and retain the exact model/input/output manifest for each trial. Screening a broad parameter space cheaply can be more useful than adding one expensive simulation that cannot be reproduced.

## 11. Team Penske: design-to-manufacturing traceability

Team Penske's February 2018 Siemens announcement and a Siemens NX case study describe CAD/CAE/PLM integration. The example ties geometric design, simulation, manufacturing and team collaboration together. This is historical evidence for that organization's engineering process, not proof of the Formula E team's software. [N15, N16]

**LapSim application:** associate each simulated result with a released geometry/configuration identifier and its approved source. A coefficient without the geometry revision that produced it is an incomplete engineering parameter.

## 12. Richard Childress Racing: historical multiphysics

Ansys's February 2018 announcement describes multiphysics use in Richard Childress Racing's car development. It supports structural/aerodynamic analysis as part of the engineering loop, but neither establishes an unchanged 2026 deployment nor supplies current racecar data. [N17]

**LapSim application:** add higher-fidelity offline analysis only where it supplies a needed model or parameter. Do not put detailed structural/CFD solvers inside the lap integration loop merely because a professional team uses them elsewhere.

## 13. Dallara: shared chassis supplier and planned facilities

Dallara's July 2026 announcement describes two Dynisma DMG-360XY systems: an Italian installation targeted for Q4 2026 and an Indianapolis installation for Q1 2027. These are plans as of the published account. Dallara's relationship to several racing categories does not prove that every team using its chassis has identical simulation infrastructure. [N18]

**LapSim application:** treat architecture reuse as a priority while keeping calibration specific to a vehicle and test condition. A shared chassis or model interface is not a shared parameter set.

## 14. Bosch and the LMDh hybrid ecosystem

IMSA's 2023 technical partnership announcement identifies Bosch contributions including the electric machine, inverter, hybrid control unit and brake-by-wire/system integration. This concerns a common hybrid subsystem; it does not establish that Bosch supplies every team's entire ECU, data logger or vehicle simulator. [N19]

**LapSim application:** define physical boundaries explicitly: wheel torque, machine torque, DC-terminal power, mechanical brake torque, and energy storage are different interfaces. Keep gearbox/differential ratios and losses in the proper direction for propulsion and regeneration.

## 15. Additional Formula E corroboration

Ansible Motion's March 2025 Penske AUTOSPORT/DS PENSKE account describes a Delta S3 installed in 2024 and four Theta Seat Sport systems delivered in January 2025. This gives more concrete deployment context for the prior AVL five-simulator report. Coupled simulators support interactive race and energy-management studies, but the vehicle/energy models remain proprietary. [N20; prior catalogue S29]

**LapSim application:** a repeatable headless experiment suite should come before a multi-driver facility. Simultaneous vehicles and opponents are a later research layer, not a prerequisite for validating independent-wheel torque allocation.

## 16. Public timing data: useful, but not raw vehicle telemetry

The IMSA and FIA WEC Al Kamel portals expose classifications and analysis resources. The reviewed WEC page listed lap/sector-related analysis and weather reports. These are potential resources for race-analysis software, not proof of access to steering, wheel torque, electrical power, suspension or tyre-state channels. Both pages displayed explicit redistribution restrictions. No timing datasets have been copied into this repository. [N21, N22]

An unaffiliated open-data wrapper was also surfaced, but a wrapper's software license or use of the word open does not establish permission to republish its upstream timing data. Start from official portals, review permissions, and retain downloads outside the public repository until reuse is authorized.

**LapSim application:** use authorized timing information to test session/stint/strategy analysis. Do not calibrate the Formula Student EV's tyre or energy model from unrelated professional race lap times.

## 17. New metrology detail: Red Bull Ford Powertrains

Hexagon's February 2026 technical release identifies CMMs, scanners, QUINDOS and Q-DAS in power-unit inspection and statistical quality analysis. It links physical measurement to model/configuration consistency, rather than treating nominal CAD as proof of the as-built part. This is additional F1 evidence, not a new open dataset. [N23]

**LapSim application:** record whether a geometry or inertia parameter is nominal CAD, supplier-rated, measured as-built, estimated, or fitted. Those evidence classes should survive parameter import and appear in saved results.

## 18. What this extension did not establish

No complete current proprietary tyre model, raw professional hybrid-controller source, full ECU calibration, or unrestricted team telemetry archive was found. Named motion vendors do not expose customer-owned physics. We did not infer a supplier for AF Corse, Aston Martin THOR, Alpine Endurance, Peugeot TotalEnergies or every GT/IndyCar entrant from adjacent manufacturer announcements. Their absence from a product-level table is a research gap, not evidence of inferior capability.

## Sources and evidence dates

Each N identifier represents one reviewed source locator. All were retrieved through a team, manufacturer, technical supplier, championship or supplier-issued release during the 11 October 2026 expansion; some rely on the retrieved search extract when the full page was inaccessible. No third-party source article is reproduced here.

- **N01, manufacturer, 30 May 2024, deployment:** https://hondanews.com/en-US/honda-racing/releases/release-f861e4df53b8ef3120e74b4caa0018b8-honda-racing-corporation-usa-unveils-latest-generation-driver-in-the-loop-simulator?selectedTabId=release-f861e4df53b8ef3120e74b4caa0018b8-photos
- **N02, supplier, September 2026, workflow:** https://www.ansiblemotion.com/ansible-motion-automotive-driver-in-the-loop-simulation-news/how-honda-uses-dil-simulators-to-gain-advantage-on-new-tracks
- **N03, manufacturer, 2 June 2026, team interview:** https://news.gm.com/home.detail.html/Pages/news/us/en/2026/jun/0602-cadillac-returns-to-le-mans-with-eyes-on-endurance-classic.html
- **N04, manufacturer, May 2025 account updated December 2025, testing plus installation plan:** https://motorsport.hyundai.com/media-center/news/2025/articles/endurance/wec/gmr-working-with-dynisma
- **N05, supplier, 21 July 2026, installed for 2027 program:** https://www.dynisma.com/news/dynisma-completes-dmg-1-installation-for-mclaren-hypercar-team
- **N06, supplier, 12 September 2012, historical:** https://www.dspace.com/en/pub/home/news/tmg_simulator.cfm
- **N07, supplier, 11 May 2023, deployment account:** https://info.archives.global.fujitsu/global/about/resources/news/press-releases/2023/0511-02.html
- **N08, manufacturer, 26 March 2024, simulator-to-track sequence:** https://newsroom.porsche.com/en_US/2024/motorsport/porsche-963-sebastian-vettel-aragon-35642.html
- **N09, manufacturer, October 2022, licensed collaboration:** https://www.press.bmwgroup.com/global/article/detail/T0405179EN/collaboration-with-iracing%3A-bmw-m-motorsport-is-the-first-manufacturer-to-launch-virtual-version-of-its-new-lmdh-car
- **N10, manufacturer, April 2026, M Hybrid V8 simulator use:** https://www.press.bmwgroup.com/deutschland/article/detail/T0456947DE/bmw-m-racing-academy%3A-%E2%80%9Eclass-of-2026%E2%80%9C-startet-in-muenchen-und-viareggio-in-kundensport-foerderprogramm?language=de
- **N11, engineering company, 11 August 2023, acquisition with target commissioning:** https://www.prattmiller.com/about/news/pratt-miller-announces-acquisition-of-new-driver-in-the-loop-simulator-system/
- **N12, manufacturer, 15 June 2016, historical:** https://media.ford.com/content/fordmedia/feu/en/news/2016/06/15/preparing-for-le-mans--ford-performance-racing-simulator.html
- **N13, supplier case study, historical context/date not pinned:** https://resources.sw.siemens.com/el-GR/case-study-hendrick-motorsport-digital-twin/
- **N14, supplier case study, workflow/date not pinned:** https://resources.sw.siemens.com/en-US/case-study-hendrick-motorsports-simcenter-star-ccm/
- **N15, team, 22 February 2018, historical agreement:** https://www.teampenske.com/news/index.cfm/c/690/53564/TEAM_PENSKE_FORMS_TECHNICAL_PARTNERSHIP_WITH_SIEMENS
- **N16, supplier, historical NX workflow:** https://resources.sw.siemens.com/en-US/case-study-team-penske-nx/
- **N17, supplier-issued release, 15 February 2018, historical:** https://news.cision.com/ansys-sweden-ab/r/richard-childress-racing-leverages-ansys-to-improve-racecar-speeds%2Cc2453019
- **N18, manufacturer, July 2026, planned Q4 2026/Q1 2027 installations:** https://www.dallara.it/en/2026/07/17/dynisma-nominata-partner-tecnologico-di-dallara-a-seguito-dellaccordo-per-due-simulatori-dmg-360xy/
- **N19, championship, 16 March 2023, hybrid-system partnership:** https://www.imsa.com/news/2023/03/16/bosch-and-imsa-announce-long-term-partnership/
- **N20, supplier, 6 March 2025, installed multi-simulator system:** https://www.ansiblemotion.com/ansible-motion-automotive-driver-in-the-loop-simulation-news/ds-penske-adopts-multi-simulator-setup-for-formula-e
- **N21, timing provider, portal inspected 11 October 2026, restricted redistribution:** https://imsa.alkamelsystems.com/
- **N22, timing provider, portal inspected 11 October 2026, restricted redistribution:** https://fiawec.alkamelsystems.com/
- **N23, supplier, 11 February 2026, metrology deployment:** https://hexagon.com/company/newsroom/press-releases/2026/red-bull-ford-powertrains-uses-hexagon-technology-to-ensure-super-high-performance-of-its-first-ever-f1-powertrain
