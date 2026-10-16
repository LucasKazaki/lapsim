# TC-01M — Lipschitz-certified continuous yaw-feasibility search

Status: portable/offline reference and handoff only. No real vehicle model or controller is claimed.

## Decision

TC-01L's endpoint theorem is useful only while its lower-layer concavity assumptions hold. When an actual source model has an interior worst case, use a bounded one-dimensional global-search certificate instead of assuming the endpoints are sufficient.

TC-01M treats:
- `L(lambda)` as the minimum feasible yaw moment;
- `U(lambda)` as the maximum feasible yaw moment.

The exact robust continuous interval is:

`[max_lambda L(lambda), min_lambda U(lambda)]`.

With source-backed global Lipschitz constants, the portable reference uses Shubert/Piyavskii-style cone bounds to adaptively certify both scalar optimizations. It emits a guaranteed robust interval only when the search converges, observed samples do not contradict the supplied constants, and the constants are explicitly marked as source-backed.

Sample consistency alone is not accepted as proof of a Lipschitz constant.

## Frozen synthetic counterexample

The fixture uses:

`L(lambda) = 20 + 400 lambda (1-lambda)`

`U(lambda) = 300 - 600 lambda (1-lambda)`

on `[0,1]`.

Endpoint-only screening gives `[20, 300] N*m`, but the true interior worst case at `lambda=0.5` gives the continuous robust interval `[120, 150] N*m`.

Analytic rate bounds are:
- `|dL/dlambda| <= 400 N*m/lambda`;
- `|dU/dlambda| <= 600 N*m/lambda`.

With a 0.25 N*m certificate tolerance, the portable implementation used 101 oracle evaluations and returned the conservative guaranteed interval:

`[120.158909062214, 149.761636406680] N*m`.

Final global-certification gaps:
- max-lower gap `0.158909062213 N*m`;
- min-upper gap `0.238363593320 N*m`.

These are mathematical fixture values, not Terps Racing parameters.

## Portable verification

Commands:
- `python -S -m unittest -v test_lipschitz_yaw_certificate.py`
- `python -S -m py_compile lipschitz_yaw_certificate.py test_lipschitz_yaw_certificate.py`

Environment:
- CPython 3.13.5
- Linux x86_64

Result:
- 28/28 tests passed;
- 0 failed;
- 0 skipped;
- both commands exited 0.

SHA-256:
- reference `aef8da419aac44177584632f030f66bdc27863f1aa784936b852c8d980aad520`;
- tests `02ddde4086123f1582a43ffb4ce6cef0f7083d1628e7dacf0c19b456ff5ddc61`;
- fixture `4395b26a3f9baeac7a3e3dd94c2a6f4c2b6d545ed31e6d628b41607e9befa58a`.

Coverage includes endpoint-missed interior extrema, conservative certificate directions, deterministic refinement, source-backing gate, observed Lipschitz-violation rejection, finite evaluation budget, constant/linear functions, malformed oracle data, and explicit zero vehicle/performance/action authority.

## Sources

Primary method:
- Bruno O. Shubert, "A Sequential Method Seeking the Global Maximum of a Function," SIAM Journal on Numerical Analysis 9(3), 1972, DOI 10.1137/0709036.

Related no-known-constant alternative:
- Jones, Perttunen, Stuckman, "Lipschitzian Optimization Without the Lipschitz Constant," JOTA 79(1), 1993, DOI 10.1007/BF00941892.

Formula SAE lower-layer context remains SAE 2021-01-0373 and SAE 930763. Official Formula SAE resources listed 2027 Formula SAE Rules V1 at access on 2026-10-05.

## Limits

This is a one-dimensional numerical certificate. It does not derive safe Lipschitz constants for an arbitrary tire/suspension/motor model, and it is not vehicle validation. If no global source-backed constants can be justified, this method must remain a research fixture and another bounded global-optimization method should be used.

## Next source-specific action

Choose one actual continuous uncertainty in the authorized team simulator, derive or reject global rate bounds for the model's lower/upper feasible-yaw functions over a reviewed interval, and compare the certificate against an independent dense sweep. Do not tune a bound merely to reduce evaluation count.
