"""Structural policies share one session and preserve hard validity/units."""
from copy import deepcopy
import pytest

from lapsim.torque_configurator.policy import PolicySpec,experimental_profile
from lapsim.torque_configurator import VehicleProfile
from lapsim.torque_configurator.adapter import validate


def test_topology_and_inactive_parameter_identity_are_explicit():
    profile=experimental_profile('synthetic_single_motor_locked_axle_rwd_v1')
    spec=deepcopy(profile.to_dict()['controller']);spec['structure']['yaw']='pi'
    value=profile.to_dict();value['controller']=spec
    with pytest.raises(ValueError,match='yaw'):VehicleProfile.from_dict(value)
    first=PolicySpec.from_dict(profile.to_dict()['controller'],profile.actuation.topology_id)
    spec=deepcopy(profile.to_dict()['controller']);spec['parameters']['yaw_kp']=44.
    other=PolicySpec.from_dict(spec,profile.actuation.topology_id)
    assert first.effective_identity==other.effective_identity


def test_experimental_plant_and_standalone_use_identical_signed_core():
    profile=experimental_profile('synthetic_independent_four_awd_v1')
    report=validate(profile,1000)
    assert report['equivalent'] and report['repeat_exact']
    outputs=report['integration']['outputs']
    assert any(min(row['limited']['wheel_torques_nm'])<0 for row in outputs)
    assert any(row['controller']['mode'] for row in outputs)
    assert abs(report['energy_residual_j'])<.5


def test_structures_change_effective_identity_and_reject_unbounded_values():
    profile=experimental_profile('synthetic_independent_four_awd_v1')
    first=PolicySpec.from_dict(profile.to_dict()['controller'],profile.actuation.topology_id)
    spec=deepcopy(profile.to_dict()['controller']);spec['structure']['pedal']='proportional'
    assert PolicySpec.from_dict(spec,profile.actuation.topology_id).effective_identity!=first.effective_identity
    spec['parameters']['slip_target']=float('nan')
    with pytest.raises(ValueError):PolicySpec.from_dict(spec,profile.actuation.topology_id)


def test_demanding_shared_discharge_and_regen_caps_are_active_and_conserved():
    profile=experimental_profile('synthetic_independent_four_awd_v1')
    value=profile.to_dict();value['policy']['initial_speed_mps']=15.
    value['actuation'].update(pack_discharge_power_limit_w=1500.,pack_charge_power_limit_w=600.)
    low=validate(VehicleProfile.from_dict(value),1000)
    value['actuation'].update(pack_discharge_power_limit_w=25000.,pack_charge_power_limit_w=8000.)
    high=validate(VehicleProfile.from_dict(value),1000)
    a,b=low['integration'],high['integration']
    assert max(row['limited']['pack_power_w'] for row in a['outputs'])<=1500.+1e-6
    assert min(row['limited']['pack_power_w'] for row in a['outputs'])>=-600.-1e-6
    assert max(row['limited']['pack_power_w'] for row in b['outputs'])>2000.
    assert max(row['achieved_pack_power_w'] for row in a['plant'])<=1500.+1e-6
    assert a['plant'][60]['u_mps']<b['plant'][60]['u_mps']
    assert any(sum(row['friction_nm'])>0 for row in a['outputs'])
    assert low['equivalent'] and high['equivalent'] and abs(low['energy_residual_j'])<.5


def test_optional_numeric_policy_telemetry_has_python_javascript_csv_parity(tmp_path):
    import csv,io,json,shutil,subprocess
    from pathlib import Path
    from lapsim.experiments.tournament_rollout import Controller,Case,rollout,CONFIGURED_REFERENCE
    from lapsim.experiments.tournament_sweep import export_timeseries
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    p=experimental_profile('synthetic_independent_four_awd_v1')
    record=rollout(Controller(CONFIGURED_REFERENCE),Case('csv',duration_s=.12),profile='synthetic_awd',configured_profile=p)
    target=tmp_path/'values.csv';export_timeseries(record,target)
    script='const fs=require("node:fs"),api=require(process.argv[1]);process.stdout.write(api.timeseriesCsv(JSON.parse(fs.readFileSync(0,"utf8"))));'
    result=subprocess.run([node,'-e',script,str(Path(__file__).resolve().parents[1]/'web/telemetry.js')],input=json.dumps(record),capture_output=True,text=True,timeout=10,check=True)
    a=list(csv.DictReader(io.StringIO(target.read_text())));b=list(csv.DictReader(io.StringIO(result.stdout)))
    assert len(a[0])==44 and a[0].keys()==b[0].keys()
    assert [{k:float(v) for k,v in row.items()} for row in a]==[{k:float(v) for k,v in row.items()} for row in b]


def test_soc_condition_reduces_drive_when_active_and_can_correctly_be_inactive():
    from lapsim.torque_configurator.session import replay
    base=experimental_profile('synthetic_independent_four_awd_v1').to_dict()
    base['controller']['structure'].update(condition='energy_save',yaw='off',traction='off',reserve='off')
    base['controller']['parameters']['coast_fraction']=.5
    def run(threshold):
        value=deepcopy(base);value['controller']['parameters']['soc_threshold']=threshold
        profile=VehicleProfile.from_dict(value)
        frames=[{'now_ms':now,'timestamp_ms':now,'accelerator_fraction':.8 if now>=20 else 0.,'brake_fraction':0.,
            'steering_rad':0.,'wheel_speeds_rad_s':[25.]*4,'pack_energy_j':profile.actuation.pack_capacity_j*.7,
            'valid':True,'enabled':True,'restart_requested':False,'wheel_available':[True]*4,
            'u_mps':5.,'v_mps':0.,'yaw_rate_rad_s':0.,'actuator_memory_nm':[0.]*4,
            'regen_available':True,'motor_temperature_c':40.,'friction_fallback':True} for now in range(0,50,10)]
        return replay(profile,frames)
    inactive=run(.5);also_inactive=run(.6);active=run(.8)
    assert [p['limited'] for p in inactive]==[p['limited'] for p in also_inactive]
    assert inactive[-1]['controller']['mode']=='drive'
    assert active[-1]['controller']['mode']=='energy_save'
    assert sum(active[-1]['controller']['command_nm'])==pytest.approx(.5*sum(inactive[-1]['controller']['command_nm']))
