"""Deterministic search bookkeeping; numerical parity has separate real tests."""
from dataclasses import asdict,replace
import math

import pytest
import importlib.util
from pathlib import Path

from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID
from lapsim.dynamics.planar import PlanarState
from lapsim.dynamics.powered_planar import PoweredState
from lapsim.experiments.gpu_search import matched_ranking,next_generation,freeze_finalists
from lapsim.experiments.search_policy import (SearchPolicy,STRUCTURES,REGEN_MODES,GENE_BOUNDS,
    initial_population,normalized_policy,offspring,active_genes,policy_digest)
from lapsim.experiments.tournament_rollout import fixture
from lapsim.experiments.tournament_rollout import allocate,Case
from lapsim.dynamics.planar import evaluate_planar_dynamics,PlanarControls


def test_stratified_seed_repeats_covers_structures_and_regen_without_inactive_genes():
    first=initial_population(20261026)
    assert first==initial_population(20261026)
    assert first!=initial_population(20261027)
    assert len({r['sha256'] for r in first})==18
    assert {(r['policy']['structure'],r['policy']['regen_mode']) for r in first}=={(s,r) for s in STRUCTURES for r in REGEN_MODES}
    for row in first:
        p=row['policy']
        if p['structure'] not in ('yaw','composed','adaptive'):assert p['yaw_kp']==p['yaw_ki']==0
        if p['regen_mode']!='two_stage':assert 'regen_region' not in row['active_genes']
        if p['regen_mode']=='off':assert 'regen_fraction' not in row['active_genes']


def test_inactive_mutations_normalize_to_identical_genome():
    genes={name:(lo+hi)/2 for name,(lo,hi) in GENE_BOUNDS.items()}
    first=normalized_policy('static','off',genes)
    genes.update(yaw_kp=44.,slip_target=.17,regen_fraction=.9,launch_speed_mps=9.)
    assert policy_digest(first)==policy_digest(normalized_policy('static','off',genes))


def test_recombination_immigrants_are_reproducible_distinct_and_within_constraints():
    parents=initial_population(408);seen=[r['sha256'] for r in parents]
    first=offspring(parents,409,seen)
    assert first==offspring(parents,409,seen)
    assert len(first)==6 and sum(c['origin']=='random immigrant' for c in first)==2
    assert len(set(seen+[r['sha256'] for r in first]))==24
    for row in first:
        policy=SearchPolicy(**row['policy'])
        for name,(lo,hi) in GENE_BOUNDS.items():assert lo<=getattr(policy,name)<=hi


def test_adaptive_modes_use_state_steering_and_soc_with_shared_primitives():
    car,pack,_=fixture();pack=replace(pack,topology_id=AWD_TOPOLOGY_ID)
    policy=SearchPolicy(structure='adaptive',regen_mode='two_stage',launch_speed_mps=6.,
        low_soc_threshold=.6,corner_threshold_rad=.1,drive_scale=.9)
    state=PoweredState(PlanarState(u_mps=5,wheel_speeds_rad_s=(25.,)*4),(0.,)*4,.7*pack.pack_capacity_j)
    effective,mode=policy.effective_policy(state,0.,car,pack)
    assert mode=='launch_slip' and effective.slip_control
    state=replace(state,plant=replace(state.plant,u_mps=8,wheel_speeds_rad_s=(40.,)*4))
    effective,mode=policy.effective_policy(state,.2,car,pack)
    assert mode=='corner_composed' and effective.yaw_control and effective.reserve_control
    effective,mode=policy.effective_policy(replace(state,pack_energy_j=.4*pack.pack_capacity_j),0.,car,pack)
    assert mode=='economy' and effective.drive_scale<policy.drive_scale
    effective,mode=policy.effective_policy(state,0.,car,pack)
    assert mode=='cruise' and not effective.slip_control


def test_observational_audit_never_changes_shared_allocator_outputs():
    car,pack,_=fixture();pack=replace(pack,topology_id=AWD_TOPOLOGY_ID)
    state=PoweredState(PlanarState(u_mps=8,wheel_speeds_rad_s=(45.,40.,42.,40.)),(0.,)*4,.7*pack.pack_capacity_j)
    physical=evaluate_planar_dynamics(car,state.plant,PlanarControls())
    for structure in STRUCTURES:
        policy=SearchPolicy(structure=structure,regen_mode='two_stage')
        effective,_=policy.effective_policy(state,.15,car,pack)
        args=(effective,state,physical,.15,90.,0.,0.,car,pack,Case('audit'))
        expected=allocate(*args);audit={};actual=allocate(*args,audit=audit)
        assert actual==expected
        assert all(type(v) is bool for v in audit.values())


def fake_records(ids,courses):
    # Deliberate algebra fixtures test scoring/selection, not car performance.
    result={}
    for i,identity in enumerate(ids):
        for course in courses:
            result[identity,'train',course]={'status':'completed','eligible':True,'violations':[],
                'distance_m':1000.,'geometry_sha256':course,'lap_time_s':100.+i,
                'net_energy_kwh':.1-.01*i,'recovered_kwh':.01*i}
    return result


def test_common_rescoring_is_order_independent_and_invalid_partial_never_wins():
    candidates=[{'id':'a'},{'id':'b'},{'id':'bad'}];courses=[f'c{i}' for i in range(6)]
    records=fake_records(['a','b','bad'],courses)
    records['bad','train','c0']['eligible']=False
    first=matched_ranking(candidates,records,courses,['train'])
    second=matched_ranking(list(reversed(candidates)),records,list(reversed(courses)),['train'])
    assert first['highest_points']==second['highest_points']==['b']
    assert first['fastest']==['a'] and first['least_net_energy']==['b']
    assert 'bad' in first['excluded']
    assert all(r['valid_laps']==6 for r in first['qualified'])
    assert first['official_points'] is False
    del records['b','train','c2']
    assert matched_ranking(candidates,records,courses,['train'])['highest_points']==['a']


def test_energy_is_not_credited_twice_and_zero_energy_is_excluded():
    candidates=[{'id':'a'},{'id':'b'}];courses=['c']
    records=fake_records(['a','b'],courses)
    before=matched_ranking(candidates,records,courses,['train'])
    records['a','train','c']['recovered_kwh']=100.
    after=matched_ranking(candidates,records,courses,['train'])
    assert before['highest_points']==after['highest_points']
    records['a','train','c']['net_energy_kwh']=0.
    assert 'a' in matched_ranking(candidates,records,courses,['train'])['excluded']


def test_prepare_is_self_contained_freezes_scenarios_and_rejects_overwrite(tmp_path):
    path=Path(__file__).resolve().parents[1]/'scripts/run_gpu_search.py'
    spec=importlib.util.spec_from_file_location('gpu_search_cli_for_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    destination=tmp_path/'search'
    module.prepare(destination,'NVIDIA GeForce RTX 5080')
    plan=module.load(destination/'plan.json');coverage=module.load(destination/'coverage.json')
    assert len(plan['initial_population'])==18 and len(plan['courses'])==6
    assert set(plan['scenarios'])=={'train','heldout-a','heldout-b'}
    assert coverage['counts']['training_saved']==6
    assert coverage['training']['provisional'] is True
    assert plan['budget']['maximum_new_gpu_laps']==204
    with pytest.raises(ValueError,match='preserved'):module.prepare(destination,'NVIDIA GeForce RTX 5080')
