"""Versioned development FSG numerical consumer, not an admitted campaign worker.

Uses the unchanged verified sampled metric, real driver/allocator/plant functions
and an explicitly required original residual predicate. No observer, guard, lease,
worker registration, checkpoint restore, signing or admission is supplied here.
The initial CG/tangent convention and all car parameters are synthetic. Raw
snapshots cannot be passed to the FSI worker or used as continuation authority.
"""
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import atan2, ceil, hypot, isfinite
from threading import Event, Lock
from time import monotonic

from lapsim_light_core.planar import PlanarState
from lapsim_light_core.powered_planar import PoweredState, energy_residual_j
from lapsim_light_core.torque_light_combined import initialize_combined_light
from lapsim_light_core.torque_light_thermal import evaluate_thermal_light
from lapsim_light_course import fsg_phase as phase, fsg_smoothing as sm, racing_geometry
from lapsim_light_course.course import SourceTrack, construct_fsg_course
from lapsim_light_guidance.driver import _project_local, _path_point, _controller, _validate_sampled_polyline
from lapsim_light_policies import core_adapter, core_registry, awd_contracts
from .fixture import construct_standing_fixture, fixture_resource_bytes
from .input_contracts import encode, digest, is_sha256, require
from .numerical_bridge import Memory
from .numerical_inputs import ResidualRegenRule, NumericalDependencyUnavailable
from .plant_tick import advance_tick

FAMILY='lapsim.fsg-development-numerical-consumer.v1'
COURSE_SCHEMA='lapsim.fsg-development-metric-course.v1'
SNAPSHOT_SCHEMA='lapsim.fsg-development-numerical-snapshot.raw.v1'
INTERVAL_SCHEMA='lapsim.fsg-development-numerical-interval.raw.v1'
MAX_ADVANCE_TICKS=1000
MAX_ADVANCE_WORK=50000
MAX_RAW_BYTES=1024*1024
ZERO=(0.,)*4
AVAILABLE=awd_contracts.AVAILABLE

def _error_text(error):
    try:return str(error)[:1024]
    except BaseException:return '<exception message unavailable>'

@dataclass(frozen=True,slots=True)
class FsgRawInterval:
    """Literal locked endpoint bytes; data only, never admission or a receipt."""
    before_raw: bytes
    interval_raw: bytes
    after_raw: bytes

class FsgDevelopmentDeadlineExceeded(RuntimeError):
    """Retained staged bytes are quarantined, not a successfully returned interval."""
    def __init__(self,raw_interval,raw_record=None):
        super().__init__('Development deadline exceeded during output finalization; raw interval quarantined')
        self.raw_interval=raw_interval
        self.raw_record=raw_record
        self.qualification_or_execution_authority=False

@dataclass(frozen=True,slots=True)
class _AcceptedBoundary:
    state: object
    memory: Memory
    tick: int=0
    departed: bool=False
    armed: bool=False
    finish: dict | None=None
    status: str='running'

