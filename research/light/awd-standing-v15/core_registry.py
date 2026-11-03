"""Seven source-only OFF candidates mapped to the actual philosophy PDF."""
from copy import deepcopy
import policy_layers
SCHEMA='lapsim.torque-light-awd-racingline-seven-registry.v4'
TOPOLOGY='synthetic_independent_four_awd_v1'
TORQUE=policy_layers.IDS
IDS=tuple('awd7-'+key.replace('_','-')+'-v4' for key in TORQUE)
MAPPING=dict(zip(IDS,TORQUE))
REGEN=('off',)
def entries():
    return [{'id':config,'torque':key,'regen':'off','regen_enabled':False,'supported_topology':TOPOLOGY,
        'controller':{'architecture':key,'parameters':dict(policy_layers.PARAMETERS)},
        'source_supported':True,'native_qualification':'UNRUN','campaign_eligible':False,
        'calibration':'synthetic provisional;not verified actual-car maps'} for config,key in MAPPING.items()]
def entry(config):
    if config not in IDS:raise ValueError('Exact seven-family AWD/OFF source candidate required')
    return deepcopy(next(v for v in entries() if v['id']==config))
def hardware_eligibility(topology):
    return {'topology':topology,'source_supported':topology==TOPOLOGY,'native_qualification':'UNRUN','campaign_eligible':False,
        'drive_availability':[True]*4,'steering':'parallel front only','regen':'excluded pending separate low-speed/brake qualification'}
def validate(value):
    if set(value)!={'schema','policies','hardware','courses'} or value['schema']!=SCHEMA or value['policies']!=entries() or value['hardware']!=hardware_eligibility(TOPOLOGY):
        raise ValueError('Registry identity differs')
    if len(value['courses'])!=1 or value['courses'][0]['id']!='amz_fssim_fsi_approx':raise ValueError('Exact FSI source course required')
