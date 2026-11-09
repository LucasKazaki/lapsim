"""One-lap physical-gate receipts; reference distance is never the finish test."""
from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite
def require(v,m):
    if not v:raise ValueError(m)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return sha256(canonical(v).encode()).hexdigest()
def crossing(events,*,tick,before_pose,after_pose,before_pack,after_pack,state,memory,
             before_state,source_sha256,source_length_m,source_before_m,source_after_m,gate):
    require(events in ((),[]) and type(tick) is int and tick>0,'Only one-lap fresh history')
    require(all(type(v) in (int,float) and isfinite(v) for v in (*before_pose,*after_pose,before_pack,after_pack,
        source_length_m,source_before_m,source_after_m)),'Finite physical gate inputs')
    require(gate['origin_xy_m']==[0.,0.] and gate['forward_unit']==[1.,0.],'Pinned source physical gate')
    d0,d1=before_pose[0],after_pose[0]
    if not(d0<0<=d1):return tuple(events)
    if source_after_m<.75*source_length_m:return tuple(events) # do not count initial departure/other track arms
    fraction=-d0/(d1-d0);y=before_pose[1]+fraction*(after_pose[1]-before_pose[1])
    if abs(y)>gate['finite_half_width_m']:return tuple(events) # crossing an infinite plane is not crossing the finite gate
    require(abs(source_after_m-source_length_m)<=2. and 0<d1-d0<=.5 and abs(source_after_m-source_before_m)<=.5,
        'Gate crossing/source winding inconsistent')
    require(abs(y)<=gate['finite_half_width_m'] and 0<=fraction<=1 and 0<=before_pack<=18000000 and 0<=after_pack<=18000000,
        'Outside physical gate segment or pack domain')
    time0=(tick-1)*.001;time1=tick*.001;energy=before_pack+fraction*(after_pack-before_pack)
    seam={'time_s':time0+fraction*(time1-time0),'pack_energy_j':energy,'fraction':fraction,
        'accepted_interval_s':[time0,time1],'gate_signed_distances_m':[d0,d1],
        'pose_endpoints_xy_m':[list(before_pose),list(after_pose)],'pack_endpoints_j':[before_pack,after_pack],
        'gate_sha256':digest(gate),'source_progress_endpoints_m':[source_before_m,source_after_m],
        'scope':'Physical source-gate intersection;time/pack interpolate,accepted physical state unchanged'}
    event={'lap':1,'source_sha256':source_sha256,'boundary_tick':tick,'crossing':seam,
        'lap_time_s':seam['time_s'],'lap_net_battery_wh':(9000000.-energy)/3600,
        'cumulative_net_battery_wh':(9000000.-energy)/3600,'accepted_state':deepcopy(state),'accepted_memory':deepcopy(memory),
        'accepted_state_sha256':digest(state),'accepted_memory_sha256':digest(memory),'previous_lap_sha256':None,
        'before_state':deepcopy(before_state),'before_state_sha256':digest(before_state),
        'state_scope':'Full accepted tick without reset/backstep;not a source-line percentage','awards':None}
    require(event['lap_time_s']>0,'Positive physical lap time required')
    return (event,)

def validate(events,*,source_sha256,current_tick,current_source_progress_m,source_length_m,gate):
    require(type(events) in (tuple,list) and len(events)<=1,'Finite one-lap history')
    if not events:return True
    event=events[0];seam=event['crossing'];tick=event['boundary_tick']
    expected=crossing((),tick=tick,before_pose=seam['pose_endpoints_xy_m'][0],after_pose=seam['pose_endpoints_xy_m'][1],
        before_pack=seam['pack_endpoints_j'][0],after_pack=seam['pack_endpoints_j'][1],state=event['accepted_state'],
        before_state=event['before_state'],
        memory=event['accepted_memory'],source_sha256=source_sha256,source_length_m=source_length_m,
        source_before_m=seam['source_progress_endpoints_m'][0],source_after_m=seam['source_progress_endpoints_m'][1],gate=gate)
    require(len(expected)==1 and canonical(expected[0])==canonical(event) and type(tick) is int and 0<tick<=current_tick and
        abs(event['accepted_memory']['source_progress_m']-seam['source_progress_endpoints_m'][1])<=1e-9 and
        current_source_progress_m>=seam['source_progress_endpoints_m'][1]-.5,'Gate receipt/current lineage differs')
    power=event['accepted_state']['thermal']['light']['powered']
    prior=event['before_state']['thermal']['light']['powered']
    require(power['pack_energy_j']==seam['pack_endpoints_j'][1] and
        prior['pack_energy_j']==seam['pack_endpoints_j'][0] and
        [power['plant']['x_m'],power['plant']['y_m']]==seam['pose_endpoints_xy_m'][1] and
        [prior['plant']['x_m'],prior['plant']['y_m']]==seam['pose_endpoints_xy_m'][0] and
        event['before_state']['thermal']['light']['feedback_ticks']==tick-1 and
        event['accepted_state']['thermal']['light']['feedback_ticks']==tick and
        event['accepted_memory']['blend_updates']==tick,'Boundary physical/energy clocks differ')
    return True
