from dataclasses import replace
from math import inf,nan
import pytest
from lapsim.experiments.tournament_scoring import ScoringRun,score_field

def run(name='a',time=100.,energy=.1):
    return ScoringRun(name,'awd','geometry',1,1000.,time,energy,True,True)

def test_single_valid_simulated_finisher_gets_275_plus_100_with_explicit_adaptation():
    result=score_field([run()]);row=result['rows']['a']
    assert row['endurance_points']==pytest.approx(275)
    assert row['efficiency_points']==100 and row['total_points']==pytest.approx(375)
    assert not row['official_points'] and row['penalties_modeled'] is False

def test_efficiency_can_overcome_a_small_time_disadvantage():
    rows=score_field([run('fast',100,.2),run('efficient',100.1,.1)])['rows']
    assert rows['fast']['endurance_points']>rows['efficient']['endurance_points']
    assert rows['efficient']['total_points']>rows['fast']['total_points']

def test_references_can_be_different_competitors_and_match_factor_equation():
    result=score_field([run('fast',100,.2),run('efficient',110,.1)])
    refs=result['references'];rows=result['rows']
    assert refs['time_reference_candidate']=='fast' and refs['energy_reference_candidate']=='efficient'
    assert rows['fast']['efficiency_factor']==pytest.approx(.5)
    assert rows['efficient']['efficiency_factor']==pytest.approx(100/110)
    assert refs['fmin']==pytest.approx((1/1.45)*(.1/.308))

def test_cutoff_completion_credit_and_dnf_without_linear_partial_credit():
    rows=score_field([run(),run('at',145,.1),run('slow',146,.1),replace(run('dnf'),completed=False)])['rows']
    assert rows['at']['endurance_points']==pytest.approx(25)
    assert rows['slow']['endurance_points']==25 and rows['slow']['efficiency_points']==0
    assert rows['dnf']['total_points']==0

def test_penalty_time_is_corrected_time_and_explicit():
    rows=score_field([run(),replace(run('penalized'),penalty_s=2.)])['rows']
    assert rows['penalized']['corrected_time_s']==102
    assert rows['penalized']['endurance_points']<275
    assert rows['penalized']['penalties_modeled'] is False

@pytest.mark.parametrize('value',[0.,-1.,inf,nan,None])
def test_unreliable_net_energy_is_unavailable(value):
    row=score_field([replace(run(),net_energy_kwh=value)])['rows']['a']
    assert row['total_points'] is None and row['reasons']

def test_energy_cap_and_full_regen_credit_use_net_energy_once():
    rows=score_field([run('within',100,.308),run('over',100,.309)])['rows']
    assert rows['within']['efficiency_eligible']
    assert rows['over']['efficiency_points']==0 and not rows['over']['efficiency_eligible']

def test_unreliable_completed_reference_does_not_improve_other_competitors():
    result=score_field([run(),replace(run('bad'),net_energy_kwh=nan)])
    assert not result['available'] and result['rows']['a']['total_points'] is None

def test_equal_ten_lap_strata_preserve_ratios_and_remain_separate():
    one=[run('a',100,.2),run('b',100.1,.1)]
    ten=[replace(r,laps=10,distance_m=r.distance_m*10,time_s=r.time_s*10,net_energy_kwh=r.net_energy_kwh*10) for r in one]
    before=score_field(one)['rows'];after=score_field(ten)['rows']
    for name in before:
        assert before[name]['total_points']==pytest.approx(after[name]['total_points'])

@pytest.mark.parametrize('changes',[{'time_s':0.},{'time_s':nan},{'distance_m':0.},{'distance_m':inf},{'penalty_s':-2.},{'laps':0},{'net_energy_kwh':1e308},{'time_s':1.5e308}])
def test_bad_units_bounds_and_nonfinite_intermediates_are_unavailable(changes):
    result=score_field([replace(run(),**changes)])
    assert not result['available'] and result['rows']['a']['total_points'] is None

def test_subnormal_cap_and_per_lap_divisors_are_unavailable():
    for value in [replace(run(),distance_m=1e-320,net_energy_kwh=5e-324),
                  replace(run(),laps=10,net_energy_kwh=5e-324),
                  replace(run(),time_s=5e-324)]:
        result=score_field([value])
        assert not result['available'] and result['rows']['a']['total_points'] is None

@pytest.mark.parametrize('changes',[{'hardware':'rwd'},{'geometry_sha256':'other'},{'laps':10}])
def test_never_mix_hardware_geometry_or_lap_count(changes):
    with pytest.raises(ValueError):score_field([run(),replace(run('b'),**changes)])
