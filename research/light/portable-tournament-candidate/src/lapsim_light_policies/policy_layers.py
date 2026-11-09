"""Seven explicit synthetic AWD/OFF recipes; all new recipes UNQUALIFIED.

Separate driver demand, allocation, yaw/slip layers and actuator constraints.
No policy changes steering, brake authority, plant energy or physical limits.
"""
from itertools import product
from math import cos,isfinite,sin,tan,sqrt

IDS=('equal_off','load_off','slip_off','feedforward_off','yaw_pi_off','yaw_slip_off','eco_neutral_off')
PARAMETERS={'slip_target':.1,'yaw_kp':20.,'yaw_ki':3.,'maximum_bias_nm':25.,'feedforward_nm_per_rad':40.,
    'feedforward_speed_reference_mps':9.,'integral_limit':1.,'allocator_period_s':.01}
def require(ok,message):
    if not ok:raise ValueError(message)
def finite(v):return type(v) in (int,float) and isfinite(v)
def four(v):require(type(v) in (tuple,list) and len(v)==4 and all(finite(x) for x in v),'Four finite wheel values');return tuple(v)
def clamp(v,lo,hi):return max(lo,min(hi,v)) # Request/integrator anti-windup bounds, never physical-state clipping.

def loss_allocation(total,moment,target,upper,quadratic,linear):
    """Exact-face enumeration of a strictly convex four-variable surrogate.

    81 fixed active-set candidates; two equality constraints and box bounds.
    This cost uses provisional motor losses, not measured maps or lap energy.
    """
    moment,upper,quadratic,linear=map(four,(moment,upper,quadratic,linear))
    require(finite(total) and 0<=total<=190 and finite(target) and all(a>0 for a in quadratic) and
        all(u>=0 for u in upper),'Finite convex allocation inputs')
    best=None;feasible=0
    for face in product((-1,0,1),repeat=4):
        free=[i for i in range(4) if face[i]==0];x=[upper[i] if face[i]==1 else 0. for i in range(4)]
        tr=total-sum(x);mr=target-sum(c*t for c,t in zip(moment,x))
        if not free:
            if abs(tr)>1e-9 or abs(mr)>1e-8:continue
        elif len(free)==1:
            i=free[0];x[i]=tr
            if abs(moment[i]*tr-mr)>1e-8:continue
        else:
            w={i:1/(2*quadratic[i]) for i in free}
            s0=sum(w.values());s1=sum(w[i]*moment[i] for i in free);s2=sum(w[i]*moment[i]**2 for i in free)
            z0=-tr-sum(w[i]*linear[i] for i in free);z1=-mr-sum(w[i]*linear[i]*moment[i] for i in free)
            determinant=s0*s2-s1*s1
            if abs(determinant)<=1e-12*max(1.,s0*s2):
                m0=moment[free[0]]
                if max(abs(moment[i]-m0) for i in free)>1e-9 or abs(mr-m0*tr)>1e-8:continue
                lam=z0/s0;mu=0.
            else:lam=(z0*s2-z1*s1)/determinant;mu=(s0*z1-s1*z0)/determinant
            for i in free:x[i]=-w[i]*(linear[i]+lam+mu*moment[i])
        if any(not finite(t) or t< -1e-9 or t>u+1e-9 for t,u in zip(x,upper)):continue
        raw=tuple(x);x=tuple(clamp(t,0.,u) for t,u in zip(x,upper))
        if abs(sum(x)-total)>1e-8 or abs(sum(c*t for c,t in zip(moment,x))-target)>1e-7:continue
        cost=sum(a*t*t+b*t for a,b,t in zip(quadratic,linear,x));feasible+=1
        if best is None or cost<best[0]:best=(cost,x,raw,face)
    require(best is not None,'No feasible energy allocation; no unrecorded fallback')
    return best[1],{'surrogate_cost_w':best[0],'raw_before_roundoff_bounds_nm':list(best[2]),'active_face':list(best[3]),
        'enumerated_faces':81,'feasible_faces':feasible,'drive_residual_nm':sum(best[1])-total,
        'drive_yaw_residual_nm':sum(c*t for c,t in zip(moment,best[1]))-target,
        'scope':'Strictly convex modeled copper+power surrogate only; not calibrated energy optimum'}

