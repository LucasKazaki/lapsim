# Licensing and permitted use

LapSim is **source-available, not open source**. The controlling terms are the
root [LICENSE](../LICENSE), the incorporated
[LICENSE_SCOPE.md](../LICENSE_SCOPE.md), and [NOTICE](../NOTICE). This page is a
plain-language guide and does not replace those files.

## What the license is intended to allow

- Anyone may inspect the public repository subject to GitHub's terms and
  applicable law.
- Recruiters, hiring managers, and technical reviewers who are not acting for
  a competing student vehicle team may download, run, and privately modify
  covered material solely to evaluate the project or its contributors.
- Current University of Maryland, College Park students, faculty, and staff may
  use covered material for coursework, teaching, independent study, and
  noncommercial academic research, provided the work is not for another
  competition team.
- Current UMD Affiliates acting for Terps Racing, including its Electric
  Vehicle program, may use covered material internally for that UMD program's
  vehicle development, simulation, testing, controls, and competition work.

## What is not licensed

Other Formula SAE, Formula Student, Formula Hybrid + Electric, Formula Bharat,
SAE Collegiate Design Series, and substantially similar student vehicle teams
may not use covered material, modified versions, or software-generated results
for their vehicle or competition program. They may not route the work through
members, advisors, sponsors, contractors, consultants, vendors, cloud
services, or automated agents.

Public redistribution, commercial product development, hosted simulation
services, and sublicensing also require a separate Signed Writing from every
applicable rights holder.

## What a public license cannot do

A public repository is technically available for others to inspect and fork
through GitHub. A license supplies legal conditions; it is not an access
control. It cannot guarantee that every reader will comply, make already
published copies disappear, turn public information into a trade secret, or
prevent an independent implementation of uncopyrighted ideas, equations,
algorithms, systems, or methods.

For that reason, vehicle-specific calibrations, telemetry, controller tuning,
private firmware, CAN definitions, and other competition-sensitive engineering
material should remain in access-controlled storage even when the public
portfolio repository stays visible.

## Important coverage limitation

The repository descends from `terps-racing-ev/lapsim`. The upstream baseline
did not contain a project license when LSCRL-1.0 was added here. LucasKazaki
can license only the copyrightable contributions that LucasKazaki owns or
controls. The upstream baseline and other contributors' material are not
covered until their applicable rights holders expressly authorize a license.

This distinction matters. A license file cannot grant rights that its committer
does not own. See `LICENSE_SCOPE.md` for the current adoption table and the
specific upstream commit.

## Data is handled separately

The software license does not automatically cover telemetry, GNSS/IMU-derived
tracks, vehicle parameters, calibration results, CAN databases, competition
evidence, firmware, CAD, vendor files, or other team engineering data. Those
items require file-specific authority. Availability in a public repository is
not permission to use them.

## Practical examples

| Activity | Result under LSCRL-1.0 |
| --- | --- |
| A company recruiter reviews the architecture and runs a synthetic demo to assess a candidate | Permitted for covered material |
| A UMD student modifies the simulator for a class project unrelated to another racing team | Permitted for covered material |
| Terps Racing EV tunes its own vehicle with covered material | Permitted for covered material |
| Another Formula SAE team runs the simulator with its own car parameters | Prohibited |
| A consultant runs it on behalf of another Formula Student team | Prohibited |
| A competitor copies only the torque-control module | Prohibited |
| Someone republishes a modified public fork as a general racing simulator | Not permitted without written authorization |
| A reader independently implements an idea or equation without copying protected expression | Not granted or prohibited by this license; applicable law controls |

## Why this is not called open source

Open-source licenses must allow use in any field of endeavor. LSCRL-1.0
deliberately restricts competition-team use, so describing this repository as
"open source" would be inaccurate. Use "public source" or "source-available."

## Requests for additional permission

Open a repository issue describing:

1. the person and organization requesting permission;
2. the exact files or release involved;
3. the intended use, users, and duration;
4. whether any competition program will benefit; and
5. whether redistribution, publication, deployment, or commercial use is
   planned.

No additional permission exists unless every applicable rights holder
provides it in a Signed Writing as defined by LSCRL-1.0.

## Legal and institutional review status

LSCRL-1.0 is a custom license drafted to express the project's intended
permissions and restrictions. It is not an OSI-approved license and has not
been represented as approved by UMD or by legal counsel. Before the entire
repository is described as licensed, the upstream rights holders, applicable
contributors, UMD ownership authorities, and counsel should review the
provenance and terms identified in `LICENSE_SCOPE.md`.
