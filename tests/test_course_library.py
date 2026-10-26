"""E17-R9 geometry/source/selection acceptance; synthetic/map approximations."""
import importlib.util
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from lapsim.courses.course_bundle import CourseBundle
from lapsim.courses.library import course_library
from lapsim.experiments.controller_tournament import specification
from lapsim.experiments.tournament_rollout import Case, Controller, course_for, rollout
from lapsim.dynamics.actuation import SINGLE_MOTOR_RWD_TOPOLOGY_ID, AWD_TOPOLOGY_ID
from lapsim.torque_configurator import example_profile
from lapsim.torque_configurator.comparison import compare
from lapsim.torque_configurator.session import replay

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_course_library',ROOT/'scripts/build_course_library.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_pinned_upstream_layouts_convert_with_bounded_correspondence_and_exact_closure():
    schema,courses=builder.build()
    assert schema=='lapsim.course-library.v1' and len(courses)==3
    for bundle,metadata in courses:
        bundle.track.validate_coherent_arcs()
        assert bundle.track.geometry_audit().endpoint_separation_m<1e-6
        assert 200<bundle.track.length_m<1000
        assert min(bundle.track.curvature_per_m)<0<max(bundle.track.curvature_per_m)
        assert metadata['audit']['endpoint_correction_m']==0
        assert metadata['classification'] in ('map_derived_approximation','synthetic_fsae_inspired')
        if metadata['classification']=='map_derived_approximation':
            assert 1<=metadata['audit']['boundary_pair_gap_min_m']<=metadata['audit']['boundary_pair_gap_max_m']<=8
            assert metadata['license']=='MIT (AMZ FSSIM)'


@pytest.mark.parametrize('index',[0,1,2])
def test_catalog_selection_reaches_actual_tournament_rollout_and_preserves_evidence(index):
    entry=course_library()['courses'][index]
    case=Case('library-acceptance',course='bundle',course_bundle=entry['bundle'],duration_s=.1)
    result=rollout(Controller(),case,profile='synthetic_awd')
    assert result['course']['label']==entry['label']
    assert result['course']['geometry_sha256']==entry['geometry_sha256']
    assert result['case']['course_bundle']==entry['bundle']
    assert result['course']['input_evidence']['provenance']==entry['bundle']['provenance']
    assert result['telemetry'][-1]['progress_m']>result['telemetry'][0]['progress_m']
    assert abs(result['metrics']['energy_residual_j'])<.5
    assert not result['eligible'] and result['metrics']['fitness'] is None


@pytest.mark.parametrize('index',[0,1,2])
def test_library_configured_profiles_use_same_core_and_reject_tampered_geometry(index):
    entry=course_library()['courses'][index]
    profiles=[example_profile(SINGLE_MOTOR_RWD_TOPOLOGY_ID),example_profile(AWD_TOPOLOGY_ID)]
    study=compare(profiles,duration_ms=100,course='bundle',course_bundle=entry['bundle'])
    for record,profile in zip(study['runs'].values(),profiles):
        assert record['course']['geometry_sha256']==entry['geometry_sha256']
        assert record['configuration']['outputs']==replay(profile,record['configuration']['frames'])
        assert record['metrics']['fitness'] is None
    bad=deepcopy(entry['bundle']);bad['geometry']['x_m'][4]+=1
    with pytest.raises(ValueError):Case('tampered',course='bundle',course_bundle=bad)


@pytest.mark.parametrize('index',[0,1,2])
def test_shipped_course_reverse_mirror_and_search_inputs_are_coherent(index):
    entry=course_library()['courses'][index]
    case=Case('transform',course='bundle',course_bundle=entry['bundle'])
    original=course_for(case)
    for changed in (replace(case,reverse=True),replace(case,mirror=True)):
        track=course_for(changed);track.validate_coherent_arcs()
        assert track.length_m==original.length_m
    spec=specification(population=4,generations=1,course='bundle',course_bundle=entry['bundle'])
    assert all(c['course_bundle']==entry['bundle'] for c in spec['training']+spec['holdout'])


