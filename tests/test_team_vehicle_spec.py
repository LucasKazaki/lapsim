"""Provisional team facts stay distinct from explicit synthetic probes."""
import math
import json
import pytest
from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID, constrain_actuation
from lapsim.torque_configurator.profile import example_profile, VehicleProfile, PROFILE_FILES
from lapsim.torque_configurator.team_spec import load_team_spec, ratio_probe, actuation_diagnostics

def test_team_update_retains_unknowns_and_motor_to_wheel_convention():
    spec = load_team_spec()
    assert spec.gear_ratio == 12.48
    assert spec.to_dict()['season'] == '2027-2028'
    assert spec.to_dict()['source']['reported_at_utc'] == '2026-10-27T04:19:00Z'
    assert spec.to_dict()['drivetrain']['gear_ratio_unit'] == 'motor_revolutions_per_driven_wheel_revolution'
    assert all((spec.to_dict()['drivetrain'][key] is None for key in spec.unknown_fields))
    assert not spec.simulation_ready
    with pytest.raises(ValueError):
        VehicleProfile.from_dict(spec.to_dict())

@pytest.mark.parametrize('value', [True, False, 0, -1, float('nan'), float('inf'), '12.48'])
def test_invalid_ratio_is_rejected_without_coercion(value):
    spec = load_team_spec()
    payload = spec.to_dict()
    payload['drivetrain']['gear_ratio'] = value
    with pytest.raises(ValueError):
        type(spec).from_dict(payload)

def test_inverse_convention_and_unknown_fields_are_rejected():
    spec = load_team_spec()
    payload = spec.to_dict()
    payload['drivetrain']['gear_ratio_unit'] = 'wheel_revolutions_per_motor_revolution'
    with pytest.raises(ValueError):
        type(spec).from_dict(payload)
    payload = spec.to_dict()
    payload['drivetrain']['calibrated'] = True
    with pytest.raises(ValueError):
        type(spec).from_dict(payload)

def test_duplicate_fields_are_rejected_before_profile_creation(tmp_path):
    text = json.dumps(load_team_spec().to_dict())
    text = text.replace('"gear_ratio": 12.48', '"gear_ratio": 12.48, "gear_ratio": 4.0')
    path = tmp_path / 'duplicate.json'
    path.write_text(text)
    with pytest.raises(ValueError, match='Duplicate'):
        load_team_spec(path)


def test_unknown_team_fields_cannot_be_filled_from_donor_defaults():
    team = load_team_spec()
    donor = example_profile(AWD_TOPOLOGY_ID)
    for field in team.unknown_fields:
        payload = team.to_dict()
        payload['drivetrain'][field] = donor.to_dict()['actuation'].get(field, 20.0)
        with pytest.raises(ValueError, match='unknown fields as null'):
            type(team).from_dict(payload)

def test_probe_requires_explicit_assumptions_and_preserves_historical_profile():
    base = example_profile(AWD_TOPOLOGY_ID)
    before = base.sha256
    with pytest.raises(ValueError, match='synthetic assumptions'):
        ratio_probe(load_team_spec(), base)
    probe, manifest = ratio_probe(load_team_spec(), base, accept_synthetic_assumptions=True)
    repeated, repeated_manifest = ratio_probe(
        load_team_spec(), base, accept_synthetic_assumptions=True
    )
    assert repeated.sha256 == probe.sha256 and repeated_manifest == manifest
    assert base.sha256 == before and base.actuation.gear_ratio == 4.0
    assert probe.actuation.gear_ratio == 12.48 and probe.sha256 != before
    assert probe.to_dict()['evidence_status'] == 'synthetic_unvalidated'
    assert manifest['assumed_values']['gear_efficiency'] == base.actuation.gear_efficiency
    assert manifest['assumed_values']['topology_id'] == base.actuation.topology_id
    assert manifest['team_claims']['gear_efficiency'] is None
    assert manifest['controller_optimality_for_new_ratio'] == 'not_established'

def evaluated(profile, command, speed):
    return constrain_actuation(profile.actuation, (command,) * 4, (speed,) * 4, 0.7 * profile.actuation.pack_capacity_j, 0.01, (True,) * 4)

def test_ratio_plumbing_changes_motor_speed_and_current_without_forcing_wheel_differences():
    base = example_profile(AWD_TOPOLOGY_ID)
    probe, _ = ratio_probe(load_team_spec(), base, accept_synthetic_assumptions=True)
    for command in (50.0, -50.0):
        a = evaluated(base, command, 10.0)
        b = evaluated(probe, command, 10.0)
        assert a.wheel_torques_nm == b.wheel_torques_nm == (command,) * 4
        assert b.motor_speeds_rad_s[0] / a.motor_speeds_rad_s[0] == pytest.approx(3.12)
        assert b.motor_torques_nm[0] / a.motor_torques_nm[0] == pytest.approx(1 / 3.12)
        assert abs(b.motor_currents_a[0]) < abs(a.motor_currents_a[0])
        assert math.isfinite(a.pack_power_w) and math.isfinite(b.pack_power_w)

def test_synthetic_limit_probes_show_ratio_sensitivity_not_real_top_speed():
    base = example_profile(AWD_TOPOLOGY_ID)
    probe, _ = ratio_probe(load_team_spec(), base, accept_synthetic_assumptions=True)
    a = evaluated(base, 10000.0, 0.0)
    b = evaluated(probe, 10000.0, 0.0)
    assert b.wheel_torques_nm[0] / a.wheel_torques_nm[0] == pytest.approx(3.12)
    assert evaluated(base, 50.0, 60.0).wheel_torques_nm[0] > 0
    assert evaluated(probe, 50.0, 60.0).wheel_torques_nm == (0.0,) * 4
    assert load_team_spec().to_dict()['drivetrain']['vehicle_top_speed_mps'] is None
    diagnostics = actuation_diagnostics(base, probe)
    assert len(diagnostics['rows']) == 4 and diagnostics['simulation_only'] is True
    assert diagnostics['rows'][0]['ratio_probe']['motor_speeds_rad_s'] == (124.80000000000001,) * 4


@pytest.mark.parametrize('architecture', list(PROFILE_FILES))
def test_ratio_diagnostic_preserves_supported_topology_front_drive(architecture):
    base = example_profile(architecture)
    probe, _ = ratio_probe(load_team_spec(), base, accept_synthetic_assumptions=True)
    diagnostics = actuation_diagnostics(base, probe)
    expected_front = (50.0, 50.0) if architecture == AWD_TOPOLOGY_ID else (0.0, 0.0)
    for profile in ('baseline', 'ratio_probe'):
        actual = diagnostics['rows'][0][profile]['wheel_torques_nm']
        assert len(actual) == 4 and actual[:2] == expected_front
