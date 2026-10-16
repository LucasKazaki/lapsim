# TC-01K branch-completion receipt — 2026-10-05

Scope: close the repository implementation gap behind the already-persisted TC-01K source index.

Current repository evidence:
- PR #66 was open/draft/mergeable at `9b07833107232333f0bd937343a1b37ba2f8ac05`;
- branch comparison: 88 ahead / 0 behind `ops/school-focus-20260930`;
- no PR comments, submitted reviews, or inline review threads;
- `research/SOURCES-TC-01K.md` exists;
- `reference/robust_yaw_uncertainty.py` and its test file were absent.

Primary-source recheck:
- SAE 2021-01-0373 describes a two-layer Formula SAE torque-vectoring controller with lower-layer vertical-load estimation and friction-ellipse margin.
- SAE 930763 states front/rear lateral-load-transfer distribution depends on roll stiffness and suspension geometry.
- Serralvo Neto et al., WEVJ 2023, DOI 10.3390/wevj14070183, calibrated a Formula SAE model from instrumented 2WD telemetry before 4WD prediction.
- Formula SAE Series Resources currently lists 2027 Formula SAE Rules V1.

Portable implementation prepared:
- finite LLTD scenario intersection;
- quasi-static normal-load screen;
- idealized friction-circle longitudinal reserve;
- actuator/tire torque-cap intersection;
- exact yaw extrema for a fixed positive total request;
- nonpositive wheel-load blocking;
- deterministic JSON and explicit zero action authority.

Portable verification:
- `python -S -m unittest -v test_robust_yaw_uncertainty.py` -> 22/22 passed;
- `python -S -m py_compile robust_yaw_uncertainty.py test_robust_yaw_uncertainty.py` -> exit 0;
- reference SHA-256 `312c4d8aff0b224a936e244da6d33730f1909647a7303b43cac221ddb285b273`;
- test SHA-256 `02b919fb033496e98efa1f24f55a66eebfcc6579141cc2b5bfa80d891da1098d`.

GitHub persistence:
- one normal Contents-API create for `projects/enme408-torque-control/reference/robust_yaw_uncertainty.py` was blocked before mutation by connected safety checks;
- no alternate branch, low-level Git object/ref write, force update, or bypass was attempted.

Evidence level: host-side portable screening implementation only. This is not real firmware, tire validation, vehicle-performance evidence, HIL, or track evidence.

Next source-specific action: bind the actual team suspension/LLTD model, tire combined-force source, rolling radii, and speed-dependent motor/inverter limits before replacing synthetic scenarios or treating the yaw envelope as a controller limit.
