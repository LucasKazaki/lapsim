"""Finite synthetic RWD LSD constitutive contract, not an admitted actuator.

Viscous-regularized torque-bias coupling; no static locking or hardware claim.
Only shaft algebra is implemented. Real motor/pack limiting, friction-limited
contact forces, wheel dynamics and RK-stage heat integration remain owner work.
"""
from dataclasses import dataclass
from math import isfinite,ulp,nextafter
from fractions import Fraction

TOPOLOGY='synthetic_viscous_regularized_torque_bias_rwd_lsd_r38'

ARITHMETIC_CONTRACT=('common-dyadic-transfer-accuracy-v2',1,1000000000000,1,100000000)


def finite(value,name):
    if type(value) not in (int,float) or not isfinite(value):
        raise ValueError(name+' must be an ordinary finite number')
    return float(value)


@dataclass(frozen=True)
class LsdAssumptions:
    preload_nm:float
    drive_bias_ratio:float
    coast_bias_ratio:float
    maximum_transfer_nm:float
    viscous_nm_per_rad_s:float

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value=finite(getattr(self,name),name)
            if value < (1.0 if name.endswith('bias_ratio') else 0.0):
                raise ValueError(name+' outside the explicit synthetic LSD domain')


def allocate_lsd(assumptions,*,requested_input_nm,minimum_input_nm,maximum_input_nm,
                 omega_left_rad_s,omega_right_rad_s):
    """Apply finite passive coupling to an upstream bounded carrier torque.

    T is the input AFTER the genuine motor's signed torque/power/pack limits.
    The explicit interval is data, never evidence of real resource admission.
    q has the sign of omegaR-omegaL; heat=q*(omegaR-omegaL) is nonnegative.
    All parameters are required; example values live only in synthetic tests.
    """
    if type(assumptions) is not LsdAssumptions:raise ValueError('Exact explicit LSD assumptions required')
    request=finite(requested_input_nm,'requested carrier torque')
    lo=finite(minimum_input_nm,'minimum available carrier torque')
    hi=finite(maximum_input_nm,'maximum available carrier torque')
    left=finite(omega_left_rad_s,'left wheel angular speed')
    right=finite(omega_right_rad_s,'right wheel angular speed')
    if not lo <= 0.0 <= hi:raise ValueError('Available signed motor interval must contain zero')
    torque=min(hi,max(lo,request))
    carrier=left/2.0+right/2.0
    input_power=finite(torque*carrier,'carrier mechanical power')
    mode='coast' if input_power<0.0 else 'drive'
    ratio=assumptions.coast_bias_ratio if mode=='coast' else assumptions.drive_bias_ratio
    fraction=(ratio-1.0)/(ratio+1.0)
    cap=min(assumptions.maximum_transfer_nm,
            finite(assumptions.preload_nm+fraction*abs(torque)/2.0,'differential transfer bound'))
    difference=finite(right-left,'relative wheel speed')
    viscous=finite(assumptions.viscous_nm_per_rad_s*difference,'viscous transfer demand')
    transfer=min(cap,max(-cap,viscous))
    # Use one common dyadic shaft grid. Carrier is rounded TOWARD ZERO to
    # twice that grid; transfer is rounded toward zero to the grid. Both
    # shafts are then exact representable multiples, with an exact carrier
    # sum and exact passive transfer. This avoids cancellation-dependent ULP
    # searches. The achieved carrier drives the electrical evaluation below.
    requested_transfer=transfer
    f=Fraction.from_float
    desired=f(transfer)
    magnitude=finite(abs(torque/2)+abs(transfer),'shaft representation scale')
    grid=2*f(ulp(magnitude))
    carrier_grid=2*grid
    achieved_exact=(1 if torque>=0 else -1)*(f(abs(torque))//carrier_grid)*carrier_grid
    achieved=finite(float(achieved_exact),'achieved carrier torque')
    actual_cap=min(assumptions.maximum_transfer_nm,
        finite(assumptions.preload_nm+fraction*abs(achieved)/2,'achieved differential bound'))
    transfer_target=min(f(abs(viscous)),f(actual_cap))
    q=(1 if viscous>=0 else -1)*(transfer_target//grid)*grid
    left_exact=achieved_exact/2+q
    right_exact=achieved_exact/2-q
    left_candidate=finite(float(left_exact),'left shaft torque')
    right_candidate=finite(float(right_exact),'right shaft torque')
    qfloat=finite(float(q),'achieved transfer')
    pair=None
    quantization_bound=8*max(f(ulp(left_candidate)),f(ulp(right_candidate)),f(ulp(torque)))
    conservative=(0<=achieved_exact<=f(torque) if torque>=0 else f(torque)<=achieved_exact<=0)
    if (f(achieved)==achieved_exact and f(left_candidate)==left_exact and f(right_candidate)==right_exact
            and f(qfloat)==q and conservative and abs(achieved_exact-f(torque))<=quantization_bound
            and desired*q>=0 and abs(q)<=abs(desired) and abs(q)<=f(actual_cap)):
        pair=(left_candidate,right_candidate,qfloat,achieved)
    # A zero coupling must preserve the exact open-differential input where its halves are representable.
    if desired==0 and 2*f(torque/2)==f(torque):
        pair=(torque/2,torque/2,0.,torque)
    if pair is None:
        error=ValueError('No representable conservative differential torque pair')
        error.lsd_operands=dict(requested_input_nm=request,minimum_input_nm=lo,maximum_input_nm=hi,
            omega_left_rad_s=left,omega_right_rad_s=right,limited_input_nm=torque,
            requested_transfer_nm=requested_transfer,transfer_bound_nm=cap,relative_speed_rad_s=difference,
            preload_nm=assumptions.preload_nm,drive_bias_ratio=assumptions.drive_bias_ratio,
            coast_bias_ratio=assumptions.coast_bias_ratio,maximum_transfer_nm=assumptions.maximum_transfer_nm,
            viscous_nm_per_rad_s=assumptions.viscous_nm_per_rad_s)
        raise error
    limited_torque=torque
    torque_left,torque_right,transfer,torque=pair
    base=f(torque)/2
    input_power=finite(torque*carrier,'achieved carrier mechanical power')
    mode='coast' if input_power<0 else 'drive'
    cap=min(assumptions.maximum_transfer_nm,assumptions.preload_nm+fraction*abs(torque)/2)
    error=abs(f(transfer)-desired)
    # Reject macroscopically unresolved transfer, including the retained
    # T=2**54,q=1.5 counterexample. The relative1e-8 envelope is explicit
    # arithmetic accuracy, not calibration; normal common-mode ULP error fits.
    # Absolute1e-12Nm is a stated arithmetic-error floor, not a hardware
    # preload, static lock, heat clip, or change to the achieved shaft pair.
    # At the selected <=2000Nm carrier /<=50Nm transfer envelope, the
    # common dyadic grid is at most2**-41Nm (<1e-12Nm). Retain the relative
    # accuracy test for macroscopically unresolved transfer at larger scales.
    tolerance=max(8*f(ulp(requested_transfer)),abs(desired)*Fraction(1,100000000),
                  Fraction(1,1000000000000))
    if error>tolerance:
        failure=ValueError('Differential transfer accuracy unavailable at supplied shaft scale')
        failure.lsd_operands=dict(requested_input_nm=request,minimum_input_nm=lo,maximum_input_nm=hi,
            omega_left_rad_s=left,omega_right_rad_s=right,limited_input_nm=limited_torque,
            achieved_input_nm=torque,left_torque_nm=torque_left,right_torque_nm=torque_right,
            requested_transfer_nm=requested_transfer,achieved_transfer_nm=transfer,
            transfer_error_nm=float(error),transfer_tolerance_nm=float(tolerance),
            shaft_grid_nm=float(grid),relative_speed_rad_s=difference,
            preload_nm=assumptions.preload_nm,drive_bias_ratio=assumptions.drive_bias_ratio,
            coast_bias_ratio=assumptions.coast_bias_ratio,maximum_transfer_nm=assumptions.maximum_transfer_nm,
            viscous_nm_per_rad_s=assumptions.viscous_nm_per_rad_s)
        raise failure
    qleft=f(torque_left)-base;qright=base-f(torque_right)
    if qleft!=f(transfer) or qright!=f(transfer):raise ValueError('Exact achieved transfer pair differs')
    exact_input=f(torque)*(f(left)+f(right))/2
    exact_output=f(torque_left)*f(left)+f(torque_right)*f(right)
    exact_heat=f(transfer)*(f(right)-f(left))
    if exact_heat<0:raise ValueError('Passive differential must not generate energy')
    heat=finite(float(exact_heat),'differential heat power')
    output_power=finite(torque_left*left+torque_right*right,'wheel shaft power')
    heat_tolerance=8*f(ulp(heat))
    if abs(exact_heat-f(heat))>heat_tolerance or abs(exact_input-exact_output-f(heat))>heat_tolerance:
        raise ValueError('Binary64 shaft work and achieved differential heat disagree at heat scale')
    residual=finite(float(exact_input-exact_output-f(heat)),'power identity residual')
    return {'topology':TOPOLOGY,'input_torque_nm':torque,'limited_input_torque_nm':limited_torque,
        'carrier_rounding_error_nm':float(f(torque)-f(limited_torque)),'left_torque_nm':torque_left,
        'right_torque_nm':torque_right,'transfer_nm':transfer,'requested_transfer_nm':requested_transfer,
        'transfer_rounding_error_nm':float(f(transfer)-f(requested_transfer)),'transfer_bound_nm':cap,
        'mode':mode,'input_power_w':input_power,'wheel_power_w':output_power,
        'differential_heat_w':heat,'power_identity_residual_w':residual,
        'achieved_tire_force_known':False,'zero_slip_guaranteed':False,
        'runtime_admission':False,'simulation_assumptions_only':True}

