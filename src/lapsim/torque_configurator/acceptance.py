"""Controller-boundary observations; no second controller or plant is implemented."""
from dataclasses import asdict
from math import isfinite,ceil

from lapsim.dynamics.actuation import SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID,TOPOLOGY_ID
from lapsim.dynamics.powered_planar import MAX_ALLOCATED_POWERED_WORK


def work_plan(profile,duration_ms,*,ten_lap=False):
    if type(ten_lap) is not bool:raise ValueError('Ten-lap allocation must be Boolean')
    maximum=600000 if ten_lap else 60000
    work_maximum=10*MAX_ALLOCATED_POWERED_WORK if ten_lap else MAX_ALLOCATED_POWERED_WORK
    """Nominal RK cost only; adaptive braking work can still exhaust the bound."""
    if type(duration_ms) is not int or not 100<=duration_ms<=maximum or duration_ms%10:
        raise ValueError('Work plan requires 100-60000 integer ms on the 10 ms clock')
    step=min(profile.vehicle.integration_step_limit_s,profile.actuation.actuator_time_constant_s/4)
    per_interval=ceil(.01/step)
    nominal=duration_ms//10*per_interval
    return {'maximum_duration_s':duration_ms/1000,'maximum_controller_observations':duration_ms//10+1,
        'maximum_cumulative_trials_and_stop_events':work_maximum,
        'effective_maximum_plant_step_s':step,'nominal_trials_per_controller_interval':per_interval,
        'nominal_trials_at_time_limit':nominal,'additional_trial_and_stop_capacity':work_maximum-nominal,
        'scope':'Nominal held intervals; adaptive brake-stop work consumes the same cumulative bound; completion is not guaranteed'}