@dataclass(frozen=True,slots=True,init=False)
class FsgNumericalCourse:
    """Complete readback plus exact retained chord metric, not a new curve fit."""
    raw: bytes
    phase: phase.FsgSmoothedPhaseView
    source: object
    track: SourceTrack

    def __init__(self,phase_raw,reference_raw,bundle_raw,cones_raw,*,work_wall_s=40.):
        budget=sm._Budget(work_wall_s)
        phase._parse(phase_raw)
        base=phase._verified_base(reference_raw,bundle_raw,cones_raw,budget)
        checked=phase._build_phase_from_verified(base,bundle_raw,cones_raw,budget)
        require(checked.raw==phase_raw,'Numerical phase differs from complete readback')
        source=construct_fsg_course(bundle_raw,cones_raw)
        v=base.payload();g=v['screens']['geometry'];sampling=v['screens']['sampling']
        track=SourceTrack(*(tuple(g[k]) for k in ('distance_m','x_m','y_m','curvature_per_m')),closed=True)
        _validate_sampled_polyline(track)
        parameter=checked.payload()['root']['representative_parameter_index']
        nodes=sampling['parameter_nodes'];i=min(bisect_right(nodes,parameter)-1,track.cell_count-1)
        require(0<=i<track.cell_count and nodes[i]<nodes[i+1],'Valid saved parameter/metric bracket required')
        fraction=(parameter-nodes[i])/(nodes[i+1]-nodes[i])
        seed=track.distance_m[i]+fraction*track.cell_length_m[i]
        xy=checked.evaluate(0.);tangent=checked.evaluate(0.,1)
        require(hypot(*tangent)>1e-6,'Regular synthetic initial tangent required')
        rp=_project_local(track,*xy,seed,12.)
        sp=_project_local(source.source_track,*xy,0.,12.)
        require(abs(rp.station_m-seed)<.1 and 0<sp.station_m<12.,'FSG gate projection seed unresolved')
        record={'schema':COURSE_SCHEMA,'family':FAMILY,'course_id':'amz_fssim_fsg_approx',
            'base_reference_sha256':sha256(reference_raw).hexdigest(),'phase_sha256':sha256(phase_raw).hexdigest(),
            'source_bundle_sha256':sha256(bundle_raw).hexdigest(),'cones_sha256':sha256(cones_raw).hexdigest(),
            'source_geometry_sha256':source.geometry_sha256,'frame_sha256':digest(source.frame_dict()),
            'retained_sampled_geometry_sha256':digest(g),'parameter_table_sha256':digest(nodes),
            'reference_length_m':track.length_m,'source_length_m':source.source_track.length_m,
            'reference_station_offset_m':rp.station_m,'source_station_offset_m':sp.station_m,
            'reference_seed_station_m':seed,'initial_reference_cross_track_m':rp.cross_track_m,
            'initial_source_cross_track_m':sp.cross_track_m,'initial_cg_xy_m':list(xy),
            'initial_heading_rad':atan2(tangent[1],tangent[0]),
            'initialization':'SYNTHETIC_CG_AT_REPRESENTATIVE_GATE_WITH_ANALYTIC_TANGENT_NOT_SOURCE_FRONT_WING',
            'progress_units':'ABSOLUTE_UNWRAPPED_SAVED_METRIC_STATIONS_METRES_WITH_SEPARATE_START_OFFSETS',
            'progress_is_exact_new_curve_arclength':False,'parameter_to_metric_is_search_seed_only':True,
            'geometry_resampled_or_refitted_or_rephased':False,
            'maximum_curve_to_sampled_view_floating_bound_m':sampling['maximum_cubic_to_view_error_bound_m'],
            'source_or_environment_or_line_authenticated':False,'actual_car_or_native_qualified':False,
            'heldout_results_used':False,'qualification_or_execution_authority':False}
        object.__setattr__(self,'raw',encode(record));object.__setattr__(self,'phase',checked)
        object.__setattr__(self,'source',source);object.__setattr__(self,'track',track)
        budget.check()

    def metadata(self):return sm.json.loads(self.raw)


