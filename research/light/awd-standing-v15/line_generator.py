"""Explicit existing-dependency SciPy/SLSQP line proposal, UNRUN.

No imports of numerical dependencies, solve, model, I/O or execution on import.
This is an explicitly named backend, not a fallback claiming TUM/IQP results.
"""
from math import atan2,cos,hypot,isfinite,sin,sqrt,tan
from time import monotonic
import json
import racing_geometry as geometry

PARAMETERS={'stations':64,'maximum_iterations':48,'maximum_objective_calls':4096,
 'work_wall_s':60.,'solver_reserve_s':15.,'clearance_intervals':8192,'clearance_depth':10,
 'curvature_intervals':8192,'curvature_depth':10,'curvature_rounding_per_m':1e-12,
 'topology_max_pairs':200000,'topology_max_bucket_entries':100000,'topology_max_pair_visits':1000000,'topology_rounding_m':1e-9,
 'vehicle_width_m':1.4,'front_extent_m':1.,'rear_extent_m':1.,'safety_margin_m':.2,
 'map_uncertainty_m':.1,'tracking_allowance_m':.1,'polyline_error_m':.001,
 'wheelbase_m':1.6,'maximum_steering_rad':.4,'minimum_sample_spacing_m':.05,'maximum_sample_spacing_m':.1,
 'declared_input_scope':'Synthetic full rectangle/uncertainty assumptions;not measured team body or survey'}

SELECTION_FRACTIONS=(1.,.5,.25,.125)

def sampled_curvature_within(values,limit):
    values=tuple(float(value) for value in values)
    geometry.require(bool(values) and isfinite(float(limit)) and float(limit)>=0 and
        all(isfinite(value) for value in values),'Finite sampled curvature required')
    return max(abs(value) for value in values)<=float(limit)

def padded_clearance_ok(slack):
    slack=float(slack)
    geometry.require(isfinite(slack),'Finite padded footprint clearance required')
    return slack>=0.

def select_scaled_offset(values,bounds,probe):
    """First predeclared nonzero, bounded vector passing a caller's prefilter.

    A passing prefilter is not final clearance. Exceptions (including a
    deadline) propagate; the selected vector still needs every full screen.
    """
    values=tuple(float(value) for value in values)
    geometry.require(len(values)==len(bounds) and len(values)>1 and callable(probe) and
        all(isfinite(value) for value in values) and any(value!=0. for value in values),
        'Nonzero finite solver vector required')
    geometry.require(all(isfinite(float(lo)) and isfinite(float(hi)) and
        float(lo)<=0.<=float(hi) and float(lo)<=value<=float(hi)
        for value,(lo,hi) in zip(values,bounds)) and tuple(bounds[0])==(0.,0.),
        'Original solver bounds and fixed gate required')
    tried=[]
    for fraction in SELECTION_FRACTIONS:
        candidate=tuple(value*fraction for value in values)
        tried.append(fraction)
        if not any(value!=0. for value in candidate):continue
        if not all(float(lo)<=value<=float(hi) for value,(lo,hi) in zip(candidate,bounds)):continue
        accepted=probe(candidate)
        geometry.require(type(accepted) is bool,'Prefilter must return a Boolean')
        if accepted:return candidate,fraction,tuple(tried)
    raise ValueError('No nonzero scaled candidate passed the fixed prefilter')


