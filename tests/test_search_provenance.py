"""Counterexamples for historical anchors and source-drift partial results."""
from hashlib import sha256
import json

import pytest

from lapsim.experiments.search_provenance import verify_anchor,publish_verified,read_verified,save_new


def anchor_fixture():
    # Minimal declared provenance fixture, not a fabricated vehicle simulation.
    controller={'philosophy':'fixed'};case={'initial_soc':.7,'regen_available':False}
    car={'wheel_radius_m':.2};pack={'pack_capacity_j':1000.};driver={'setting':1}
    record={'status':'completed','eligible':True,'violations':[],'profile':'synthetic_awd',
        'controller':controller,'case':case,'car':car,'actuation':pack,'driver':driver,
        'course':{'geometry_sha256':'geometry','length_m':100.},
        'telemetry':[{'t_s':0.,'u_mps':5.,'v_mps':0.,'yaw_rad_s':0.,'pack_energy_j':700.,'wheel_omega_rad_s':[25.]*4}]}
    expected={'expected_controller':controller,'expected_case':case,'expected_car':car,
        'expected_pack':pack,'expected_driver':driver,'geometry_sha256':'geometry','distance_m':100.}
    return record,expected


@pytest.mark.parametrize('mismatch',['hash','geometry','length','controller','fixture','case','initial'])
def test_anchor_requires_original_hash_and_matching_inputs(mismatch):
    record,expected=anchor_fixture()
    if mismatch=='geometry':record['course']['geometry_sha256']='different'
    elif mismatch=='length':record['course']['length_m']=101.
    elif mismatch=='controller':record['controller']={'philosophy':'other'}
    elif mismatch=='fixture':record['actuation']={'pack_capacity_j':2000.}
    elif mismatch=='case':record['case']={'initial_soc':.8,'regen_available':False}
    elif mismatch=='initial':record['telemetry'][0]['u_mps']=4.
    blob=json.dumps(record).encode();identity='wrong' if mismatch=='hash' else sha256(blob).hexdigest()
    with pytest.raises(ValueError):verify_anchor(blob,identity,**expected)


def test_verified_anchor_is_accepted_without_stamping_new_geometry():
    record,expected=anchor_fixture();blob=json.dumps(record).encode()
    assert verify_anchor(blob,sha256(blob).hexdigest(),**expected)==record


def test_source_drift_never_publishes_staged_eligible_result(tmp_path):
    row={'status':'completed','eligible':True,'raw_record_sha256':'raw','net_energy_kwh':.01}
    save_new(tmp_path/'staged/course.summary.json',{**row,'verification_state':'unverified_batch'})
    with pytest.raises(ValueError,match='Source drift'):
        publish_verified(tmp_path,'candidate','train',{'course':row},before_sources={'file':'before'},after_sources={'file':'after'})
    assert not (tmp_path/'course.summary.json').exists()
    assert read_verified(tmp_path/'course.summary.json',{'file':'before'},'candidate','train','course') is None


def test_receipt_source_and_summary_hashes_are_required_for_ranking(tmp_path):
    row={'status':'completed','eligible':True,'raw_record_sha256':'raw','net_energy_kwh':.01}
    sources={'file':'same'}
    publish_verified(tmp_path,'candidate','train',{'course':row},before_sources=sources,after_sources=sources)
    path=tmp_path/'course.summary.json'
    assert read_verified(path,sources,'candidate','train','course')['eligible'] is True
    assert read_verified(path,{'file':'changed'},'candidate','train','course') is None
    data=json.loads(path.read_text());data['net_energy_kwh']=0.
    path.write_text(json.dumps(data))
    assert read_verified(path,sources,'candidate','train','course') is None
