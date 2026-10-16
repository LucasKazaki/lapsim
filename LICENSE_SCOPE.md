# License scope and provenance

Status date: October 16, 2026

This is the **Scope Notice** incorporated into the version of the **LapSim
Source-Available Competition-Restricted License 1.0 (LSCRL-1.0)** distributed
with it. It records known provenance and prevents the root `LICENSE` file from
being read as a claim that one person owns or can license every item in this
repository.

## 1. Repository ancestry

This repository descends from `terps-racing-ev/lapsim` through upstream commit:

`4b55928cffbc8a5a3dbf8f489dec791f7d791269`

That upstream history includes copyrightable work committed under the names
`Adi` and `funnysomething`. The upstream repository did not declare a project
license when this notice was prepared.

**The upstream baseline and any portions derived from it are not Covered
Material under LSCRL-1.0 merely because this repository contains the root
license.** They remain subject to the rights of their respective owners unless
and until each applicable owner, or a person legally authorized to act for that
owner, expressly adopts LSCRL-1.0 or another written license.

## 2. Maintainer-authored additions

LucasKazaki applies LSCRL-1.0 to the copyrightable portions of original
contributions that LucasKazaki owns or controls and that were added after the
upstream commit identified above.

This statement does not:

- claim ownership of pre-existing upstream expression;
- claim ownership of another contributor's work;
- override third-party licenses;
- convert facts, ideas, equations, methods, algorithms, or unprotectable
  material into copyrighted property; or
- grant rights in material for which LucasKazaki lacks licensing authority.

Repository history can help identify provenance but is not conclusive proof of
copyright ownership.

## 3. Future contributions

A contribution intentionally submitted and accepted after LSCRL-1.0 appears in
the repository is Covered Material only to the extent that its contributor has
the necessary rights and applies the license under Section 9 of LSCRL-1.0 or a
separate signed agreement.

## 4. Data and engineering evidence excluded from the software license

Unless a file-specific notice signed by the applicable rights holder expressly
states otherwise, LSCRL-1.0 does **not** license:

- raw or processed telemetry and log files;
- measured or reconstructed vehicle, track, GNSS, IMU, CAN, battery, inverter,
  motor, tire, or driver data;
- calibration results, fitted coefficients, derived parameter sets, and
  vehicle-specific configurations;
- competition submissions, rule-check evidence, setup recommendations, and
  team decision records;
- CAD, PCB, firmware, hardware designs, CAN databases, vendor files, and
  sponsor-provided material; or
- credentials, personal data, confidential information, or material published
  by mistake.

This exclusion applies to team-derived measurements and outputs under
`analysis/data/`, `outputs/`, and `output/` unless a file-specific notice says
otherwise. It includes the bundled derived course files
`analysis/data/track/gnss_imu_endurance_track.csv` and
`analysis/data/track/gnss_imu_endurance_track.json` unless their applicable
rights holders later provide a file-specific written license.

Public visibility is not permission to use excluded material.

## 5. Third-party software and documents

Dependencies, copied excerpts, standards, rules, research papers, images,
fonts, datasets, vendor documents, and other third-party material remain under
their own terms. Their inclusion, reference, or packaging does not place them
under LSCRL-1.0. The license and notice files distributed with a dependency
control for that dependency.

## 6. Current adoption status

| Rights holder or material | LSCRL-1.0 status |
| --- | --- |
| Copyrightable original contributions owned or controlled by LucasKazaki | Adopted, subject to this scope file |
| Upstream `terps-racing-ev/lapsim` baseline through commit `4b55928c...` | Pending express authorization; not presently covered |
| Contributions owned by other people or entities | Covered only after their express adoption or other written authorization |
| Engineering data and evidence described in Section 4 | Excluded unless expressly licensed file by file |
| Third-party material | Governed by its own terms |

## 7. Required review before representing the whole repository as licensed

Do not state that the entire repository is licensed under LSCRL-1.0 until all
of the following are documented:

1. authorization from every applicable owner of the upstream baseline;
2. confirmation of whether UMD, a sponsor, a course agreement, or another
   contract owns or restricts any relevant software or data;
3. contributor and third-party provenance review;
4. approval to publish each team-derived dataset or engineering artifact; and
5. review of the custom license and the proposed publication scope by
   qualified counsel or the appropriate UMD intellectual-property office.

Until then, LSCRL-1.0 is an effective grant only for Covered Material whose
rights holder has actually adopted it. All other rights are reserved.