def require_solver_success(result,calls,finite_x,bounds=None):
    """Return a nonconverged proposal only for a bounded status-9 iterate.

    That return means only that solver offsets are within their declared
    bounds. All sampled/continuous geometry checks remain mandatory before
    any artifact is written, and dynamic replay remains unqualified.
    """
    if bool(getattr(result,'success',False)) and finite_x is True:return
    def number(name,integer=False):
        try:
            value=float(getattr(result,name,None))
            if not isfinite(value) or (integer and (value!=int(value) or abs(value)>10**9)):return None
            return int(value) if integer else value
        except (TypeError,ValueError,OverflowError):return None
    message=str(getattr(result,'message','unavailable'))
    diagnostic={'success':bool(getattr(result,'success',False)),'finite_x':finite_x if type(finite_x) is bool else None,
        'status':number('status',True),'message':message[:256],'message_truncated':len(message)>256,
        'nit':number('nit',True),'nfev':number('nfev',True),'njev':number('njev',True),
        'objective':number('fun'),'objective_calls':calls}
    if getattr(result,'success',None) is not None and not bool(result.success) and diagnostic['status']==9 and \
            finite_x is True and diagnostic['objective'] is not None and bounds is not None:
        try:
            values=[float(value) for value in result.x]
            inside=len(values)==len(bounds) and all(isfinite(value) and float(low)<=value<=float(high)
                for value,(low,high) in zip(values,bounds))
        except (AttributeError,TypeError,ValueError,OverflowError):inside=False
        if inside:
            return {**diagnostic,'disposition':'NONCONVERGED_BOUNDS_ONLY_PENDING_GEOMETRY'}
    raise ValueError('Bounded line solver rejected result; diagnostic: '+json.dumps(diagnostic,ensure_ascii=True,allow_nan=False))

