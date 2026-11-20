"""Read/check the public synthetic bundle, not a simulator or owner launcher."""
from dataclasses import asdict, replace
from hashlib import sha256
import json
from math import pi, isclose
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
FAMILIES = ('manual', 'drag96', 'drag91')


def require(ok, why):
    if not ok: raise ValueError(why)


def digest(data): return sha256(data).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def go(family):
    require(family in FAMILIES, 'expected manual, drag96, or drag91')
    root = ROOT/family
    index = json.loads((ROOT/'PUBLIC_FILE_MANIFEST.json').read_bytes())
    pins = {row['path']: row for row in index['files']}
    for name,row in pins.items():
        path = ROOT/name
        path.resolve().relative_to(ROOT.resolve())
        raw = path.read_bytes()
        require(len(raw)==row['bytes'] and digest(raw)==row['sha256'], 'export file differs: '+name)
    inputs = {p.stem:p.read_bytes() for p in (root/'data').glob('*.json')}
    require(set(inputs)=={'profile','retained_fixture','course','historical_case_data','cones'}, 'exact synthetic data set required')
    sys.path.insert(0,str(root/'src'))
    if family=='manual':
        from lapsim.learning.live.demo_initialization import construct, PINS
    else:
        from lapsim.learning.live.initialization import construct, PINS
    require(all((len(raw),digest(raw))==tuple(PINS[k]) for k,raw in inputs.items()), 'source synthetic input pins differ')
    plant=construct(inputs)
    state=plant.state;powered=state.thermal.light.powered;body=powered.plant
    require(state.thermal.light.feedback_ticks==state.thermal.thermal.ticks==state.drs.ticks==powered.integration_trials==powered.integration_substeps==0,
            'zero-step static validation only')
    require((body.u_mps,body.v_mps,body.yaw_rate_rad_s,*body.wheel_speeds_rad_s)==(0.,)*7 and powered.pack_energy_j==9_000_000.,'starting state differs')
    require(plant.actuation.gear_efficiency==(.91 if family=='drag91' else .96),'wrong arm')
    if family=='manual':
        from demo_plant import map_and_start
        geometry,initial=map_and_start(inputs)
        require(initial['speed_mps']==initial['sim_s']==0 and geometry['cones'] and geometry['centerline'],'synthetic geometry/readback differs')
        import test_keyboard_view
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_keyboard_view)
        result=unittest.TextTestRunner(verbosity=1).run(suite)
        require(result.wasSuccessful(),'keyboard routing/control scheduling tests failed')
        tests=result.testsRun
    else:
        from ev_parent.drag_case import CASE,REQUEST
        from lapsim.learning.live.drag_probe import drag_command,STAGING,nose_coordinate
        from lapsim.learning.live.drag_verify import STAGING as VERIFY_STAGING
        require(CASE=='driver_full_pedal' and tuple(drag_command(plant.actuation,plant.profile['policy'],throttle_case=CASE))==(0.,0.,500.,500.),'fixed demand differs')
        require(STAGING==VERIFY_STAGING==REQUEST['staging'] and isclose(nose_coordinate(body,body),-.3,abs_tol=1e-14) and REQUEST['maximum_ticks']==8000,'public drag timing binding differs')
        require(digest(inputs['profile'])==REQUEST['physics_profile_sha256'],'drag profile pin differs')
        tests=0
    from lapsim_light_core.actuation import constrain_actuation
    conf=plant.actuation
    # The common public parameter check, not a second driving run.
    omega=3200*2*pi/60/conf.gear_ratio;energy=9_000_000.;speeds=(omega,)*4
    low=constrain_actuation(conf,(0.,0.,150.,150.),speeds,energy,.001)
    high=constrain_actuation(conf,(0.,0.,500.,500.),speeds,energy,.001)
    require(low.wheel_torques_nm==(0.,0.,150.,150.) and low.pack_power_w<80_000.,'unsaturated comparison differs')
    require('shared_pack_power_current_interval_energy' in high.constraints and isclose(high.pack_power_w,80_000.,abs_tol=1e-7),'expected pack cap differs')
    expected={'manual':(33155.17881864665,715.976980661589),'drag96':(33155.17881864665,715.976980661589),
              'drag91':(34992.16903206109,678.6865129187979)}[family]
    require(isclose(low.pack_power_w,expected[0],rel_tol=1e-13) and isclose(sum(high.wheel_torques_nm),expected[1],rel_tol=1e-13),'public fixed point differs from accepted numerical fixture')
    # Check sources actually imported from the selected relative export, not an installed package.
    imports=[]
    for name,module in list(sys.modules.items()):
        if name.startswith(('lapsim','ev_parent','utils')) or name in ('demo_plant','keyboard_view','test_keyboard_view'):
            p=Path(module.__file__).resolve();relative=p.relative_to(ROOT.resolve()).as_posix()
            require(relative in pins and digest(p.read_bytes())==pins[relative]['sha256'],'unbound import: '+name)
            imports.append(name)
    print(json.dumps(dict(family=family,zero_physics_ticks=True,native_launches=0,keyboard_tests=tests,source_imports=len(imports),
        gear_efficiency=conf.gear_efficiency,initial_model_sha256=state.model_sha256,powered_initial_sha256=digest(canonical(asdict(powered))),
        low_pack_W=low.pack_power_w,high_total_wheel_torque_nm=sum(high.wheel_torques_nm),high_pack_W=high.pack_power_w),sort_keys=True))


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('python -I -S -B validate_public.py manual|drag96|drag91')
    go(sys.argv[1])