class BoundaryAudit:
    def __init__(self,profile):
        self.profile=profile
        self.previous_command=(0.,)*4
        self.observations=0
        self.braking_ticks=0
        self.residual_drive_braking_ticks=0
        self.failures=set()
        self.peaks={name:0. for name in ('pack_power_w','pack_current_a','motor_current_a',
            'actuator_rate_nm_per_s','friction_nm','residual_drive_during_braking_nm')}

    def observe(self,frame,output,actual,rate,brakes,shortfall):
        pack=self.profile.actuation
        experimental=self.profile.to_dict()['schema']=='lapsim.torque-profile.v2'
        single=pack.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)
        slew=pack.actuator_slew_nm_per_s/(2 if single else 1)
        guard_slew=8000. if pack.topology_id==TOPOLOGY_ID else min(8000.,slew)
        command=output['controller']['command_nm']
        failures=set()
        def check(ok,name):
            if not ok:failures.add(name)
        def bounded(value,low,high,name):
            check(isfinite(value) and low-1e-6<=value<=high+1e-6,name)
        energy=frame['pack_energy_j']
        bounded(energy,0.,pack.pack_capacity_j,'pack_energy')
        upper=min(pack.pack_discharge_power_limit_w,pack.pack_voltage_v*pack.pack_discharge_current_limit_a,energy/.01)
        lower=-min(pack.pack_charge_power_limit_w,pack.pack_voltage_v*pack.pack_charge_current_limit_a,(pack.pack_capacity_j-energy)/.01)
        for electrical in (output['limited'],asdict(actual)):
            bounded(electrical['pack_power_w'],lower,upper,'shared_pack_power_current_energy')
            check(abs(electrical['pack_current_a']*pack.pack_voltage_v-electrical['pack_power_w'])<1e-6,'pack_units')
            for current,torque,speed in zip(electrical['motor_currents_a'],electrical['motor_torques_nm'],electrical['motor_speeds_rad_s']):
                bounded(abs(current),0.,min(pack.motor_current_limit_a,pack.inverter_current_limit_a),'motor_current')
                cap=min(pack.motor_peak_torque_nm,pack.torque_constant_nm_per_a*min(pack.motor_current_limit_a,pack.inverter_current_limit_a))
                if speed>pack.motor_base_speed_rad_s:cap=min(cap,pack.motor_peak_torque_nm*pack.motor_base_speed_rad_s/speed)
                if speed>=pack.motor_maximum_speed_rad_s:cap=0.
                bounded(abs(torque),0.,cap,'motor_torque_speed')
            torques=electrical['wheel_torques_nm']
            if not experimental:check(all(t>=-1e-6 for t in torques),'propulsive_only')
            if single:
                check(abs(torques[2]-torques[3])<1e-6 and torques[0]==torques[1]==0,'single_motor_equal_axle')
                check(all(electrical['motor_currents_a'][i]==0 for i in (0,1,3)),'single_shared_motor_accounting')
            elif pack.topology_id==TOPOLOGY_ID:
                check(torques[0]==torques[1]==0,'rwd_front_inhibit')
        for now,previous in zip(command,self.previous_command):
            bounded(now,-1000. if experimental else 0.,1000.,'guard_signed_bounds' if experimental else 'guard_nonnegative')
            if output['controller']['command_allowed'] or not experimental:check(now-previous<=guard_slew*.01+1e-6,'guard_rise_slew')
        for value in rate[10:14]:bounded(abs(value),0.,slew,'plant_actuator_slew')
        if single:check(abs(rate[12]-rate[13])<1e-6,'single_shared_slew')
        capacity=self.profile.policy['maximum_friction_brake_nm']
        for value in brakes:bounded(value,0.,capacity,'friction_capacity')
        if frame['brake_fraction']>0:
            self.braking_ticks+=1
            check(all(t<=0 for t in command) if experimental else all(t==0 for t in command),'brake_propulsion_inhibit')
            residual=sum(max(0.,t) for t in actual.wheel_torques_nm)
            if residual>1e-6:self.residual_drive_braking_ticks+=1
            self.peaks['residual_drive_during_braking_nm']=max(self.peaks['residual_drive_during_braking_nm'],residual)
            check(sum(brakes)+sum(max(0.,-v) for v in actual.wheel_torques_nm)-residual+shortfall>=4*capacity*frame['brake_fraction']-1e-6,'brake_compensation')
        bounded(shortfall,0.,1e-6,'brake_shortfall')
        for name,value in (('pack_power_w',abs(actual.pack_power_w)),('pack_current_a',abs(actual.pack_current_a)),
            ('motor_current_a',max(map(abs,actual.motor_currents_a))),('actuator_rate_nm_per_s',max(map(abs,rate[10:14]))),
            ('friction_nm',max(brakes))):self.peaks[name]=max(self.peaks[name],value)
        self.previous_command=tuple(command)
        self.observations+=1
        self.failures.update(failures)
        return sorted(failures)

    def finish(self,record):
        metrics=record['metrics']
        lap=metrics['lap_time_s']
        checks={'completed_course':record['status']=='completed' and metrics['completion_fraction']==1,
                'finite_positive_lap':type(lap) in (float,int) and isfinite(lap) and lap>0,
                'no_rollout_violations':not record['violations'],
                'energy_ledger':isfinite(metrics['energy_residual_j']) and abs(metrics['energy_residual_j'])<.5,
                'all_recorded_frames_audited':self.observations==len(record['configuration']['frames']),
                'boundary_constraints':not self.failures,'braking_observed':self.braking_ticks>0}
        if record['case'].get('laps')==10:checks['ten_completed_laps']=record['round']['completed_laps']==10
        return {'schema':'lapsim.configured-full-lap-acceptance.v1','passed':all(checks.values()),
                'checks':checks,'boundary_failures':sorted(self.failures),'observations':self.observations,
                'braking_ticks':self.braking_ticks,'residual_drive_braking_ticks':self.residual_drive_braking_ticks,
                'peaks':self.peaks,'scope':'10 ms controller-boundary observations, not independent RK-stage or physical validation'}