def allocate(policy,*,total_drive_nm,normal_loads_n,slip,steer,u_mps,yaw_rate_rad_s,integral,wheel_positions_m,
             wheel_radius_m,wheelbase_m,wheel_speeds_rad_s,mass_kg,nominal_mu,pack,dt=.01,freeze_integral=False):
    require(policy in IDS and dt==PARAMETERS['allocator_period_s'] and finite(total_drive_nm) and 0<=total_drive_nm<=190 and
        type(freeze_integral) is bool and
        all(finite(v) for v in (steer,u_mps,yaw_rate_rad_s,integral,wheel_radius_m,wheelbase_m)) and
        abs(steer)<=.4 and u_mps>=0 and wheel_radius_m>0 and wheelbase_m>0 and abs(integral)<=1,
        'Fixed AWD allocation domain and clock')
    loads=four(normal_loads_n);slip=four(slip);omega=four(wheel_speeds_rad_s)
    require(all(n>=0 for n in loads) and len(wheel_positions_m)==4,'Declared normal load/geometry estimates')
    original_integral=integral
    desired=[total_drive_nm/4]*4;before=tuple(desired);diagnostics={'policy':policy,'regen_enabled':False,
        'slip_binding':False,'yaw_changed':False,'reserve_binding':False,'load_changed':False,'energy_changed':False,
        'load_estimator':'Ideal model-based normal loads;not measured sensor estimates','parameters':dict(PARAMETERS)}
    if policy=='load_off':
        require(sum(loads)>0,'No supported contact load')
        desired=[total_drive_nm*n/sum(loads) for n in loads];diagnostics['load_changed']=max(abs(a-b) for a,b in zip(desired,before))>1e-9
    has_pi=policy in ('yaw_pi_off','yaw_slip_off')
    slip_on=policy in ('slip_off','yaw_slip_off')
    error=u_mps*tan(steer)/wheelbase_m-yaw_rate_rad_s
    candidate_integral=clamp(integral+dt*error,-1.,1.) if has_pi and not freeze_integral else integral
    raw_bias=0.
    if has_pi and total_drive_nm>0:raw_bias=PARAMETERS['yaw_kp']*error+PARAMETERS['yaw_ki']*candidate_integral
    if policy=='feedforward_off':
        raw_bias=PARAMETERS['feedforward_nm_per_rad']*steer*clamp(u_mps/PARAMETERS['feedforward_speed_reference_mps'],0.,2.)
    bias=clamp(raw_bias,-PARAMETERS['maximum_bias_nm'],PARAMETERS['maximum_bias_nm'])
    def yaw_split(bounded_bias):
        values=list(before)
        for left,right in ((0,1),(2,3)):
            axle=values[left]+values[right]
            values[right]=clamp(values[right]+bounded_bias/2,0.,axle);values[left]=axle-values[right]
        return values
    if policy=='feedforward_off' or has_pi:
        desired=yaw_split(bias)
        diagnostics['yaw_changed']=max(abs(a-b) for a,b in zip(desired,before))>1e-9
    # Conditional integration freezes windup on command/bias saturation, allows unwind.
    saturated=abs(raw_bias-bias)>1e-9 or any(t<=0 for t in desired) and total_drive_nm>0
    if has_pi and total_drive_nm>0 and (not saturated or error*raw_bias<0):integral=candidate_integral
    if has_pi and integral!=candidate_integral and total_drive_nm>0:
        raw_bias=PARAMETERS['yaw_kp']*error+PARAMETERS['yaw_ki']*integral
        bias=clamp(raw_bias,-PARAMETERS['maximum_bias_nm'],PARAMETERS['maximum_bias_nm']);desired=yaw_split(bias)
    if slip_on:
        factors=[min(1.,PARAMETERS['slip_target']/max(PARAMETERS['slip_target'],s)) for s in slip]
        preliminary_slip=any(abs(t-t*f)>1e-9 for t,f in zip(desired,factors))
        # Conservative conditional integration: if the slip layer sheds any
        # requested torque, preserve the previous PI state. This avoids
        # accumulating yaw demand while the later layer cannot deliver it;
        # it can also defer unwinding during persistent slip. It is not a
        # back-calculated delivered-yaw controller.
        if has_pi and preliminary_slip:
            integral=original_integral
            raw_bias=PARAMETERS['yaw_kp']*error+PARAMETERS['yaw_ki']*integral
            bias=clamp(raw_bias,-PARAMETERS['maximum_bias_nm'],PARAMETERS['maximum_bias_nm']);desired=yaw_split(bias)
            diagnostics['yaw_integral_frozen_by_slip']=True
        before_slip=tuple(desired);desired=[t*f for t,f in zip(desired,factors)]
        diagnostics['slip_binding']=any(abs(a-b)>1e-9 for a,b in zip(before_slip,desired))
    if policy=='feedforward_off' or has_pi:
        # Report the actual pre-slip yaw command using the committed integral.
        yaw_base=yaw_split(bias)
        diagnostics['yaw_changed']=max(abs(a-b) for a,b in zip(yaw_base,before))>1e-9
    diagnostics.update(yaw_error_rad_s=error,yaw_bias_requested_nm=raw_bias,yaw_bias_bounded_nm=bias,
        yaw_integral_frozen=has_pi and (freeze_integral or integral!=candidate_integral),
        yaw_integral_frozen_external=has_pi and freeze_integral)
    if policy=='eco_neutral_off' and total_drive_nm>0:
        # This convex surrogate matches only actuation's propulsive power
        # branch. A negative wheel speed with positive torque switches the
        # real electrical conversion branches; do not optimize that different
        # piecewise objective or silently substitute a recipe.
        require(all(w >= 0 for w in omega),
                'Eco surrogate requires nonnegative wheel speeds; signed-power branch unsupported')
        # Preserve this recipe's demanded total and direct drive-yaw moment.
        # With identical motor maps/speeds, equal split may already minimize loss.
        angles=(steer,steer,0.,0.);moment=[]
        for (x,y),angle in zip(wheel_positions_m,angles):moment.append((x*sin(angle)-y*cos(angle))/wheel_radius_m)
        target=sum(c*t for c,t in zip(moment,desired));total=sum(desired)
        require(finite(mass_kg) and mass_kg>0 and finite(nominal_mu) and nominal_mu>0,'Declared nominal tire-capacity estimate')
        lateral=abs(u_mps*yaw_rate_rad_s)*mass_kg/4
        upper=[min(190.,wheel_radius_m*sqrt(max(0.,(.85*nominal_mu*n)**2-lateral**2))) for n in loads]
        diagnostics['energy_capacity_model']='Nominal-mu combined-slip reserve estimate;not measured grip or actual tire-force oracle'
        gain=pack.gear_ratio*pack.gear_efficiency*pack.torque_constant_nm_per_a
        require(gain>0 and pack.equivalent_copper_resistance_ohm>0,'Positive declared synthetic copper-loss coefficient')
        quadratic=[pack.equivalent_copper_resistance_ohm/(gain*gain*pack.inverter_efficiency)]*4
        linear=[w/(pack.gear_efficiency*pack.motor_conversion_efficiency*pack.inverter_efficiency) for w in omega]
        chosen,audit=loss_allocation(total,moment,target,upper,quadratic,linear)
        diagnostics['energy_changed']=max(abs(a-b) for a,b in zip(chosen,desired))>1e-9
        diagnostics['energy_surrogate']=audit;desired=list(chosen)
    require(all(finite(t) and t>=0 for t in desired) and sum(desired)<=total_drive_nm+1e-8,'No synthesized drive demand or regen')
    diagnostics['requested_total_nm']=total_drive_nm;diagnostics['proposed_total_nm']=sum(desired)
    diagnostics['force_demand_shed_nm']=total_drive_nm-sum(desired)
    return tuple(desired),integral,diagnostics
