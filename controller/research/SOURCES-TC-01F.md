# TC-01F sources

Accessed 2026-10-03.

## Primary standards

NIST Technical Note 1297, Appendix A — Law of Propagation of Uncertainty
https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty
- Eq. A-3 gives first-order uncertainty propagation with sensitivity coefficients and covariance.
- NIST page was current when accessed 2026-10-03.

JCGM 101:2008 — Evaluation of measurement data, Supplement 1 to the GUM:
Propagation of distributions using a Monte Carlo method
https://www.bipm.org/en/doi/10.59161/jcgm101-2008
DOI: 10.59161/JCGM101-2008
Official PDF:
https://www.bipm.org/documents/20126/2071204/JCGM_101_2008_E.pdf/325dcaad-c15a-407c-1105-8b7f322d651c
- Section 5.8 discusses validity conditions for nonlinear-model GUM propagation.
- Section 5.9 describes Monte Carlo propagation.
- Section 7.2 states that required trial count depends on the output distribution and numerical objective; 1e6 is noted as an often-useful scale for some 95% coverage-interval calculations and adaptive procedures are available.
- JCGM copyright remains with the JCGM organizations; this research cites rather than redistributes the document.

## Control/reference context

Julio-Rodríguez, Santana-Díaz, Ramirez-Mendoza,
“Individual Drive-Wheel Energy Management for Rear-Traction Electric Vehicles with In-Wheel Motors,”
Applied Sciences 11(10):4679, published 2021-05-20.
DOI 10.3390/app11104679.
https://www.mdpi.com/2076-3417/11/10/4679
- supports geometry-based electronic-differential wheel-speed references;
- vehicle-specific parameters/results are not imported.

Sun, Lee, Tian,
“Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE Racing Car,”
SAE 2021-01-0373, published 2021-04-06.
DOI 10.4271/2021-01-0373.
https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373
- separates upper direct-yaw-moment control from lower torque distribution.

Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx
- current observed resource: 2027 Formula SAE Rules, Version V1.
- TC-01F derives no tolerance, sensor limit, or controller threshold from that resource.

## Project pins

- reference/kinematic_ediff.py blob 304e50e04a5d3e9a6d07aaa78ae4456da27af1ed
- reference/kinematic_observer.py blob e8721a7b7c6f4382995bbf1f773276d3e9f2290b
- research/TC-01B.md blob 477fba61d6687f725ee14bbaa3230d672d36f593
- research/SOURCES-TC-01E.md blob 572f738732bebfb7b9213720eb0e88a3f83fe962

Applicability:
These sources support the numerical method and control-layer separation. They do not establish Terps Racing geometry, uncertainty distributions, covariance, steering range, residual thresholds, or vehicle acceptance.