def event_transition(course,*,departed,armed,tick,before_xy,after_xy,before_pack_j,after_pack_j,
        before_relative_reference_m,after_relative_reference_m,before_relative_source_m,after_relative_source_m):
    """Pure development event arithmetic; fabricated inputs grant no state authority."""
    require(type(course) is FsgNumericalCourse and type(departed) is bool and type(armed) is bool and
        (not armed or departed) and type(tick) is int and tick>0,'Exact development event boundary required')
    require(all(type(p) in (tuple,list) and len(p)==2 for p in (before_xy,after_xy)),
        'Two-dimensional finite gate endpoint pairs required')
    numbers=(*before_xy,*after_xy,before_pack_j,after_pack_j,before_relative_reference_m,
        after_relative_reference_m,before_relative_source_m,after_relative_source_m)
    require(all(type(v) in (int,float) and isfinite(v) for v in numbers),'Finite event interval required')
    require(hypot(after_xy[0]-before_xy[0],after_xy[1]-before_xy[1])<=.5 and
        abs(after_relative_reference_m-before_relative_reference_m)<=.5 and
        abs(after_relative_source_m-before_relative_source_m)<=.5,'Discontinuous event interval rejected')
    gate=course.phase.payload()['gate'];o,n=gate['origin_xy_m'],gate['forward_unit']
    signed=sum((after_xy[i]-o[i])*n[i] for i in (0,1))
    if not departed:
        # The representative may lie a few 1e-11m behind the exact digital gate.
        # Its first forward hit is departure, never a finished lap.
        departed=after_relative_reference_m>.5 and after_relative_source_m>.5 and signed>1e-6
        return (departed,False),None
    rlength,slength=course.track.length_m,course.source.source_track.length_m
    previously_armed=armed
    armed=armed or (after_relative_reference_m>=.75*rlength and after_relative_source_m>=.75*slength)
    require(course.phase.finite_segment_crossing(after_xy,before_xy) is None,'Reverse finite gate crossing after departure')
    hit=course.phase.finite_segment_crossing(before_xy,after_xy)
    if hit is None:return (departed,armed),None
    require(previously_armed and min(before_relative_reference_m,after_relative_reference_m)>=.75*rlength and
        min(before_relative_source_m,after_relative_source_m)>=.75*slength and
        abs(after_relative_reference_m-rlength)<=2. and abs(after_relative_source_m-slength)<=2.,
        'Finite crossing without both complete gate-relative windings')
    require(0<=before_pack_j<=18000000 and 0<=after_pack_j<=18000000,'Event pack domain differs')
    f=hit['fraction'];time_s=(tick-1+f)*.001;energy=before_pack_j+f*(after_pack_j-before_pack_j)
    return (departed,armed),{'schema':'lapsim.fsg-development-finish.raw.v1','boundary_tick':tick,
        'fraction':f,'fraction_exact':hit['fraction_exact'],'point_xy_m':hit['point_xy_m'],
        'accepted_interval_s':[(tick-1)*.001,tick*.001],'time_s':time_s,'pack_energy_j':energy,
        'net_battery_wh':(9000000.-energy)/3600.,'pose_endpoints_xy_m':[list(before_xy),list(after_xy)],
        'pack_endpoints_j':[before_pack_j,after_pack_j],
        'relative_reference_endpoints_m':[before_relative_reference_m,after_relative_reference_m],
        'relative_source_endpoints_m':[before_relative_source_m,after_relative_source_m],
        'phase_sha256':course.metadata()['phase_sha256'],'base_reference_sha256':course.metadata()['base_reference_sha256'],
        'scope':'DEVELOPMENT_FINITE_CG_GATE_INTERSECTION_TIME_PACK_INTERPOLATION_ACCEPTED_STATE_NOT_RESET',
        'physical_interval_authentication_supplied':False,'awards':None,'qualification_or_execution_authority':False}