@pytest.mark.parametrize('change',[
    lambda p:p.__setitem__(0,(float('nan'),0)),
    lambda p:p.__setitem__(0,(True,0)),
    lambda p:p.__setitem__(1,p[0]),
    lambda p:p.__setitem__(0,(10001,0)),
])
def test_malformed_source_points_reject_instead_of_becoming_a_course(change):
    points=[(0,0),(10,0),(20,5),(20,15),(10,20),(0,20),(-10,15),(-10,5)]
    change(points)
    with pytest.raises(ValueError):builder.rounded_polygon(points)


def test_crossing_course_rejects_before_arc_generation():
    points=[(0,0),(20,20),(25,20),(25,0),(20,0),(0,20),(-5,20),(-5,0)]
    with pytest.raises(ValueError,match='crossing'):builder.rounded_polygon(points)


def test_bundle_rejects_wrong_units_and_catalog_cannot_choose_filesystem_paths(tmp_path,monkeypatch):
    entry=course_library()['courses'][0]
    bad=deepcopy(entry['bundle']);bad['coordinate_frame']['units']='ft'
    with pytest.raises(ValueError,match='meters'):CourseBundle.from_dict(bad)
    shutil.copytree(ROOT/'configs/courses',tmp_path/'configs/courses')
    path=tmp_path/'configs/courses/catalog.json'
    catalog=json.loads(path.read_text(encoding='utf-8'));catalog['courses'][0]['path']='../../secret.json'
    path.write_text(json.dumps(catalog),encoding='utf-8')
    import lapsim.courses.library as library
    monkeypatch.setattr(library,'repository_root',lambda:tmp_path)
    with pytest.raises(ValueError,match='path'):library.course_library()


def test_catalog_http_boundary_returns_validated_library_without_starting_jobs():
    from lapsim.experiments.tournament_server import Handler
    handler=object.__new__(Handler);handler.path='/api/course/catalog';seen=[]
    handler.json_response=lambda value,*args:seen.append(value)
    handler.do_GET()
    assert len(seen)==1 and len(seen[0]['courses'])==3


def test_configurator_api_forwards_selected_bundle(monkeypatch,tmp_path):
    import lapsim.torque_configurator.api as api
    import lapsim.torque_configurator.comparison as comparison
    seen=[]
    monkeypatch.setattr(comparison,'compare',lambda profiles,**kw:seen.append(kw) or {'runs':{},'fingerprint':'recorded'})
    monkeypatch.setattr(comparison,'save_comparison',lambda *args:None)
    monkeypatch.setattr(api,'repository_root',lambda:tmp_path)
    entry=course_library()['courses'][0]
    api.action('compare',{'profile':example_profile(SINGLE_MOTOR_RWD_TOPOLOGY_ID).to_dict(),
        'reference_architecture':AWD_TOPOLOGY_ID,'course':'bundle','course_bundle':entry['bundle']})
    assert seen[0]['course']=='bundle' and seen[0]['course_bundle']==entry['bundle']


def test_export_carries_upstream_data_license_and_catalog(tmp_path):
    from lapsim.torque_configurator.export import export_source
    target=tmp_path/'source'
    export_source(example_profile(),target,100)
    assert (target/'configs/courses/upstream/amz-fssim/LICENSE.md').read_bytes()==(ROOT/'configs/courses/upstream/amz-fssim/LICENSE.md').read_bytes()
    assert (target/'configs/courses/catalog.json').exists()


def test_source_notice_and_ui_both_load_shared_course_picker():
    license=(ROOT/'configs/courses/upstream/amz-fssim/LICENSE.md').read_text(encoding='utf-8')
    assert 'Akademischer Motorsportverein' in license and 'MIT License' in license
    for name in ('tournament.html','torque-configurator.html'):
        page=(ROOT/'web'/name).read_text(encoding='utf-8')
        assert 'course_library.js' in page and 'id="course-preview"' in page
