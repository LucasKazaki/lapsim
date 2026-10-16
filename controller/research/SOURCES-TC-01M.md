# SOURCES-TC-01M — Lipschitz-certified continuous uncertainty search

Accessed 2026-10-05.

## Shubert — one-dimensional global search with a rate-of-change bound

Bruno O. Shubert,
"A Sequential Method Seeking the Global Maximum of a Function,"
SIAM Journal on Numerical Analysis 9(3), 379–388, September 1972.
DOI: 10.1137/0709036
https://doi.org/10.1137/0709036

Primary-source abstract:
- considers a scalar objective on a closed interval;
- assumes a bound on the rate of change is available;
- develops a sequential global search method and discusses computation;
- the method is shown minimax under its assumptions.

Applicability to TC-01M:
TC-01M uses the same Lipschitz-envelope idea for two scalar functions of one
continuous uncertainty variable:
- lower feasible yaw bound L(lambda), whose global maximum is needed;
- upper feasible yaw bound U(lambda), whose global minimum is needed.

TC-01M does not claim a Lipschitz bound merely because sampled points happen to
be consistent with one. The bound must be derived/reviewed from the actual
source model before the result is labeled a guarantee.

## Jones, Perttunen, Stuckman — optimization without a known Lipschitz constant

D. R. Jones, C. D. Perttunen, B. E. Stuckman,
"Lipschitzian Optimization Without the Lipschitz Constant,"
Journal of Optimization Theory and Applications 79(1), 157–181, October 1993.
DOI: 10.1007/BF00941892

Applicability:
This is a relevant alternative family when a trustworthy Lipschitz constant is
not available. TC-01M deliberately does not implement DIRECT or claim its
guarantees. It keeps the source-backed-bound requirement explicit.

## Formula SAE torque-vectoring context

Yiwen Sun, Runfeng Lee, Guangyu Tian,
"Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE
Racing Car," SAE Technical Paper 2021-01-0373, published 2021-04-06.
DOI: 10.4271/2021-01-0373
https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373

Primary-source abstract:
- two-layer torque-vectoring architecture;
- upper layer requests direct yaw moment;
- lower layer estimates wheel vertical load and distributes torque using tire
  friction-ellipse lateral-force margin;
- the underlying vehicle model uses measured/identified vehicle parameters.

Applicability:
TC-01M remains a lower-layer feasibility/certification tool. It does not
generate the target yaw moment.

## LLTD context

Chris L. Clover, James E. Bernard,
"The Influence of Lateral Load Transfer Distribution on Directional Response,"
SAE Technical Paper 930763, published 1993-03-01.
DOI: 10.4271/930763
https://saemobilus.sae.org/papers/influence-lateral-load-transfer-distribution-directional-response-930763

Primary-source abstract:
- front/rear lateral load-transfer distribution depends on roll stiffness and
  suspension geometry;
- LLTD materially affects directional response.

Applicability:
This supports treating LLTD, or a related suspension/load-transfer parameter, as
an uncertainty that must come from source-backed team evidence.

## Formula SAE rules

Official Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current listing at access:
- `2027 Formula SAE Rules` — Version `V1`.

TC-01M derives no Lipschitz constant, LLTD range, tire coefficient, torque limit,
yaw target, sample period, geometry, or safety threshold from the rules.

## Mathematical certificate used by TC-01M

For adjacent samples `(a, f(a))`, `(b, f(b))` and a valid Lipschitz constant K:

- certified upper bound on `max f` over `[a,b]`:
  `(f(a) + f(b) + K*(b-a))/2`;
- certified lower bound on `min f` over `[a,b]`:
  `(f(a) + f(b) - K*(b-a))/2`.

TC-01M adaptively evaluates the cone-intersection point associated with the
largest remaining global-certification gap.

For robust yaw:
- exact robust lower endpoint is `max_lambda L(lambda)`;
- exact robust upper endpoint is `min_lambda U(lambda)`.

If the global-max certificate for `L` has upper bound `B_L` and the global-min
certificate for `U` has lower bound `B_U`, then `[B_L, B_U]` is a conservative
guaranteed robust interval, provided:
- both source-backed Lipschitz bounds are valid globally;
- every oracle evaluation returns a valid feasible interval `L <= U`;
- the search reaches its requested tolerance.

Observed sample consistency is only a falsification check. It cannot establish
that the global Lipschitz bound is valid between unsampled points.
