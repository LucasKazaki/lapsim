"""Small shipped course library; all payloads use the existing bundle validator."""
import json

from lapsim.resources import repository_root
from .course_bundle import CourseBundle

ONLINE_COURSE_IDS = ('fsae_michigan_2019_image','fsae_michigan_2022_image','fsae_michigan_2023_image','fsae_electric_2024_image','fs_east_2017_image')
CAMPAIGN_COURSE_IDS = (*ONLINE_COURSE_IDS,'fused_gnss_imu_trajectory_approx')
COURSE_IDS = ("amz_fssim_fsg_approx", "amz_fssim_fsi_approx", "technical_slalom_v1", *CAMPAIGN_COURSE_IDS)


def course_library():
    root = repository_root() / "configs/courses"
    raw = (root / "catalog.json").read_bytes()
    if len(raw) > 256_000:
        raise ValueError("Course catalog exceeds its byte bound")
    catalog = json.loads(raw)
    if catalog.get("schema") != "lapsim.course-library.v1" or [row.get("id") for row in catalog.get("courses", [])] != list(COURSE_IDS):
        raise ValueError("Unsupported course catalog")
    result = []
    for row in catalog["courses"]:
        # Catalog paths are display metadata, never a filesystem authority.
        if row.get('path') != 'configs/courses/'+row['id']+'.json':
            raise ValueError('Unsupported course catalog path')
        bundle = CourseBundle.load(root / (row["id"] + ".json"))
        if bundle.course_id != row["id"] or bundle.geometry_sha256 != row.get("geometry_sha256") or bundle.label != row.get("label"):
            raise ValueError("Course catalog/bundle identity mismatch")
        if row.get("classification") not in ("map_derived_approximation", "synthetic_fsae_inspired",'trajectory_derived_approximation'):
            raise ValueError("Unknown course evidence classification")
        result.append({**row, "bundle": bundle.to_dict()})
    return {"schema": catalog["schema"], "courses": result}
