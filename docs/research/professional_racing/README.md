# Professional racing research for a Formula Student EV simulator

Consolidated **11 October 2026** for ENME408/Terps Racing LapSim. Repository baseline reviewed: `67b3659a4d9dcf88a7074fb52b526f19d9aee30b`.

## Read by purpose

| Document | Contents |
|---|---|
| [Development roadmap](lapsim_development_roadmap.md) | Ten proposed work packages grounded in existing LapSim interfaces, with dependencies, physical questions and acceptance tests. |
| [Machine-readable backlog](backlog.json) | Priorities, source references, inspected code areas and implementation status. All tasks begin as proposed. |
| [F1 systems and teams](f1_teams_and_telemetry.md) | Telemetry/control/logging architecture, simulation layers, all 11 organizations from the F1 review, and additional Ferrari/Alpine/Audi/Cadillac evidence. |
| [Formula ladder and electric racing](formula_ladder_and_electric.md) | F2/F3 organization matrix, regional F4 data access, Season 12 Formula E teams, student-team code/logs and accessible simulation research. |
| [Additional professional programs](additional_professional_teams.md) | HRC, Cadillac/JOTA/WTR, Genesis, McLaren Hypercar, Toyota, Porsche, BMW, Pratt Miller, Ford, Hendrick, Team Penske, RCR, Dallara and hybrid/data suppliers. Includes 23 N-series source entries. |
| [Preserved 50-source catalogue](formula_racing_research_catalogue_2026-10-10.md) | Earlier source URLs, evidence dates, limitations, F4 file-listing evidence and licensing/access boundaries, preserved byte-for-byte. |
| [Evidence, access and validation notes](evidence_and_access.md) | Corrections to earlier broad statements, source quality, data restrictions, verification performed and limits of this upload. |

Source identifiers **S01-S50** refer to the preserved catalogue. **F identifiers** refer to the F1 report's sources (F12 unused). **N01-N23** refer to the additional-program report. Identifiers are not a count of unique URLs or distinct teams: a manufacturer can support several programs, and a case study can have several source locators.

## Most useful conclusions for this repository

The research supports investing first in a consistent signal/quality contract, realistic actuator and regeneration constraints, fixed-clock controller tests, and multi-channel model correlation. It does not justify replacing the existing simulator with a game or purchasing professional motion hardware before those interfaces and models are credible.

The existing repository already has component models, event APIs, recorded replay, provenance-aware profiles, battery validation, four-corner tyre work, and a separate transient four-wheel experiment. The roadmap therefore focuses on integration and remaining validity limits rather than proposing those features as entirely new.

These are engineering recommendations, not measured performance improvements. An attractive lap time can result from compensating model errors or infeasible commands. Preserve source, configuration, numerical settings and uncertainty in every comparison.

## Scope and maintenance

F1 coverage retains 11 organizations; F2/F3 coverage retains 11 organizations reviewed across those categories; Formula E coverage is explicitly the 10 organizations from the 2025/26 Season 12 review. F4 and additional professional categories are selected evidence-backed cases, not an exhaustive worldwide roster. No complete proprietary team model or unrestricted professional telemetry archive was found.

For future updates, record publication date, event/deployment date, access date, evidence type, named program, supported claim and limitation. Recheck an announced installation before upgrading its status. Keep source locators and original summaries rather than copying third-party articles or restricted datasets. Do not silently substitute professional-car parameters for missing Formula Student measurements.

This commit adds research documentation and a proposed backlog only. It does not change simulator runtime code, enable new controllers, or certify a vehicle design.
