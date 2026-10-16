# TC-02CQ: IID recovery qualification can misstate burst behavior

Scope: synthetic offline research only for the 2027–28 U.S. Formula SAE Electric torque-control project. This note supplements TC-02CP; it is not MCU, inverter, team-interface or vehicle evidence. Inspected ENME408 research PR #66 at `31533ebdcaddb53925d5acb77b0126415832159c`, 2026-10-11. No independent review or native Company Runtime ACK was observed.

## Checked decision

Do not treat the TC-02CE IID consecutive-good-sample model as a general recovery latency predictor. A two-state Good/Bad Markov sensitivity fixture with an explicit initial distribution and conditional transition probabilities demonstrates the limitation. The two hypothetical processes below both have stationary P(Good)=0.5:

| Process | P(G next \| G) | P(G next \| B) | P(2 consecutive G by 12 observations) | P(3 consecutive G by 3 observations) |
| --- | ---: | ---: | ---: | ---: |
| IID | 0.5 | 0.5 | 0.907958984375 | 0.125 |
| Persistent | 0.95 | 0.05 | 0.6761478874014673 | 0.45125 |

Thus IID can overstate a long-horizon recovery chance by 23.18 percentage points and understate an early-window chance by 32.625 points under different declared scenarios. Correlation is not uniformly conservative or nonconservative. Samples are not seconds, and new controller ticks need not represent newly received sensor frames. All transition probabilities are research assumptions, **not** Terps Racing data.

## Portable verification and integration boundary

Local standalone dynamic programming oracle `markov_recovery_sensitivity.py` SHA-256 `9608dbce221dc9f73cb9ddecbc13067a741bf7f964c435d870c7bb43315c4a6c` and new tests SHA-256 `e59f46826320a6a67946ab6b7a2d312104be3e752cd2bd534301d3fb487db985`. Linux x86-64 / CPython 3.13.5, standard-library CPU: 16 new + 19 archived TC-02CP tests passed (35 total), exit 0. Independent brute-force path enumeration and IID reduction were tested; an intentionally wrong IID-substitution model produced three expected failures, exit 1. Two initial test-expectation errors were corrected and retained in the local packet.

These new scripts are **not published by this note**. The original TC-02CP recovery model/test pair remains the first review/integration priority. Do not stage additional research fixtures until the existing pair has a fresh head/path/ownership check, full repository suite and independent review. Company Runtime registration and local-worker read remain unverified. No vehicle commands or hardware/firmware modifications are authorized.

Primary source: Gilbert, E. N. (September 1960), *Capacity of a Burst-Noise Channel*, Bell System Technical Journal 39(5), 1253–1265, DOI https://doi.org/10.1002/j.1538-7305.1960.tb03959.x. This fixture is a simplified two-state Markov Good/Bad process, **not** Gilbert's exact burst-channel model. Official STM32F405 family references: https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html (RM0090 V22, ES0182 V19). U.S. rules index: https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx (2027 Rules V1 as accessed 2026-10-11). None approves this recovery policy.

Next: an authorized reviewer should assess the existing TC-02CP two-file patch and ask for a read-only timestamped qualified-observation bench trace before fitting correlated recovery probabilities.
