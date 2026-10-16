# Contributing

Contributions are welcome only when their provenance and intended licensing are
clear.

## Before submitting

- Read `LICENSE`, `LICENSE_SCOPE.md`, `NOTICE`, and `docs/licensing.md`.
- Do not submit proprietary, confidential, export-controlled, sponsor-restricted,
  or competition-sensitive information.
- Do not submit telemetry, vehicle parameters, calibration results, CAD,
  firmware, CAN databases, vendor files, standards, papers, images, or code
  copied from another source unless the repository maintainers have documented
  authority to accept and distribute it.
- Keep synthetic examples clearly labeled as synthetic.
- Preserve third-party notices and identify every external source.

## Licensing of a contribution

Unless a separate signed agreement states otherwise, intentionally submitting a
contribution for inclusion means that:

1. you represent that you created it or otherwise have authority to submit it;
2. you apply LSCRL-1.0 to the copyrightable portion you own or control;
3. you grant Repository Maintainers the Section 9.2 rights needed to review,
   modify, publish, distribute, and sublicense the contribution as part of the
   repository and its releases under LSCRL-1.0;
4. you understand that the contribution may be used by the Authorized UMD Team
   under Section 5 of LSCRL-1.0;
5. you do not grant the repository maintainers rights in third-party material
   beyond what its actual license permits; and
6. you understand that a contribution cannot authorize publication or use of
   UMD-, team-, sponsor-, employer-, or third-party-owned material.

Do not submit a contribution if you cannot make those statements.

## Commit sign-off

Every commit made after this policy is adopted must include a Developer
Certificate of Origin sign-off that matches the commit author:

```text
Signed-off-by: Your Name <your-email@example.com>
```

Add it with `git commit -s`. The sign-off certifies that you have the right to
submit the contribution under the repository's stated terms. A sign-off is not
a substitute for obtaining required UMD, team, sponsor, employer, or
third-party approval.

The pull request that first introduces this policy is the sole bootstrap
exception because the requirement did not exist on its base commit. The
`DCO sign-off` GitHub Actions workflow enforces the rule on every later pull
request.

## Pull-request checklist

A pull request should identify:

- original code and documentation created for the change;
- modified upstream files;
- third-party code, data, equations, images, or documents consulted or copied;
- any generated or AI-assisted content that requires human provenance review;
- whether the change contains or derives from team data;
- the tests run; and
- any ownership or publication question that remains unresolved.

Maintainers may reject or remove material when provenance or authority is not
adequately documented.
