# Repository agent instructions

These instructions apply to automated coding agents, local workers, and human-assisted agents operating anywhere in this repository.

## Read before changing or publishing anything

Read and follow, in this order:

1. `LICENSE`
2. `LICENSE_SCOPE.md`
3. `NOTICE`
4. `CONTRIBUTING.md`
5. `LOCAL-WORKER.md`
6. `docs/licensing.md`

LapSim is **source-available, not open source**. LSCRL-1.0 permits specified recruiter evaluation, UMD educational use, and Terps Racing use of Covered Material. It does not permit another student vehicle competition program, or anyone acting for that program, to use Covered Material or generated results for Competition Use.

## Mandatory constraints

- Do not replace, remove, broaden, or supplement LSCRL-1.0 without an explicit maintainer decision, documented rights-holder authority, and legal review.
- Do not describe the entire repository as uniformly licensed. The inherited `terps-racing-ev/lapsim` baseline, other contributors' material, third-party content, and engineering data remain subject to `LICENSE_SCOPE.md`.
- Do not publish telemetry, measured or reconstructed vehicle or track data, calibrations, fitted parameters, vehicle-specific configurations, firmware, CAD, PCB files, CAN databases, vendor files, credentials, personal data, sponsor-restricted material, or other competition-sensitive information without file-specific authority.
- Do not infer permission from public visibility, a Git commit, an issue comment, a Slack message, or repository ownership.
- Preserve all project and third-party license, attribution, provenance, validation, and safety notices.
- Keep public examples synthetic or independently authorized whenever possible.
- Record unresolved ownership, data-rights, or publication questions instead of assuming permission.

## Required checks

After any change to licensing, provenance, contribution rules, packaging, release documentation, or agent instructions, run:

```bash
python scripts/check_license_policy.py
```

Before publishing a build or release, run the complete repository verification workflow and confirm the distribution includes the controlling legal and provenance files. Follow `LOCAL-WORKER.md` and `docs/release.md`.

All changes must use the repository's protected pull-request workflow. Follow the provenance checklist in `CONTRIBUTING.md` and use Developer Certificate of Origin sign-off where required.
