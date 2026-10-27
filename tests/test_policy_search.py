from lapsim.torque_configurator.policy import experimental_profile,PolicySpec
from lapsim.torque_configurator.policy_search import sample_profiles,hardware_identity,pareto,diverse_elites


def test_sampling_spans_structures_full_ranges_and_only_active_genes():
    base=experimental_profile('synthetic_single_motor_locked_axle_rwd_v1')
    first=sample_profiles(base,4082601,12);second=sample_profiles(base,4082601,12)
    assert [p.sha256 for p in first]==[p.sha256 for p in second]
    assert all(hardware_identity(p)==hardware_identity(base) for p in first)
    specs=[PolicySpec.from_dict(p.to_dict()['controller'],p.actuation.topology_id) for p in first]
    assert len({s.effective_identity for s in specs})==12
    assert len({s.to_dict()['structure']['traction'] for s in specs})==3
    assert all(s.to_dict()['structure']['yaw']=='off' for s in specs)
    assert min(s.to_dict()['parameters']['drive_scale'] for s in specs)<.65
    assert max(s.to_dict()['parameters']['drive_scale'] for s in specs)>.95


def test_pareto_keeps_speed_energy_extremes_and_never_promotes_failed_or_slow_endpoint():
    def point(name,t,e,*,accepted=True,speed=5.,behavior=None):
        return dict(id=name,time_s=t,net_energy_kwh=e,accepted=accepted,completed_laps=10,final_speed_mps=speed,behavior_sha256=behavior or name)
    points=[point('fast',100,.2),point('efficient',110,.1),point('dominated',120,.3),
            point('failed',1,-10,accepted=False),point('coasted_endpoint',105,.01,speed=2.)]
    result=pareto(points,5.)
    assert set(result['frontier_ids'])=={'fast','efficient'}
    assert result['exemplars']['fastest']=='fast' and result['exemplars']['lowest_energy']=='efficient'
    assert len(result['excluded'])==2
    assert set(diverse_elites(points,result))=={'fast','efficient'}
