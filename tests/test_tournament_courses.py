"""Course-selection contracts: coherent geometry, portable identity and isolation."""
from dataclasses import asdict, replace
from math import pi

import pytest

from lapsim.experiments.controller_tournament import specification
from lapsim.experiments.tournament_rollout import Case, Controller, course_for, rollout
from lapsim.courses.course_bundle import CourseBundle
from test_course_bundle import _manifest


def test_autocross_has_both_turn_directions_and_exact_closed_arcs():
    track = course_for(Case('autocross', course='autocross'))
    track.validate_coherent_arcs()
    assert 150 < track.length_m < 500
    assert min(track.curvature_per_m) < 0 < max(track.curvature_per_m)
    assert track.geometry_audit().endpoint_separation_m < 1e-8
    assert sum(k * d for k, d in zip(track.curvature_per_m, track.cell_length_m)) == pytest.approx(2*pi)


def test_autocross_centerline_has_no_crossings_or_retraced_segments():
    track = course_for(Case('autocross', course='autocross'))
    points = list(zip(track.x_m, track.y_m))
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i, (a, b) in enumerate(zip(points, points[1:])):
        for j in range(i+2, len(points)-1):
            if i == 0 and j == len(points)-2:
                continue
            c, d = points[j:j+2]
            if (max(a[0],b[0])+1e-8 < min(c[0],d[0]) or max(c[0],d[0])+1e-8 < min(a[0],b[0]) or
                max(a[1],b[1])+1e-8 < min(c[1],d[1]) or max(c[1],d[1])+1e-8 < min(a[1],b[1])):
                continue
            assert not (cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0), (i,j)


def test_reverse_and_mirror_preserve_length_and_transform_curvature():
    case = Case('course', course='autocross')
    track = course_for(case)
    reverse = course_for(replace(case, reverse=True))
    mirror = course_for(replace(case, mirror=True))
    reverse.validate_coherent_arcs()
    mirror.validate_coherent_arcs()
    assert reverse.length_m == mirror.length_m == track.length_m
    assert reverse.curvature_per_m == tuple(-v for v in reversed(track.curvature_per_m))
    assert mirror.y_m == tuple(-v for v in track.y_m)


def test_course_is_bound_into_search_and_checkpoint_inputs():
    spec = specification(population=4, generations=1, course='autocross')
    assert all(c['course'] == 'autocross' for c in spec['training'] + spec['holdout'])
    assert any(c['reverse'] for c in spec['holdout'])
    assert spec['resources']['maximum_simulated_run_s'] == 600
    assert all(c['laps']==10 for c in spec['training']+spec['holdout'])
    assert spec['scenario_inputs']['battery_capacity_kwh'] == 5.5
    assert spec['scenario_inputs']['endurance_energy_weights'] == [275, 100]


def test_selected_course_reaches_rollout_and_does_not_change_legacy_default():
    original = course_for(Case('legacy'))
    case = Case('short', course='autocross', duration_s=.05)
    record = rollout(Controller(), case, profile='synthetic_awd')
    assert record['case'] == asdict(case)
    assert record['course']['length_m'] != original.length_m
    assert record['course']['geometry_sha256']
    assert not record['eligible'] and record['metrics']['fitness'] is None


def test_bad_course_and_nonboolean_transform_fail_before_simulation():
    with pytest.raises(ValueError):
        Case('bad', course='not_a_course')
    with pytest.raises(ValueError):
        Case('bad', reverse=1)


def test_imported_geometry_and_corridor_are_used_and_tampering_rejects():
    manifest = _manifest()
    bundle = CourseBundle.from_dict(manifest)
    case = Case('import', course='bundle', course_bundle=manifest, duration_s=.05)
    result = rollout(Controller(), case, profile='synthetic_awd')
    assert result['course']['geometry_sha256'] == bundle.geometry_sha256
    assert result['driver']['assumed_half_width_m'] == manifest['ai_defaults']['half_width_m']
    assert result['driver']['vehicle_width_m'] == manifest['ai_defaults']['vehicle_width_m']
    assert result['case']['course_bundle'] == manifest
    manifest['geometry']['x_m'][5] += 1
    with pytest.raises(ValueError):
        Case('tamper', course='bundle', course_bundle=manifest)


def test_sweep_propagates_course_and_transforms(tmp_path):
    from lapsim.experiments.tournament_sweep import run_sweep
    cases = []
    def short(controller, case, **kwargs):
        cases.append(case)
        return rollout(controller, replace(case, duration_s=.01), **kwargs)
    config = {'course': 'autocross', 'reverse': True, 'mirror': True,
              'axes': [{'parameter': 'drive_scale', 'minimum': .7, 'maximum': 1, 'count': 2}]}
    result = run_sweep(config, tmp_path/'sweep', rollout_fn=short)
    assert len(cases) == 2 and result['status'] == 'completed'
    assert all(c.course == 'autocross' and c.reverse and c.mirror for c in cases)


def test_search_executes_the_embedded_cases_and_refuses_a_changed_course(tmp_path):
    from lapsim.experiments.controller_tournament import run_search
    from test_controller_tournament import fake_rollout
    seen = []
    def record(controller, case, **kwargs):
        seen.append(case)
        return fake_rollout(controller, case, **kwargs)
    spec = specification(population=4, generations=1, course='autocross')
    state = run_search(tmp_path/'search', spec, rollout_fn=record)
    assert state['status'] == 'completed'
    assert all(c.course == 'autocross' and c.duration_s == 600 and c.laps==10 for c in seen)
    assert any(c.reverse for c in seen)
    changed = specification(population=4, generations=1, course='autocross', mirror=True)
    with pytest.raises(ValueError, match='config/source mismatch'):
        run_search(tmp_path/'search', changed, resume=True, rollout_fn=record)
