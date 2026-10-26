# Demonstration course library

Three portable v1 bundles, shared by Controller Lab and the standalone torque
configurator's course comparison. The existing desktop course-bundle importer
can also read these files; new desktop GUI acceptance is not claimed here.
Select a course in the existing **Course** menu, or pass `--course bundle
--course-bundle configs/courses/<id>.json` to the tournament CLI. Expand
**Selected course map and source** to inspect the setup before running.
Changing setup does not rewrite the currently loaded replay.

| ID | Length | Classification | Tightest arc |
|---|---:|---|---:|
| `amz_fssim_fsg_approx` | 306.450 m | Upstream simulator-map approximation | 3.664 m |
| `amz_fssim_fsi_approx` | 216.149 m | Upstream simulator-map approximation | 2.457 m |
| `technical_slalom_v1` | 303.298 m | Original synthetic FSAE-inspired test | 6.467 m |

FSG/FSI are upstream filenames, not verification of an official event, year,
survey accuracy or contemporary competition layout. These are not measured
team courses. The current bundle schema has only `synthetic`/`measured`; all
three conservatively use `synthetic`. The catalog separately identifies the
map-derived approximations and every bundle retains its processing provenance.
The tight FSI radius may exceed a particular vehicle/driver's steering envelope;
such failures must remain diagnostics rather than be hidden or used as rankings.

## Upstream data and reuse

AMZ Racing's [FSSIM repository](https://github.com/AMZ-Racing/fssim) is a Formula
Student Driverless simulator. Pinned commit:
`cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4`.

- [FSG.yaml](https://github.com/AMZ-Racing/fssim/blob/cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4/fssim_gazebo/models/track/tracks_yaml/FSG.yaml), Git blob `dcd1cd7509bcbd8b77189a2f142ce89290959a1d`.
- [FSI.yaml](https://github.com/AMZ-Racing/fssim/blob/cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4/fssim_gazebo/models/track/tracks_yaml/FSI.yaml), Git blob `8ae29a671564b439346541ccbf5521ab73701f3a`.
- [MIT notice](https://github.com/AMZ-Racing/fssim/blob/cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4/LICENSE.md), copyright 2019 Akademischer Motorsportverein Zürich.

Unmodified numeric point-list content and the MIT notice are retained under
`upstream/amz-fssim/`. Bundle provenance includes the local raw-file SHA-256;
catalog entries include normalized geometry identities. The repository's
license is unchanged. Source exports carry the original notice/data/catalog.

## Geometry method and limitations

`scripts/build_course_library.py` runs offline. It parses only the bounded numeric
left/right point-list subset of these pinned files, not executable YAML. Source
coordinates are interpreted as metric local Gazebo coordinates; no scaling is
applied. Ordered left samples are projected to nearest right-boundary segments,
then midpoint pairs approximate a centerline. Correspondence is not a survey.
Finite coordinates, separation, crossings and plausible pair gaps are checked.

Each centerline polygon vertex receives a tangent circular fillet; trim lengths
cannot overlap. Straight connectors and circular turns produce one analytic
closed loop. The existing bundle validator independently checks positions,
distance, curvature and seam heading. No plotted-only endpoint correction is
used. Cells are at most 0.5 m. The technical test uses original metric vertices
with repeated slaloms, varied-radius turns and braking approaches.

All corridors assume **3 m half-width**, 1.4 m vehicle width and .2 m margin.
Those assumptions do not retain or certify the upstream cone boundaries. Flat
planar geometry has no measured elevation, banking, surface or grip survey.
Driver/controller/plant limits remain independent of course validity. A valid
map is not proof that a selected vehicle completes it.

Rebuild/check from the repo root with the existing environment:

```text
python scripts/build_course_library.py
python scripts/build_course_library.py --check
```

Use the established resource guard for numerical validation. Never overwrite
prior acceptance attempts or call a time-limited trace a completed lap.

## Other public sources reviewed, not imported

The official [SAE 2026 handbook](https://www.fsaeonline.com/Page.aspx?pageid=b1e4f33c-84b1-41af-837b-87f89b275d4c)
links [autocross](https://www.fsaeonline.com/app/MapViewer.aspx?mapid=3e2267bf-1e50-4342-8edc-8414337c971e)
and [endurance](https://www.fsaeonline.com/app/MapViewer.aspx?mapid=76097adf-6d31-4ded-88d5-3f4979c2d5e1)
images. A reusable metric centerline and redistribution terms were not established;
no official graphic or invented digitization is included.

FSG's [2006 track-data announcement](https://www.formulastudent.de/pr/news/details/article/track-layout)
invites simulation reconstruction, but its linked archive currently requires
login. No authentication or access workaround was attempted.

The [StarkStrom FSD dataset](https://github.com/iv461/fsd_racetrack_dataset)
offers LiDAR-derived layouts, with manual boundary annotation and stated position
uncertainty, under LGPL-3.0. It is a future measured-source candidate, not part of
this bounded three-course slice or a claimed event survey.
