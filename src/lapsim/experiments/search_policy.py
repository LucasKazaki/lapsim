"""Seeded policy structures using the existing allocation/brake core.

No independent physics or copied controller implementation. A policy selects
existing slip/yaw/reserve primitives and bounded gains from ideal kinematics,
held steering and pack SOC. True road grip is never an input to dispatch.
"""
from dataclasses import asdict,dataclass,fields,replace
from hashlib import sha256
import json
from math import cos,sin
import random

from lapsim.qmc_sampler import latin_hypercube
from .tournament_rollout import Controller,number,BOUNDS

STRUCTURES=('static','slip','yaw','reserve','composed','adaptive')
REGEN_MODES=('off','two_stage','proportional')
GENE_BOUNDS={**BOUNDS,'allocation_front_bias':(.15,.85),'launch_speed_mps':(3.,10.),
    'corner_threshold_rad':(.03,.2),'low_soc_threshold':(.3,.9),'economy_scale':(.6,1.)}
DEFAULTS={'slip_target':.1,'yaw_kp':0.,'yaw_ki':0.,'regen_fraction':.65,'regen_region':.25,
    'launch_speed_mps':6.,'corner_threshold_rad':.1,'low_soc_threshold':.7,'economy_scale':.8}


@dataclass(frozen=True)
class AllocationPolicy(Controller):
    slip_control: bool=False
    yaw_control: bool=False
    reserve_control: bool=False
    allocation_front_bias: float=.5

    def __post_init__(self):
        super().__post_init__()
        if any(type(getattr(self,name)) is not bool for name in ('slip_control','yaw_control','reserve_control')):
            raise ValueError('Allocation switches must be booleans')
        number(self.allocation_front_bias,'allocation_front_bias',.15,.85)


@dataclass(frozen=True)
class SearchPolicy(Controller):
    structure: str='static'
    regen_mode: str='off'
    allocation_front_bias: float=.5
    launch_speed_mps: float=6.
    corner_threshold_rad: float=.1
    low_soc_threshold: float=.7
    economy_scale: float=.8

    def __post_init__(self):
        super().__post_init__()
        if self.structure not in STRUCTURES or self.regen_mode not in REGEN_MODES:
            raise ValueError('Unsupported search policy structure or regen mode')
        expected='proportional' if self.regen_mode=='proportional' else 'two_stage'
        if self.pedal_mode!=expected:raise ValueError('Regen identity conflicts with pedal mode')
        for name,bounds in GENE_BOUNDS.items():number(getattr(self,name),name,*bounds)

    def effective_policy(self,state,steering,car,pack):
        structure=self.structure;mode=structure
        flags={'static':(False,False,False),'slip':(True,False,False),
            'yaw':(False,True,False),'reserve':(False,False,True),
            'composed':(True,True,True)}
        scale=self.drive_scale
        if structure=='adaptive':
            p=state.plant;slips=[]
            for i,(x,y) in enumerate(car.wheel_positions_m):
                angle=steering if i<2 else 0.
                local=cos(angle)*(p.u_mps-p.yaw_rate_rad_s*y)+sin(angle)*(p.v_mps+p.yaw_rate_rad_s*x)
                slips.append((car.wheel_radius_m*p.wheel_speeds_rad_s[i]-local)/max(abs(local),car.low_speed_regularization_mps))
            if max(slips)>self.slip_target*1.05:mode='slip_protection';bits=(True,False,False)
            elif p.u_mps<self.launch_speed_mps:mode='launch_slip';bits=(True,False,False)
            elif abs(steering)>=self.corner_threshold_rad:mode='corner_composed';bits=(True,True,True)
            elif state.pack_energy_j/pack.pack_capacity_j<self.low_soc_threshold:
                mode='economy';bits=(False,False,False);scale=max(BOUNDS['drive_scale'][0],scale*self.economy_scale)
            else:mode='cruise';bits=(False,False,False)
        else:bits=flags[structure]
        base={field.name:getattr(self,field.name) for field in fields(Controller)}
        base['drive_scale']=scale
        return AllocationPolicy(**base,slip_control=bits[0],yaw_control=bits[1],reserve_control=bits[2],
            allocation_front_bias=self.allocation_front_bias),mode


def active_genes(structure,regen):
    active={'drive_scale','allocation_front_bias'}
    if structure in ('slip','composed','adaptive'):active.add('slip_target')
    if structure in ('yaw','composed','adaptive'):active.update(('yaw_kp','yaw_ki'))
    if structure=='adaptive':active.update(('launch_speed_mps','corner_threshold_rad','low_soc_threshold','economy_scale'))
    if regen!='off':active.add('regen_fraction')
    if regen=='two_stage':active.add('regen_region')
    return tuple(name for name in GENE_BOUNDS if name in active)


def normalized_policy(structure,regen,genes):
    active=active_genes(structure,regen)
    values={name:float(genes[name]) if name in active else DEFAULTS[name]
        for name in GENE_BOUNDS}
    return SearchPolicy(philosophy='fixed',structure=structure,regen_mode=regen,
        pedal_mode='proportional' if regen=='proportional' else 'two_stage',**values)


def policy_digest(policy):
    return sha256(json.dumps(asdict(policy),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def initial_population(seed):
    design=latin_hypercube(len(GENE_BOUNDS),seed).random(n=18)
    result=[]
    for index,(structure,regen) in enumerate((s,r) for s in STRUCTURES for r in REGEN_MODES):
        genes={name:lo+float(design[index,j])*(hi-lo) for j,(name,(lo,hi)) in enumerate(GENE_BOUNDS.items())}
        policy=normalized_policy(structure,regen,genes)
        result.append({'id':f'g0-{index:02d}-{structure}-{regen}','policy':asdict(policy),
            'sha256':policy_digest(policy),'active_genes':active_genes(structure,regen),'origin':'stratified seeded initial design'})
    return result


def offspring(parents,seed,seen,count=6):
    """Four recombined/mutated children and two random immigrants, deduplicated."""
    rng=random.Random(seed);result=[];known=set(seen)
    if not parents:raise ValueError('No eligible parents')
    for index in range(count):
        for attempt in range(100):
            immigrant=index>=count-2
            first,second=rng.choice(parents),rng.choice(parents)
            a,b=first['policy'],second['policy']
            structure=rng.choice(STRUCTURES) if immigrant or rng.random()<.35 else rng.choice((a['structure'],b['structure']))
            regen=rng.choice(REGEN_MODES) if immigrant or rng.random()<.25 else rng.choice((a['regen_mode'],b['regen_mode']))
            genes={}
            for name,(lo,hi) in GENE_BOUNDS.items():
                value=float(rng.choice((a,b))[name])
                if immigrant:value=rng.uniform(lo,hi)
                elif rng.random()<.5:value+=rng.gauss(0,.2*(hi-lo))
                genes[name]=min(hi,max(lo,value))
            policy=normalized_policy(structure,regen,genes);identity=policy_digest(policy)
            if identity not in known:break
        else:raise ValueError('Could not generate a distinct active genome')
        known.add(identity)
        result.append({'id':f'g1-{index:02d}-{structure}-{regen}','policy':asdict(policy),'sha256':identity,
            'active_genes':active_genes(structure,regen),'origin':'random immigrant' if immigrant else 'crossover and bounded mutation',
            'parents':[] if immigrant else [first['id'],second['id']]})
    return result
