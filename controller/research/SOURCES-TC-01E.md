# TC-01E sources

Accessed 2026-10-03.

- NIST TN 1297 Appendix A, Law of Propagation of Uncertainty:
  https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty
  First-order propagation uses sensitivity coefficients, standard uncertainties, and covariance terms.
- Julio-Rodríguez, Santana-Díaz, Ramirez-Mendoza, Applied Sciences 2021, DOI 10.3390/app11104679:
  https://www.mdpi.com/2076-3417/11/10/4679
  Electronic-differential work using vehicle kinematics; no Terps Racing parameters are imported.
- Sun, Lee, Tian, SAE 2021-01-0373:
  https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373
  Separates direct-yaw-moment control from lower torque distribution.
- Formula SAE Series Resources:
  https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx
  Current resource listing exposes 2027 Formula SAE Rules V1.

Project pins:
- kinematic_ediff.py blob 304e50e04a5d3e9a6d07aaa78ae4456da27af1ed
- TC-01B.md blob 477fba61d6687f725ee14bbaa3230d672d36f593
- kinematic_observer.py blob e8721a7b7c6f4382995bbf1f773276d3e9f2290b

Applicability: these sources support uncertainty-aware kinematic-reference analysis. They do not establish vehicle geometry, sensor uncertainty, covariance, thresholds, interfaces, or control policy.
