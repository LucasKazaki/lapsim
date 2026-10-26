"""Frozen image-trace geometry, unit conversion and tournament wiring."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest
from lapsim.courses.course_bundle import CourseBundle
from lapsim.courses.library import ONLINE_COURSE_IDS,course_library
from lapsim.experiments.controller_tournament import specification
from lapsim.experiments.tournament_rollout import Case,Controller,rollout

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('identity',ONLINE_COURSE_IDS)
def test_five_distinct_valid_closed_metric_courses(identity):
    courses=course_library()['courses'];entry=next(r for r in courses if r['id']==identity)
    bundle=CourseBundle.from_dict(entry['bundle']);track=bundle.solver_track(.5)
    track.validate_coherent_arcs()
    assert track.geometry_audit().endpoint_separation_m<1e-6
    assert 600<track.length_m<2500
    assert track.cell_count<=5000
    assert min(track.curvature_per_m)<0<max(track.curvature_per_m)
    assert 'IMAGE-DERIVED APPROXIMATION' in entry['label']
    assert len({r['geometry_sha256'] for r in courses})==len(courses)
    assert entry['reference_image_sha256']==bundle.to_dict()['provenance']['source_sha256']
    assert entry['audit']['endpoint_correction_m']==0

@pytest.mark.parametrize('identity',ONLINE_COURSE_IDS)
def test_selection_reaches_same_plant_and_explicit_single_lap_horizon(identity):
    entry=next(r for r in course_library()['courses'] if r['id']==identity)
    spec=specification(population=4,generations=1,course='bundle',course_bundle=entry['bundle'],laps=1)
    case=Case(**spec['training'][0]);assert case.laps==1 and case.long_course and case.duration_s==300
    record=rollout(Controller(),Case('wiring',course='bundle',course_bundle=entry['bundle'],duration_s=.1,long_course=True),profile='synthetic_awd')
    assert record['course']['geometry_sha256']==entry['geometry_sha256']
    assert record['telemetry'][-1]['progress_m']>record['telemetry'][0]['progress_m']
    assert abs(record['metrics']['energy_residual_j'])<.5

def test_original_bounds_preserved_and_long_mode_not_silent():
    with pytest.raises(ValueError):Case('too-long',duration_s=61)
    with pytest.raises(ValueError):Case('not-bundle',long_course=True)
    entry=course_library()['courses'][-1]
    with pytest.raises(ValueError):Case('not-round',course='bundle',course_bundle=entry['bundle'],long_course=True,laps=10)
    bad=deepcopy(entry['bundle']);bad['geometry']['x_m'][4]+=1
    with pytest.raises(ValueError):Case('bad',course='bundle',course_bundle=bad)

def test_feet_and_preliminary_length_are_explicit():
    entries={r['id']:r for r in course_library()['courses']}
    assert entries['fsae_michigan_2023_image']['scale_m_per_pixel']==500*.3048/200
    assert entries['fs_east_2017_image']['length_m']==pytest.approx(700,abs=1e-7)

def test_existing_gnss_imu_trajectory_is_used_without_claiming_original_curvature():
    entry=next(r for r in course_library()['courses'] if r['id']=='fused_gnss_imu_trajectory_approx')
    bundle=CourseBundle.from_dict(entry['bundle']);bundle.track.validate_coherent_arcs()
    assert entry['classification']=='trajectory_derived_approximation'
    assert entry['source_rows']==1979 and entry['original_reported_length_m']==989
    assert 980<bundle.track.length_m<1030
    assert 'original complementary IMU curvature is not reused' in bundle.description
    assert bundle.track.geometry_audit().endpoint_separation_m<1e-6