def generate(raw_yaml,bundle):
    """One later owned-worker call only. Caller enforces hard deadline/lease.

    Returns a provisionally screened raw proposal; actual driver replay and
    rigorous floating-point roundoff verification remain UNRUN. No campaign
    eligibility or minimum-time guarantee is granted.
    """
    # The enclosing owned command must also enforce an outer hard deadline;
    # a cooperative check cannot interrupt an import that hangs internally.
    start=monotonic()
    import numpy as np
    from scipy.interpolate import CubicSpline
    from scipy.optimize import minimize
    import scipy,sys
    from pathlib import Path
    from hashlib import sha256
    here=Path(__file__).resolve().parent
    geometry.require(Path(geometry.__file__).resolve()==here/'racing_geometry.py','Fixed producer geometry helper')
    producer_sources={str(here/name):sha256((here/name).read_bytes()).hexdigest() for name in ('line_generator.py','racing_geometry.py')}
    backend={'python_executable':sys.executable,'python_version':sys.version,'numpy_version':np.__version__,
        'scipy_version':scipy.__version__,'entry_source_sha256':{str(Path(module.__file__).resolve()):sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (np,scipy,sys.modules[CubicSpline.__module__],sys.modules[minimize.__module__])},
        'scope':'Observed backend entry sources/versions;complete compiled dependency lock requires independent producer audit'}
    p=dict(PARAMETERS);calls=0
    def deadline(reserve=0):
        geometry.require(monotonic()-start+reserve<p['work_wall_s'],'Line generation whole-work cap reached')
    deadline()
    frame=geometry.reconstruct_frame(raw_yaml,bundle['geometry']);deadline()
    source=bundle['geometry'];length=source['distance_m'][-1];n=p['stations']
    stations=np.linspace(0.,length,n+1)
    base=np.column_stack((np.interp(stations,source['distance_m'],source['x_m']),np.interp(stations,source['distance_m'],source['y_m'])))
    # Preserve the immutable source and close this separate periodic-fit view.
    base[-1]=base[0]
    reference=CubicSpline(stations,base,bc_type='periodic');tangent=reference(stations[:-1],1)
    speed=np.linalg.norm(tangent,axis=1);geometry.require(np.all(speed>1e-8),'Degenerate spline reference')
    normals=np.column_stack((tangent[:,1],-tangent[:,0]))/speed[:,None]
    widths=geometry.widths_on_normals(frame,base[:-1].tolist(),normals.tolist());deadline()
    half=.5*p['vehicle_width_m']+p['safety_margin_m']+p['map_uncertainty_m']+p['tracking_allowance_m']+p['polyline_error_m']
    lower=-np.asarray(widths['left_width_m'])+half;upper=np.asarray(widths['right_width_m'])-half
    geometry.require(np.all(lower<upper) and np.all(lower<=0) and np.all(upper>=0),'Reference lacks full declared corridor allowance')
    bounds=list(zip(lower,upper));bounds[0]=(0.,0.) # fixed physical source start/finish gate
    dense=np.linspace(0.,length,4*n,endpoint=False)
    kappa_bound=.95*tan(p['maximum_steering_rad'])/p['wheelbase_m']
    def curve(alpha):
        xy=base[:-1]+normals*np.asarray(alpha)[:,None]
        return CubicSpline(stations,np.vstack((xy,xy[0])),bc_type='periodic')
    def curvature(spline):
        v=spline(dense,1);a=spline(dense,2);v2=np.sum(v*v,axis=1)
        geometry.require(np.all(v2>1e-8),'Degenerate candidate tangent')
        return (v[:,0]*a[:,1]-v[:,1]*a[:,0])/v2**1.5,np.sqrt(v2)
    def objective(alpha):
        nonlocal calls
        calls+=1;geometry.require(calls<=p['maximum_objective_calls'],'Finite objective-call cap');deadline(p['solver_reserve_s'])
        k,ds=curvature(curve(alpha))
        return float(np.mean(k*k*ds)+.01*np.mean(ds))
    def constraints(alpha):
        deadline(p['solver_reserve_s']);k,_=curvature(curve(alpha));return kappa_bound-np.abs(k)
    baseline_objective=objective(np.zeros(n))
    result=minimize(objective,np.zeros(n),method='SLSQP',bounds=bounds,
        constraints=[{'type':'ineq','fun':constraints}],options={'maxiter':p['maximum_iterations'],'ftol':1e-8,'disp':False,'workers':1})
    deadline()
    try:finite_x=bool(np.asarray(result.x).shape==(len(bounds),) and np.isfinite(result.x).all())
    except (AttributeError,TypeError,ValueError):finite_x=None
    partial= require_solver_success(result,calls,finite_x,bounds=bounds)
    # Apply the exact original optimizer bounds, including (0,0) at the
    # physical start, to both converged and provisional iterates; never clip.
    geometry.require(len(result.x)==len(bounds) and all(float(low)<=float(value)<=float(high)
        for value,(low,high) in zip(result.x,bounds)),'Solver iterate exceeds declared offset bounds')
    margin=p['safety_margin_m']+p['map_uncertainty_m']+p['tracking_allowance_m']+p['polyline_error_m']
    def prefilter(candidate):
        deadline(p['solver_reserve_s'])
        proposed=curve(candidate);k,_=curvature(proposed)
        if not sampled_curvature_within(k,kappa_bound+1e-8):return False
        for a,b in zip(stations,stations[1:]):
            deadline(p['solver_reserve_s'])
            mid=(a+b)/2;xy=proposed(mid);v=proposed(mid,1)
            slack=geometry.footprint_clearance(frame,(float(xy[0]),float(xy[1]),atan2(v[1],v[0])),
                front_m=p['front_extent_m'],rear_m=p['rear_extent_m'],width_m=p['vehicle_width_m'],margin_m=margin)
            if not padded_clearance_ok(slack):return False
        return True
    selected,fraction,tried=select_scaled_offset(result.x,bounds,prefilter)
    selected_objective=objective(selected) # counted; retains the geometry time reserve
    spline=curve(selected);k,_=curvature(spline)
    geometry.require(np.max(np.abs(k))<=kappa_bound+1e-8,'Candidate exceeds declared geometric steering bound')
    # The solver constraints sample256 points only. Independently bound the
    # complete cubic cells and reject if refinement cannot establish the limit.
    curvature_intervals=0;maximum_curvature_bound=0.
    def certify_curvature(a,b,depth):
        nonlocal curvature_intervals,maximum_curvature_bound
        curvature_intervals+=1;deadline()
        geometry.require(curvature_intervals<=p['curvature_intervals'],'Continuous curvature interval cap')
        mid=(a+b)/2;half=(b-a)/2
        derivatives=[tuple(float(x) for x in spline(mid,n)) for n in (1,2,3)]
        bound=geometry.cubic_curvature_upper_bound(*derivatives,half)
        if bound+p['curvature_rounding_per_m']<=kappa_bound:
            maximum_curvature_bound=max(maximum_curvature_bound,bound);return
        geometry.require(depth<p['curvature_depth'],'Continuous curvature bound unresolved;no sampled-only acceptance')
        certify_curvature(a,mid,depth+1);certify_curvature(mid,b,depth+1)
    for a,b in zip(stations,stations[1:]):certify_curvature(float(a),float(b),0)
    coeff=spline.c # local powers (t-station_i), not upstream normalized local-t coefficients
    interval_count=0;minimum_slack=float('inf');sampled=[];sampled_stations=[]
    radius=hypot(max(p['front_extent_m'],p['rear_extent_m']),p['vehicle_width_m']/2)
    def certify(a,b,depth):
        nonlocal interval_count,minimum_slack
        interval_count+=1;deadline();geometry.require(interval_count<=p['clearance_intervals'],'Continuous clearance interval cap')
        mid=(a+b)/2;delta=(b-a)/2;xy=spline(mid);v=spline(mid,1)
        acceleration=max(float(np.linalg.norm(spline(a,2))),float(np.linalg.norm(spline(b,2))))
        # Each call remains within one cubic cell: acceleration is affine,
        # so its norm maximum occurs at an interval endpoint.
        vmin=float(np.linalg.norm(v))-acceleration*delta
        vmax=float(np.linalg.norm(v))+acceleration*delta
        slack=geometry.footprint_clearance(frame,(float(xy[0]),float(xy[1]),atan2(v[1],v[0])),
            front_m=p['front_extent_m'],rear_m=p['rear_extent_m'],width_m=p['vehicle_width_m'],margin_m=margin)
        geometry.require(slack>=0,'Actual candidate rectangle violates approximate source corridor')
        displacement=float('inf') if vmin<=1e-9 else (vmax+radius*acceleration/vmin)*delta
        if slack>=displacement:
            minimum_slack=min(minimum_slack,slack-displacement)
            return
        geometry.require(depth<p['clearance_depth'],'Continuous footprint clearance unresolved;no nodal-only acceptance')
        certify(a,mid,depth+1);certify(mid,b,depth+1)
    for a,b in zip(stations,stations[1:]):certify(float(a),float(b),0)
    # Independently bound the polyline representation error by |f''|*h^2/8.
    def sample(a,b,depth=0):
        deadline();geometry.require(depth<=16 and len(sampled)<=5000,'Finite reference sampling cap')
        pa,pb=spline(a),spline(b);acc=max(float(np.linalg.norm(spline(a,2))),float(np.linalg.norm(spline(b,2))))
        if acc*(b-a)**2/8>p['polyline_error_m'] or np.linalg.norm(pb-pa)>p['maximum_sample_spacing_m']:
            sample(a,(a+b)/2,depth+1);sample((a+b)/2,b,depth+1)
        else:
            geometry.require(len(sampled)<5000,'Finite reference sampling cap')
            sampled_stations.append(float(a));sampled.append([float(pa[0]),float(pa[1])])
    for a,b in zip(stations,stations[1:]):sample(float(a),float(b))
    # Every accepted cubic subarc is within the declared error of its chord.
    # Nonadjacent chords must be separated by more than twice that error.
    # At each shared endpoint, including the seam, prove strictly positive
    # derivative projection along the common tangent on both full subarcs.
    topology=geometry.verify_nonlocal_polyline_clearance(sampled,p['polyline_error_m'],
        rounding_m=p['topology_rounding_m'],max_pairs=p['topology_max_pairs'],
        max_bucket_entries=p['topology_max_bucket_entries'],max_pair_visits=p['topology_max_pair_visits'],deadline_callback=deadline)
    station_edges=sampled_stations+[float(length)]
    velocities=[tuple(float(x) for x in spline(s,1)) for s in station_edges]
    accelerations=[tuple(float(x) for x in spline(s,2)) for s in station_edges]
    adjacent=geometry.verify_adjacent_tangent_projection(station_edges,velocities,accelerations,deadline_callback=deadline)
    xy=sampled+[sampled[0][:]];distance=[0.]
    for a,b in zip(xy,xy[1:]):
        step=hypot(b[0]-a[0],b[1]-a[1]);geometry.require(step>1e-9,'Collapsed sampled path');distance.append(distance[-1]+step)
    # Store curvature sampled at the actual candidate station intervals;
    # the driver explicitly declares sampled_polyline preview semantics.
    headings=[atan2(b[1]-a[1],b[0]-a[0]) for a,b in zip(xy,xy[1:])]
    curv=[]
    from math import remainder,pi
    for i,h in enumerate(headings):
        ds=.5*((distance[i+1]-distance[i])+(distance[i]-distance[i-1] if i else distance[-1]-distance[-2]))
        curv.append(remainder(h-headings[i-1],2*pi)/ds)
    deadline()
    optimization=({'converged':False,'solver_converged':False,'status':9,'disposition':'NONCONVERGED_GEOMETRY_SCREENED',
        'message':partial['message'],'message_truncated':partial['message_truncated'],
        'nfev':partial['nfev'],'njev':partial['njev'],'optimality_claimed':False}
        if partial is not None else {'converged':fraction==1.,'solver_converged':True,'status':int(result.status),
        'disposition':'CONVERGED_GEOMETRY_SCREENED' if fraction==1. else 'SCALED_FROM_CONVERGED_GEOMETRY_SCREENED',
        'message':str(result.message)[:256],'message_truncated':len(str(result.message))>256,
        'nfev':int(result.nfev),'njev':int(result.njev),'optimality_claimed':False})
    optimization['selection']={'fractions_tried':list(tried),'selected_fraction':fraction,
        'maximum_absolute_offset_m':max(abs(value) for value in selected),
        'original_solver_objective':float(result.fun),'selected_objective':selected_objective,
        'scope':'First fixed nonzero scale passing sampled curvature and padded midpoints;full geometric checks follow'}
    artifact={'schema':'ev.awd-fsi-frozen-racing-reference.v6','status':'GEOMETRY_SCREENED_DYNAMIC_REPLAY_UNRUN',
        'method':'explicit_scipy_periodic_minimum_curvature_slsqp_scaled_v5','minimum_time_proven':False,
        'source_geometry_sha256':geometry.SOURCE_GEOMETRY_SHA,'source_bundle_payload_sha256':geometry.digest(bundle),
        'raw_boundary_sha256':sha256(raw_yaml).hexdigest(),'producer_source_sha256':producer_sources,
        'numerical_backend':backend,'numerical_backend_fingerprint_sha256':geometry.digest(backend),
        'frame':frame,'frame_sha256':geometry.digest(frame),'parameters':p,'width_mapping':widths,
        'geometry':{'model':'sampled_polyline','closed':True,'distance_m':distance,'x_m':[v[0] for v in xy],
            'y_m':[v[1] for v in xy],'curvature_per_m':curv},
        'reference_geometry_sha256':None,'source_course_length_m':length,'reference_length_m':distance[-1],
        'gate':{'origin_xy_m':[0.,0.],'forward_unit':[1.,0.],'finite_half_width_m':3.,'scope':'Source physical gate;not moved with reference distance'},
        'coefficients':{'basis':'scipy_local_station_power3_to0','knots_m':stations.tolist(),'xy_coefficients':coeff.tolist()},
        'clearance':{'floating_point_continuous_rectangle_screen':True,'intervals':interval_count,'minimum_bound_m':minimum_slack,
            'rigorous_roundoff_proof':False,
            'polyline_error_bound_m':p['polyline_error_m'],'actual_vehicle_replay_or_swept_trajectory_qualified':False},
        'geometric_curvature':{'floating_point_bound_per_m':maximum_curvature_bound,'limit_per_m':kappa_bound,
            'intervals':curvature_intervals,'rigorous_roundoff_proof':False,
            'scope':'Untested floating-point cubic screen only;not steering-rate or vehicle dynamics'},
        'topology':{**topology,'adjacent_tangent_projection_screen':adjacent,'rigorous_roundoff_proof':False,
            'scope':'Untested floating-point simple-loop screen;not actual driven trajectory'},
        'optimization':optimization,'baseline_objective':baseline_objective,'candidate_objective':selected_objective,'iterations':int(result.nit),
        'objective_calls':calls,'work_wall_s':monotonic()-start,'role':'development','heldout_used':False,
        'shared_across_techniques':True,'awards':None}
    artifact['reference_geometry_sha256']=geometry.digest(artifact['geometry'])
    geometry.require(len(geometry.canonical(artifact).encode())<=2*1024*1024,'Fixed2MiB line artifact bound')
    return artifact
