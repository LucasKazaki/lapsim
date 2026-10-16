# Local worker licensing instructions

The repository uses **LSCRL-1.0**, a source-available, competition-restricted
license. It is not an OSI-approved open-source license.

## Required behavior

1. Preserve `LICENSE`, `LICENSE_SCOPE.md`, `NOTICE`, `CONTRIBUTING.md`, and
   `docs/licensing.md`.
2. Do not replace or supplement LSCRL-1.0 with MIT, Apache-2.0, BSD, GPL,
   AGPL, MPL, Creative Commons, The Unlicense, or another license without an
   explicit maintainer decision and rights-holder review.
3. Treat `LICENSE_SCOPE.md` as controlling provenance. Do not claim that the
   entire repository is licensed until the upstream rights holders and every
   other applicable owner expressly authorize that statement.
4. Do not publish telemetry, measured or reconstructed vehicle data, track
   data, calibrations, fitted parameters, vehicle configurations, firmware,
   CAD, CAN databases, vendor files, credentials, or sponsor-restricted
   material without file-specific authority.
5. Keep competition-sensitive implementation and data in access-controlled
   storage even when the public portfolio remains available.
6. Run `python scripts/check_license_policy.py` after any licensing,
   packaging, release, or provenance change.
7. Before producing a Windows distribution, confirm that the archive contains
   the project license, scope notice, notice, contribution policy, and
   licensing guide.
8. Record legal or ownership uncertainty as an issue; do not invent permission
   or silently broaden the license.

## Sync procedure after the licensing PR merges

```bash
git fetch origin
git switch main
git pull --ff-only origin main
python scripts/check_license_policy.py
```

Then run the repository's normal full verification workflow before publishing a
new release. A passing software test does not establish ownership, legal
enforceability, real-car accuracy, or permission to publish excluded data.