class FsgDevelopmentConsumer:
    """Finite one-process numerical component, not native Start or continuation.

    Owns accepted state. Returned raw bytes have no restore/accept/admission API.
    A required predicate's pin checks input consistency only, not authentication.
    Tests using a double must label that dependency separately from real physics.
    """
    def __init__(self,course,*,policy_id,residual_regen_rule,residual_regen_rule_sha256,
                 maximum_ticks,maximum_work):
        require(type(course) is FsgNumericalCourse,'Exact fully constructed FSG numerical course required')
        method=getattr(residual_regen_rule,'residual_low_speed_regen',None)
        if not callable(method) or getattr(method,'__func__',method) is ResidualRegenRule.residual_low_speed_regen:
            raise NumericalDependencyUnavailable('Original residual-regeneration predicate required; no fallback')
        require(is_sha256(residual_regen_rule_sha256) and
            getattr(residual_regen_rule,'implementation_sha256',None)==residual_regen_rule_sha256,
            'Residual predicate differs from explicit input pin; hash is not authentication')
        core_registry.entry(policy_id)
        horizon=(ceil(course.track.length_m/3.)+30)*1000
        require(type(maximum_ticks) is int and 1<=maximum_ticks<=horizon and
            type(maximum_work) is int and 1<=maximum_work<=8*maximum_ticks,'Explicit finite tick/work limits required')
        f=construct_standing_fixture(fixture_resource_bytes(),reference_length_m=course.track.length_m,
            reference_geometry_sha256=course.metadata()['retained_sampled_geometry_sha256'])
        core_adapter.ensure_topology(f.actuation,AVAILABLE)
        m=course.metadata();point=PlanarState(x_m=m['initial_cg_xy_m'][0],y_m=m['initial_cg_xy_m'][1],
            heading_rad=m['initial_heading_rad'],u_mps=0.,wheel_speeds_rad_s=ZERO)
        state=initialize_combined_light(f.settings,f.thermal,f.drs_policy,f.actuation,
            PoweredState(point,ZERO,9000000.),f.environment,initial_temperature_c=70.,
            automatic_drs_enabled=True,load_longitudinal_mps2=0.,load_lateral_mps2=0.)
        self.course,self.fixture=course,f
        self._driver=replace(f.driver,target_progress_m=m['reference_station_offset_m']+course.track.length_m)
        p=course.phase.reference.payload()['proposal']['parameters']
        self._body=(p['front_m'],p['rear_m'],p['width_m'],p['safety_margin_m']+p['map_uncertainty_m'])
        self._frame=course.source.frame_dict()  # Owned copy of the verified immutable frame.
        self._rule=residual_regen_rule;self._rule_pin=residual_regen_rule_sha256
        self._policy_id=policy_id;self._case=core_adapter.case_for(policy_id)
        self._initial=state
        self._boundary=_AcceptedBoundary(state,Memory(previous_progress=m['reference_station_offset_m'],source_progress_m=m['source_station_offset_m']))
        self._violation=None;self._rejected=None
        self._attempted_work=0;self._cancel=Event();self._lock=Lock()
        self._work_accounting_complete=True;self._quarantined_interval_sha256=None
        self._context_raw=encode({'family':FAMILY,'course':m,'fixture':sm.json.loads(f.configuration_json),
            'policy':core_registry.entry(policy_id),'maximum_ticks':maximum_ticks,'maximum_work':maximum_work,
            'clocks':{'plant_s':.001,'driver_ticks':50,'allocator_ticks':10,'logging_ticks':20},
            'guidance_driver':asdict(self._driver),
            'guidance_target_scope':'ABSOLUTE_UNWRAPPED_REFERENCE_STATION_R0_PLUS_LENGTH_NOT_A_FINISH_TEST',
            'cancellation_scope':'COOPERATIVE_TICK_BOUNDARY_IN_FLIGHT_TICK_MAY_COMMIT_THEN_CANCEL_OBSERVED_NEXT_BOUNDARY',
            'residual_regen_rule_input_pin':residual_regen_rule_sha256,
            'source_environment_or_rule_authenticated':False,'checkpoint_restore_supported':False,
            'native_or_campaign_registered':False,'qualification_or_execution_authority':False})
        self._limits=(maximum_ticks,maximum_work)
        self._observe(state,self._memory,0)

    @property
    def _state(self):return self._boundary.state
    @property
    def _memory(self):return self._boundary.memory
    @property
    def _tick(self):return self._boundary.tick
    @property
    def _departed(self):return self._boundary.departed
    @property
    def _armed(self):return self._boundary.armed
    @property
    def _finish(self):return self._boundary.finish
    @_finish.setter
    def _finish(self,value):self._boundary=replace(self._boundary,finish=value)
    @property
    def _status(self):return self._boundary.status
    @_status.setter
    def _status(self,value):self._boundary=replace(self._boundary,status=value)

    def _publish_boundary(self,boundary):
        self._boundary=boundary  # Single immutable accepted-record publication.

    def request_cancel(self):self._cancel.set()

    def snapshot(self):
        require(self._lock.acquire(blocking=False),'Snapshot requires a returned numerical call')
        try:return self._snapshot()
        finally:self._lock.release()

    def _snapshot(self):
        m=self.course.metadata()
        raw=encode({'schema':SNAPSHOT_SCHEMA,'family':FAMILY,'context':sm.json.loads(self._context_raw),
            'context_sha256':sha256(self._context_raw).hexdigest(),'tick':self._tick,'status':self._status,
            'state':asdict(self._state),'state_sha256':digest(asdict(self._state)),'memory':asdict(self._memory),
            'relative_reference_progress_m':self._memory.previous_progress-m['reference_station_offset_m'],
            'relative_source_progress_m':self._memory.source_progress_m-m['source_station_offset_m'],
            'departed':self._departed,'armed':self._armed,'finish':self._finish,'violation':self._violation,
            'rejected_attempt':self._rejected,'attempted_numerical_work':self._attempted_work,
            'attempted_numerical_work_is_lower_bound':not self._work_accounting_complete,
            'quarantined_interval_sha256':self._quarantined_interval_sha256,
            'cancellation_requested':self._cancel.is_set(),
            'checkpoint_restore_or_continuation_authority':False,'awards':None,'heldout_results_used':False,
            'qualification_or_execution_authority':False})
        require(len(raw)<=MAX_RAW_BYTES,'Development snapshot exceeds raw capacity')
        return raw

    def _observe(self,state,memory,tick):
        f=self.fixture;p=state.thermal.light.powered;point=p.plant;meta=self.course.metadata()
        rp=_project_local(self.course.track,point.x_m,point.y_m,memory.previous_progress,12.)
        sp=_project_local(self.course.source.source_track,point.x_m,point.y_m,memory.source_progress_m,12.)
        require(abs(rp.station_m-memory.previous_progress)<=.5 and abs(sp.station_m-memory.source_progress_m)<=.5,
            'Projection discontinuity exceeds 1ms domain')
        for track,projection in ((self.course.track,rp),(self.course.source.source_track,sp)):
            px,py=_path_point(track,projection.station_m)
            require(hypot(point.x_m-px,point.y_m-py)<=f.driver.usable_half_width_m,
                'Full projection residual exceeds declared synthetic driver corridor')
        require(-.5<=rp.station_m-meta['reference_station_offset_m']<=self.course.track.length_m+1. and
            -.5<=sp.station_m-meta['source_station_offset_m']<=self.course.source.source_track.length_m+1.,
            'Gate-relative progress outside one-lap development domain')
        _,physical,electrical=evaluate_thermal_light(f.settings,f.thermal,f.actuation,state.thermal,
            memory.held,memory.steer,ZERO,AVAILABLE,f.environment,aero_mode=state.drs.actual_mode)
        require(physical.road_valid and all(w.road_valid and w.normal_load_n>=0 and abs(w.slip_ratio)<=1 and
            w.force_utilization<=1+32*2.220446049250313e-16 for w in physical.wheels),'Road/slip/combined force domain exceeded')
        require(point.u_mps>=0 and abs(point.yaw_rate_rad_s)<=2 and abs(atan2(point.v_mps,max(.5,point.u_mps)))<=.5 and
            all(v>=0 for v in point.wheel_speeds_rad_s) and 0<=p.pack_energy_j<=f.actuation.pack_capacity_j,
            'Forward numerical velocity/wheel/pack domain exceeded')
        require(getattr(self._rule,'implementation_sha256',None)==self._rule_pin,'Residual predicate input pin changed')
        residual_regen=self._rule.residual_low_speed_regen(point.u_mps,electrical)
        require(type(residual_regen) is bool and not residual_regen,'Residual low-speed regeneration or nonboolean predicate')
        require(electrical.pack_power_w>=0 and all(v>=0 for v in electrical.wheel_torques_nm),
            'OFF development domain rejects generating actual power/torque')
        front,rear,width,margin=self._body
        slack=racing_geometry.footprint_clearance(self._frame,
            (point.x_m,point.y_m,point.heading_rad),front_m=front,rear_m=rear,width_m=width,margin_m=margin)
        require(slack>=0,'Synthetic physical rectangle outside approximate cone corridor')
        residual=energy_residual_j(f.settings.forces.plant,self._initial.thermal.light.powered,p)
        require(abs(residual)<=.002+128*2.220446049250313e-16*f.actuation.pack_capacity_j*(p.integration_trials+tick+1),
            'Mechanical energy residual exceeded')
        require(tick==state.drs.ticks==state.thermal.thermal.ticks==state.thermal.light.feedback_ticks,'Physical component clocks disagree')
        return rp,sp,physical,electrical,slack,residual

    def _row(self):
        p=self._state.thermal.light.powered;m=self.course.metadata()
        return {'tick':self._tick,'state_sha256':digest(asdict(self._state)),
            'pose_xy_m':[p.plant.x_m,p.plant.y_m],'heading_rad':p.plant.heading_rad,'u_mps':p.plant.u_mps,
            'pack_energy_j':p.pack_energy_j,'absolute_reference_station_m':self._memory.previous_progress,
            'absolute_source_station_m':self._memory.source_progress_m,
            'relative_reference_progress_m':self._memory.previous_progress-m['reference_station_offset_m'],
            'relative_source_progress_m':self._memory.source_progress_m-m['source_station_offset_m'],
            'requested_nm':self._memory.requested,'proposed_nm':self._memory.proposed,'limited_nm':self._memory.held,
            'steering_rad':self._memory.steer,'friction_nm':self._memory.friction,'status':self._status}

    def advance(self,*,ticks,work_wall_s,maximum_new_work=MAX_ADVANCE_WORK):
        return self._advance(ticks=ticks,work_wall_s=work_wall_s,
            maximum_new_work=maximum_new_work).interval_raw

    def advance_with_snapshots(self,*,ticks,work_wall_s,maximum_new_work=MAX_ADVANCE_WORK):
        """Return literal endpoints from the same locked and bounded operation."""
        return self._advance(ticks=ticks,work_wall_s=work_wall_s,maximum_new_work=maximum_new_work)

    def _advance(self,*,ticks,work_wall_s,maximum_new_work):
        require(type(ticks) is int and 1<=ticks<=MAX_ADVANCE_TICKS and
            type(work_wall_s) in (int,float) and isfinite(work_wall_s) and 0<work_wall_s<=10 and
            type(maximum_new_work) is int and 1<=maximum_new_work<=MAX_ADVANCE_WORK,'Finite development call limits required')
        require(self._lock.acquire(blocking=False),'Concurrent numerical writer refused')
        active_call=False
        try:
            require(self._status=='running','Terminal development event cannot advance or retry')
            active_call=True
            deadline=monotonic()+work_wall_s
            before=self._snapshot();start_tick=self._tick;start_work=self._attempted_work
            rows=[self._row()];f=self.fixture;meta=self.course.metadata()
            while self._tick<min(start_tick+ticks,self._limits[0]):
                if self._cancel.is_set():self._status='cancelled';break
                if monotonic()>=deadline:self._status='wall_limit';break
                remaining=min(self._limits[1]-self._attempted_work,maximum_new_work-(self._attempted_work-start_work))
                if remaining<=0:self._status='work_limit';break
                old_boundary=self._boundary
                old=self._state;m=self._memory;updated=None;stage='controls';work_unknown=False
                try:
                    rp,sp,physical,_,slack,_=self._observe(old,m,self._tick)
                    if self._tick%50==0:
                        command,_=_controller(self.course.track,f.settings.forces.plant,f.environment,self._driver,old.thermal.light.powered.plant,rp,slack)
                        m=replace(m,driver_command=awd_contracts.normalize_driver_command(command),driver_updates=m.driver_updates+1)
                    require(m.driver_command is not None,'Missing saved driver command')
                    m=replace(m,steer=m.driver_command.steering_angles_rad)
                    if self._tick%10==0:
                        allocation=core_adapter.allocate_core(self._policy_id,old.thermal.light.powered,physical,m.steer,
                            sum(m.driver_command.drive_torques_nm),sum(m.driver_command.brake_torques_nm),m.integral,
                            f.settings.forces.plant,f.actuation,self._case,.01)
                        m=replace(m,requested=allocation.requested,proposed=allocation.proposed,held=allocation.limited.wheel_torques_nm,
                            integral=allocation.integral,total_brake=allocation.total_brake,raw_regen=allocation.raw_regen,
                            last_allocation=allocation.diagnostics,allocator_updates=m.allocator_updates+1,
                            load_interventions=m.load_interventions+int(allocation.diagnostics.get('load_changed',False)),
                            energy_interventions=m.energy_interventions+int(allocation.diagnostics.get('energy_changed',False)),
                            feedforward_interventions=m.feedforward_interventions+int(core_registry.entry(self._policy_id)['torque']=='feedforward_off' and allocation.diagnostics.get('yaw_changed',False)),
                            slip_interventions=m.slip_interventions+int(allocation.diagnostics.get('slip_binding',False)),
                            yaw_interventions=m.yaw_interventions+int(allocation.diagnostics.get('yaw_changed',False)),
                            reserve_interventions=m.reserve_interventions+int(allocation.diagnostics.get('reserve_binding',False)),
                            regen_inhibited_updates=m.regen_inhibited_updates+int(allocation.diagnostics['regen_inhibited']))
                    if old.thermal.light.powered.plant.u_mps<=2:m=replace(m,held=tuple(max(0.,v) for v in m.held))
                    _,_,electrical=evaluate_thermal_light(f.settings,f.thermal,f.actuation,old.thermal,m.held,m.steer,ZERO,AVAILABLE,f.environment,aero_mode=old.drs.actual_mode)
                    friction,blend=core_adapter.brake_blend(m.total_brake,m.raw_regen,electrical)
                    require(blend['shortfall_nm']<=1e-6,'Common friction authority cannot meet requested braking')
                    m=replace(m,friction=friction,blend_updates=m.blend_updates+1,
                        electrical_limit_ticks=m.electrical_limit_ticks+int(bool(electrical.constraints)),
                        generating_boundaries=m.generating_boundaries+int(electrical.pack_power_w<0),
                        brake_redistribution_ticks=m.brake_redistribution_ticks+int(blend['redistributed']),
                        maximum_brake_overshoot_nm=max(m.maximum_brake_overshoot_nm,blend['overshoot_nm']))
                    stage='pre_plant'
                    require(monotonic()<deadline,'Development deadline exhausted before new plant work')
                    stage='plant';work_unknown=True
                    updated=advance_tick(f.settings,f.thermal,f.drs_policy,f.actuation,old,m.held,m.steer,friction,
                        f.environment,braking_requested=m.total_brake>0,maximum_work=remaining)
                    stage='post_step'
                    oldp,newp=old.thermal.light.powered,updated.thermal.light.powered
                    delta=newp.integration_trials+newp.wheel_stop_events-oldp.integration_trials-oldp.wheel_stop_events
                    require(type(delta) is int and 0<delta<=remaining,'Returned numerical work counters differ from finite cap')
                    self._attempted_work+=delta
                    work_unknown=False
                    require(monotonic()<deadline,'Development call wall limit exceeded by provisional tick')
                    nrp,nsp,nphysical,_,_,_=self._observe(updated,m,self._tick+1)
                    m=replace(m,previous_progress=nrp.station_m,source_progress_m=nsp.station_m,
                        sampled_draw_j=m.sampled_draw_j+max(0.,oldp.pack_energy_j-newp.pack_energy_j),
                        sampled_recovery_j=m.sampled_recovery_j+max(0.,newp.pack_energy_j-oldp.pack_energy_j),
                        maximum_slip=max(m.maximum_slip,max(abs(w.slip_ratio) for w in nphysical.wheels)),
                        maximum_utilization=max(m.maximum_utilization,max(w.force_utilization for w in nphysical.wheels)),
                        maximum_yaw=max(m.maximum_yaw,abs(newp.plant.yaw_rate_rad_s)))
                    stage='event'
                    flags,finish=event_transition(self.course,departed=self._departed,armed=self._armed,tick=self._tick+1,
                        before_xy=(oldp.plant.x_m,oldp.plant.y_m),after_xy=(newp.plant.x_m,newp.plant.y_m),
                        before_pack_j=oldp.pack_energy_j,after_pack_j=newp.pack_energy_j,
                        before_relative_reference_m=rp.station_m-meta['reference_station_offset_m'],
                        after_relative_reference_m=nrp.station_m-meta['reference_station_offset_m'],
                        before_relative_source_m=sp.station_m-meta['source_station_offset_m'],
                        after_relative_source_m=nsp.station_m-meta['source_station_offset_m'])
                    if finish is not None:
                        finish.update(before_state=asdict(old),accepted_state=asdict(updated),accepted_memory=asdict(m),
                            accepted_state_sha256=digest(asdict(updated)))
                    status=('development_completed' if finish is not None else
                            'time_limit' if self._tick+1==self._limits[0] else 'running')
                    candidate=_AcceptedBoundary(updated,m,self._tick+1,*flags,finish,status)
                    require(monotonic()<deadline,'Development deadline exceeded before physical/event commit')
                    stage='publication'
                    self._publish_boundary(candidate)
                except BaseException as exc:
                    self._boundary=old_boundary  # Also handles interruption immediately after publication.
                    if work_unknown:self._work_accounting_complete=False
                    self._status='invalid';self._violation=_error_text(exc)
                    self._rejected={'stage':stage,'candidate_tick':self._tick+1,'accepted_state_sha256':digest(asdict(self._state)),
                        'provisional_state':None if updated is None else asdict(updated),'provisional_memory':asdict(m),
                        'unreturned_numerical_work_unknown':work_unknown,'committed':False,'qualification_or_execution_authority':False}
                    if not isinstance(exc,(ValueError,ArithmeticError)):raise
                if self._tick%20==0 or self._status!='running':rows.append(self._row())
                if self._status!='running':break
            if rows[-1]['tick']!=self._tick or rows[-1]['status']!=self._status:rows.append(self._row())
            after=self._snapshot();packet=encode({'schema':INTERVAL_SCHEMA,'family':FAMILY,'context_sha256':sha256(self._context_raw).hexdigest(),
                'start_snapshot_sha256':sha256(before).hexdigest(),'end_snapshot_sha256':sha256(after).hexdigest(),
                'start_tick':start_tick,'end_tick':self._tick,'requested_ticks':ticks,'maximum_new_work':maximum_new_work,
                'attempted_work_delta':self._attempted_work-start_work,'rows':rows,'status':self._status,'finish':self._finish,
                'evidence_scope':'RAW_DEVELOPMENT_COMPONENT_WITH_REQUIRED_BUT_NOT_AUTHENTICATED_PREDICATE',
                'awards':None,'qualification_or_execution_authority':False})
            require(len(packet)<=MAX_RAW_BYTES,'Development interval exceeds raw capacity')
            captured=FsgRawInterval(before,packet,after)
            if monotonic()>=deadline:
                self._status='wall_limit';self._quarantined_interval_sha256=sha256(packet).hexdigest()
                if self._rejected is None:
                    self._rejected={'stage':'finalization','provisional_finish':self._finish,
                        'accepted_physics_retained':True,'unreturned_numerical_work_unknown':False,
                        'committed':False,'qualification_or_execution_authority':False}
                self._finish=None
                # No second serialization is attempted after the expired fence.
                # The owning caller retains exception bytes and snapshots later.
                raise FsgDevelopmentDeadlineExceeded(packet,captured)
            return captured
        except BaseException:
            if active_call and self._status in ('running','development_completed'):
                self._status='invalid'
                if self._rejected is None:
                    self._rejected={'stage':'output_serialization','provisional_finish':self._finish,
                        'accepted_physics_retained':True,'unreturned_numerical_work_unknown':False,
                        'committed':False,'qualification_or_execution_authority':False}
                self._finish=None
            raise
        finally:self._lock.release()
