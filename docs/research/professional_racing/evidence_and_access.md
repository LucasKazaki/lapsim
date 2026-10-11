# Evidence, access and validation notes

Research consolidation: 11 October 2026. Reviewed repository baseline: `67b3659a4d9dcf88a7074fb52b526f19d9aee30b`.

## Evidence types are not interchangeable

- A **team/manufacturer deployment account** supports the named program and date, not every customer or later season.
- A **supplier case study** can establish a product relationship. Performance gains remain supplier/customer claims unless independently validated.
- An **announcement** is evidence of a contract or plan, not completed commissioning.
- A **historical case** establishes past use, not an unchanged current stack.
- A **job description** establishes a requested skill, not necessarily a deployed system.
- A **repository listing or documentation** establishes inspectable material, not a successful build, complete calibration, or safe controller.
- A **file listing** establishes filenames and metadata only. It does not establish decoded channels, anonymous access or redistribution rights.
- A **model-generated channel** is not a physical measurement, and a derived estimator is not independent validation of its own inputs.

The new technical cases primarily use teams, manufacturers, suppliers and championships. A prior firsthand-driver interview is retained with its limitation. Older supplier press-release mirrors remain explicitly labeled in the F1 source list. Retained sources have not all been re-fetched in this expansion.

## Corrections and refinements to the earlier discussion

**Ferrari:** the initial broad summary omitted a concrete historical simulator disclosure. The consolidated report includes the July 2021 Ferrari/Dynisma completion announcement and its subsequent calibration/use plan. It also adds a specific AWS pit-stop analysis case instead of attributing all Ferrari-wide cloud services to the F1 engineering loop. See F19-F20.

**Alpine:** the earlier named-DIL gap is superseded by the May 2026 disclosure that installation was completed during 2025. This is evidence of installed hardware, not a public vehicle-model package. See F24.

**Audi/Sauber:** HPE's 2023 Sauber GreenLake case supplies named historical CFD infrastructure. It does not prove Audi's complete 2026 platform is unchanged. See F36.

**Cadillac:** GM's simulator/correlation accounts add engineering detail beyond IFS and additive manufacturing. The virtual Spanish Grand Prix was a June 2025 preparation exercise, not an actual Cadillac F1 race entry. See F39-F40.

**Motion Applied:** use the current product page's Motion Control Toolbox name. Do not assume that a headline sample rate is every channel's rate or a verified aggregate radio throughput. Product latency is not whole-vehicle or transcontinental latency. See F01-F04.

**Penske and McLaren identities:** Penske AUTOSPORT, Team Penske and Porsche Penske Motorsport must not be merged into one software deployment. McLaren F1, McLaren Automotive and McLaren Hypercar disclosures are likewise program-specific.

**Rules:** F2/F3 logging is not unrestricted moving-car telemetry. Formula E has season-specific and conditional provisions; Season 12 is not Season 13. None of these rulebooks establishes Formula SAE permission for a controller or aerodynamic system. The archived rulebook entries preserve the prior review date; they are not a new rules audit.

## Data access and redistribution

The F4 U.S. archive was listed through an authenticated connector in the preceding review. Three VIR `.stf` files were observed, but not decoded. Their actual channel coverage, anonymous availability and reuse permissions are unresolved. Only the official links and observed filenames are included here. [Prior catalogue S16-S18]

Waterloo code/logs, UBC firmware, OpenLAP, TUM and other public repositories have different licenses and data provenance. Inspect their current licenses and bundled third-party material before copying code or measurements. A software license does not necessarily grant permission to redistribute every dataset in a repository. No third-party firmware or logs are vendored by this commit. [S38-S47]

TTC measurements are institution/member restricted. Check authorized UMD access and keep raw or restricted derived material outside the public repository. Use synthetic regression fixtures when public tests are needed. [S48]

The inspected Al Kamel IMSA and WEC portals explicitly displayed restrictions on redistribution. Public viewing and export links do not automatically permit mirroring. No timing archive is copied here, and no unofficial wrapper's open-source license is treated as permission to redistribute its upstream data. [Additional report N21-N22]

Private Terps evidence bundles, CAN logs, parameter selections and credentials remain outside this research package. Retain the repository's existing source-profile allowlists and external-evidence boundary.

## Verification performed and limits

The live repository was read through the authenticated GitHub connector. The inspected materials included the README, architecture, four-wheel dynamics, source-profile documentation, and part of `src/vehicle_model/mech/tire.py`. This supports a targeted roadmap, not a complete numerical audit of every solver.

The preserved catalogue's Git blob is `970890b772cb1c207c2447d6a70fc59bd7289c20`, matching the original supplied Markdown byte-for-byte. Its SHA-256 is `96ef2656cd1da833f6556d8728176636d43c64fe4f6d071e0763f02d9b163892`. A local parser recovered all 50 entries and compared every source record with the original companion JSON; all records matched exactly. The catalogue therefore retains the original JSON source metadata as well as the narrative/access notes.

The proposed backlog is not implementation evidence. No simulation model, controller, workflow permission or runtime dependency is changed by this upload. No full repository test suite, external firmware build, third-party simulator benchmark, decoded professional dataset analysis, HIL bench experiment or physical vehicle validation was performed in this research task.

External source pages can change or disappear. Successful retrieval on a research date does not guarantee permanent access. Record replacements and changed evidence status rather than silently rewriting a historical claim.
