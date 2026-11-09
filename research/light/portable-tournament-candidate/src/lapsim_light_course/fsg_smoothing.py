"""Separate fixed periodic-cubic FSG proposal and bounded geometric screens.

One shared cyclic control basis defines the periodic C2 mathematical model.
Production, coefficient evaluation and screening use the standard library. No original
producer authentication, gate/mission, actual-car or native authority is added.
"""
from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
import json
from math import atan2, hypot, isfinite, remainder, pi, tan
from time import monotonic

from . import _fsi_geometry as g, racing_geometry as rg
from .course import construct_fsg_course
from .fsg_reference import require, point, _unique, _nonfinite
from .fsg_source_arcs import _steering_proxy

PROPOSAL_SCHEMA = 'lapsim.fsg-fixed-periodic-bspline-proposal.v1'
SCHEMA = 'lapsim.fsg-fixed-periodic-bspline-candidate.v1'
MAX_BYTES = 2*1024*1024
JOIN_TOLERANCE = 1e-9
PARAMETERS = {
    'stations':64,'front_m':1.,'rear_m':1.,'width_m':1.4,
    'safety_margin_m':.2,'map_uncertainty_m':.1,'tracking_allowance_m':.1,
    'wheelbase_m':1.6,'maximum_steering_rad':.4,'curvature_limit_fraction':.95,
    'polyline_error_m':.001,'maximum_sample_spacing_m':.1,
    'minimum_sample_spacing_m':.05,'maximum_samples':5000,
    'maximum_curvature_intervals':8192,'maximum_clearance_intervals':8192,
    'maximum_depth':10,'maximum_sampling_depth':16,
    'rounding_m':1e-9,'curvature_rounding_per_m':1e-12,
    'maximum_topology_pairs':200000,'maximum_bucket_entries':100000,
    'maximum_pair_visits':1000000}


class SplineScreenFailure(ValueError):
    """A rejected/unresolved proposal is retained without a success packet."""
    def __init__(self,message,proposal_raw):
        super().__init__(message)
        self.proposal_raw = proposal_raw


class _Budget:
    def __init__(self,wall_s):
        require(type(wall_s) in (int,float) and isfinite(wall_s) and 0 < wall_s <= 40,
            'Explicit positive geometry window no greater than40seconds required')
        self.start = monotonic()
        self.wall_s = wall_s

    def check(self):
        require(monotonic()-self.start < self.wall_s,'Finite smoothing geometry deadline exhausted')


def _controls_to_coefficients(controls):
    """Derived float power view; shared cyclic controls define the actual model.

    Uniform cubic basis weights are (1-t)^3, 3t^3-6t^2+4,
    -3t^3+3t^2+3t+1, t^3, each divided by6. Cyclic index reuse makes
    position/first/second derivatives join algebraically, including the seam.
    Derived rounded coefficients are not independent defining input pieces.
    """
    require(type(controls) in (list,tuple) and 4 <= len(controls) <= 64,
        'Bounded shared periodic controls required')
    points = tuple(point(v) for v in controls)
    rows = [[],[],[],[]]
    for i,b in enumerate(points):
        a,c,d = points[i-1],points[(i+1)%len(points)],points[(i+2)%len(points)]
        rows[0].append([(-a[j]+3*b[j]-3*c[j]+d[j])/6 for j in (0,1)])
        rows[1].append([(3*a[j]-6*b[j]+3*c[j])/6 for j in (0,1)])
        rows[2].append([(-3*a[j]+3*c[j])/6 for j in (0,1)])
        rows[3].append([(a[j]+4*b[j]+c[j])/6 for j in (0,1)])
    return rows


def evaluate_periodic_controls(controls,parameter,derivative=0):
    """Evaluate the defining cyclic basis, parameterized by source-sample index.

    Derivative3 takes the right-hand cubic at an integer knot. This geometry
    evaluation supplies no source consistency, rate-in-time or admission.
    """
    require(type(controls) in (list,tuple) and 4 <= len(controls) <= 64 and
        type(parameter) in (int,float) and isfinite(parameter) and abs(parameter) <= 1e6 and
        type(derivative) is int and 0 <= derivative <= 3,
        'Bounded periodic controls/parameter/derivative required')
    points = tuple(point(p) for p in controls)
    value = parameter%len(points)
    i = int(value);t = value-i
    if derivative == 0:
        weights = ((1-t)**3,3*t**3-6*t*t+4,-3*t**3+3*t*t+3*t+1,t**3)
    elif derivative == 1:
        weights = (-3*(1-t)**2,9*t*t-12*t,-9*t*t+6*t+3,3*t*t)
    elif derivative == 2:
        weights = (6*(1-t),18*t-12,-18*t+6,6*t)
    else:
        weights = (-6.,18.,-18.,6.)
    active = (points[i-1],points[i],points[(i+1)%len(points)],points[(i+2)%len(points)])
    return tuple(sum(w*p[j] for w,p in zip(weights,active))/6 for j in (0,1))


def _interpolating_controls(nodes,budget):
    """Finite solve of (Pprev+4Pi+Pnext)/6=node_i, two RHS columns.

    The fixed cyclic matrix is strictly diagonally dominant and positive
    definite. This is an interpolation solve, without optimization or tuning.
    """
    require(type(nodes) in (list,tuple) and 4 <= len(nodes) <= 64,
        'Bounded source fit nodes required')
    nodes = tuple(point(v) for v in nodes)
    n = len(nodes)
    matrix = [[0.]*(n+2) for _ in range(n)]
    for i,p in enumerate(nodes):
        matrix[i][i] = 4.
        matrix[i][(i-1)%n] = 1.
        matrix[i][(i+1)%n] = 1.
        matrix[i][n:] = [6*p[0],6*p[1]]
    for pivot in range(n):
        budget.check()
        scale = matrix[pivot][pivot]
        require(isfinite(scale) and scale > 1e-12,'Nonregular interpolation pivot rejected')
        for j in range(pivot,n+2):matrix[pivot][j] /= scale
        for i in range(pivot+1,n):
            factor = matrix[i][pivot]
            if factor:
                for j in range(pivot+1,n+2):matrix[i][j] -= factor*matrix[pivot][j]
                matrix[i][pivot] = 0.
    controls = [[0.,0.] for _ in range(n)]
    for i in range(n-1,-1,-1):
        budget.check()
        for axis in (0,1):
            controls[i][axis] = matrix[i][n+axis]-sum(matrix[i][j]*controls[j][axis] for j in range(i+1,n))
    _controls_to_coefficients(controls)
    require(all(hypot(*g.sub(tuple((controls[i-1][j]+4*controls[i][j]+controls[(i+1)%n][j])/6
        for j in (0,1)),nodes[i])) <= JOIN_TOLERANCE for i in range(n)),
        'Interpolation residual exceeds declared tolerance')
    return controls


def _eval(coeff,index,u,derivative=0):
    a,b,c,d = (coeff[j][index] for j in range(4))
    if derivative == 0:
        return tuple(((a[j]*u+b[j])*u+c[j])*u+d[j] for j in (0,1))
    if derivative == 1:
        return tuple((3*a[j]*u+2*b[j])*u+c[j] for j in (0,1))
    if derivative == 2:
        return tuple(6*a[j]*u+2*b[j] for j in (0,1))
    require(derivative == 3,'Supported cubic derivative required')
    return tuple(6*a[j] for j in (0,1))


def _validate_chain(knots,coeff):
    require(type(knots) in (list,tuple) and 5 <= len(knots) <= 65 and
        all(type(v) in (int,float) and isfinite(v) and 0 <= v <= 10000 for v in knots) and
        knots[0] == 0. and all(b>a for a,b in zip(knots,knots[1:])),
        'Finite increasing cubic parameter knots required')
    n = len(knots)-1
    require(type(coeff) in (list,tuple) and len(coeff) == 4 and
        all(type(row) in (list,tuple) and len(row) == n for row in coeff) and
        all(type(v) in (list,tuple) and len(v) == 2 and
            all(type(x) in (int,float) and isfinite(x) and abs(x) <= 10000 for x in v)
            for row in coeff for v in row),'Bounded local-power cubic coefficient shape required')
    maximum = [0.,0.,0.]
    curvature_jump = 0.
    for i in range(n):
        nxt = (i+1)%n
        end = knots[i+1]-knots[i]
        for derivative in range(3):
            a,b = _eval(coeff,i,end,derivative),_eval(coeff,nxt,0.,derivative)
            error = hypot(*g.sub(a,b))
            maximum[derivative] = max(maximum[derivative],error)
            require(error <= JOIN_TOLERANCE,'Position/velocity/acceleration join or seam mismatch')
        v,a = _eval(coeff,i,end,1),_eval(coeff,i,end,2)
        w,b = _eval(coeff,nxt,0.,1),_eval(coeff,nxt,0.,2)
        require(min(hypot(*v),hypot(*w)) > 1e-9,'Nonregular cubic join required to be rejected')
        curvature_jump = max(curvature_jump,abs(g.cross(v,a)/hypot(*v)**3-g.cross(w,b)/hypot(*w)**3))
    return {'joins_including_seam_checked':n,'maximum_position_residual_m':maximum[0],
        'maximum_parameter_velocity_residual':maximum[1],
        'maximum_parameter_acceleration_residual':maximum[2],
        'maximum_curvature_join_residual_per_m':curvature_jump,
        'tolerance':JOIN_TOLERANCE,'scope':'FLOATING_C2_CONSISTENCY_NOT_EXACT_PERIODICITY_OR_GLOBAL_RATE_PROOF'}


def _interval_bounds(coeff,index,a,b):
    mid,h = (a+b)/2,(b-a)/2
    v = _eval(coeff,index,mid,1)
    acc = max(hypot(*_eval(coeff,index,u,2)) for u in (a,b))
    speed = hypot(*v)
    return mid,h,v,acc,speed-acc*h,speed+acc*h


def _screen_chain(knots,coeff,frame,p,budget):
    joins = _validate_chain(knots,coeff)
    left,right = (tuple(g.checked_polygon(frame[k])) for k in ('left_xy_m','right_xy_m'))
    for a,b in g.segments(left):
        for c,d in g.segments(right):
            require(not g._hit(a,b,c,d),'Approximate cone boundaries cross or touch')
    require(rg._point_inside(left[0],right) != rg._point_inside(right[0],left),
        'Strictly nested approximate cone boundaries required')
    corridor = {'left_xy_m':left,'right_xy_m':right}
    limit = p['curvature_limit_fraction']*tan(p['maximum_steering_rad'])/p['wheelbase_m']
    require(isfinite(limit) and limit > 0,'Finite synthetic curvature limit required')
    counts = {'curvature':0,'clearance':0,'sampling':0}
    max_curvature = 0.;min_speed = float('inf');max_gradient = 0.
    minimum_clearance = float('inf')
    radius = hypot(max(p['front_m'],p['rear_m']),p['width_m']/2)
    margin = p['safety_margin_m']+p['map_uncertainty_m']+p['tracking_allowance_m']+p['polyline_error_m']+p['rounding_m']

    def curvature(i,a,b,depth):
        nonlocal max_curvature,min_speed,max_gradient
        budget.check();counts['curvature'] += 1
        require(counts['curvature'] <= p['maximum_curvature_intervals'],'Curvature interval budget exhausted')
        mid,h,v,amax,vmin,vmax = _interval_bounds(coeff,i,a,b)
        acc,j = _eval(coeff,i,mid,2),_eval(coeff,i,mid,3)
        bound = rg.cubic_curvature_upper_bound(v,acc,j,h)
        if vmin > 1e-9 and isfinite(bound) and bound+p['curvature_rounding_per_m'] <= limit:
            numerator = abs(g.cross(v,acc))+h*abs(g.cross(v,j))+.5*h*h*abs(g.cross(acc,j))
            gradient = p['wheelbase_m']*(vmax*hypot(*j)/vmin**4+3*numerator*vmax*amax/vmin**6)
            require(isfinite(gradient),'Finite interior proxy gradient bound required')
            max_curvature = max(max_curvature,bound);min_speed = min(min_speed,vmin)
            max_gradient = max(max_gradient,gradient)
            return
        if hypot(*v) > 1e-9:
            require(abs(g.cross(v,acc))/hypot(*v)**3 <= limit,'Cubic midpoint exceeds synthetic curvature limit')
        require(depth < p['maximum_depth'],'Continuous curvature unresolved at depth cap')
        curvature(i,a,mid,depth+1);curvature(i,mid,b,depth+1)

    def clearance(i,a,b,depth):
        nonlocal minimum_clearance
        budget.check();counts['clearance'] += 1
        require(counts['clearance'] <= p['maximum_clearance_intervals'],'Clearance interval budget exhausted')
        mid,h,v,amax,vmin,vmax = _interval_bounds(coeff,i,a,b)
        xy = _eval(coeff,i,mid)
        require(hypot(*v) > 1e-9,'Nonregular clearance midpoint rejected')
        slack = rg.footprint_clearance(corridor,(*xy,atan2(v[1],v[0])),
            front_m=p['front_m'],rear_m=p['rear_m'],width_m=p['width_m'],margin_m=margin)
        require(slack > 0,'Cubic rectangle fails padded approximate corridor')
        displacement = float('inf') if vmin <= 1e-9 else (vmax+radius*amax/vmin)*h
        if isfinite(displacement) and slack > displacement:
            minimum_clearance = min(minimum_clearance,slack-displacement)
            return
        require(depth < p['maximum_depth'],'Continuous rectangle clearance unresolved at depth cap')
        clearance(i,a,mid,depth+1);clearance(i,mid,b,depth+1)

    # Carry the original cubic-cell index through all recursion and evaluate
    # both interval endpoints with that cell's one-sided polynomial.
    for i,(a,b) in enumerate(zip(knots,knots[1:])):
        curvature(i,0.,b-a,0)
    for i,(a,b) in enumerate(zip(knots,knots[1:])):
        clearance(i,0.,b-a,0)

    sampled = [];parameters = [];intervals = []
    join_error = joins['maximum_position_residual_m']
    def sample(i,a,b,depth):
        budget.check();counts['sampling'] += 1
        require(counts['sampling'] <= 16384,'Sampling interval budget exhausted')
        pa,pb = _eval(coeff,i,a),_eval(coeff,i,b)
        amax = max(hypot(*_eval(coeff,i,u,2)) for u in (a,b))
        error = amax*(b-a)**2/8+join_error
        if error > p['polyline_error_m'] or hypot(*g.sub(pb,pa)) > p['maximum_sample_spacing_m']:
            require(depth < p['maximum_sampling_depth'],'Polyline error/spacing unresolved at depth cap')
            mid = (a+b)/2
            sample(i,a,mid,depth+1);sample(i,mid,b,depth+1)
            return
        require(len(sampled) < p['maximum_samples'],'Sample capacity exhausted without coarsening')
        sampled.append(pa);parameters.append(knots[i]+a);intervals.append((i,a,b,error))
    for i,(a,b) in enumerate(zip(knots,knots[1:])):
        sample(i,0.,b-a,0)
    xy = sampled+[sampled[0]]
    lengths = [hypot(*g.sub(b,a)) for a,b in zip(xy,xy[1:])]
    require(all(p['minimum_sample_spacing_m'] <= d <= p['maximum_sample_spacing_m']+p['rounding_m'] for d in lengths),
        'Declared sampled view spacing required; no silent redistribution')
    topology = rg.verify_nonlocal_polyline_clearance(sampled,p['polyline_error_m'],
        rounding_m=p['rounding_m'],max_pairs=p['maximum_topology_pairs'],
        max_bucket_entries=p['maximum_bucket_entries'],max_pair_visits=p['maximum_pair_visits'],deadline_callback=budget.check)
    # Explicit one-sided endpoint projections, inflated by the observed join
    # velocity residual, cover both incident sampled intervals and the seam.
    projection_minimum = float('inf')
    for j,(i,a,b,error) in enumerate(intervals):
        budget.check()
        for anchor,which in ((a,'start'),(b,'end')):
            v = _eval(coeff,i,anchor,1)
            acc = max(hypot(*_eval(coeff,i,u,2)) for u in (a,b))
            lower = hypot(*v)-acc*(b-a)-joins['maximum_parameter_velocity_residual']
            require(lower > 1e-9,'Adjacent interval tangent projection unresolved')
            projection_minimum = min(projection_minimum,lower)
    distance = [0.]
    for length in lengths:distance.append(distance[-1]+length)
    previews = []
    for i,a,b,error in intervals:
        mid = (a+b)/2;v,acc = _eval(coeff,i,mid,1),_eval(coeff,i,mid,2)
        previews.append(g.cross(v,acc)/hypot(*v)**3)
    return {'joins':joins,'curvature':{'maximum_floating_bound_per_m':max_curvature,
            'limit_per_m':limit,'intervals':counts['curvature'],'minimum_parameter_speed_bound':min_speed,
            'maximum_interior_proxy_angle_gradient_bound_rad_per_m':max_gradient,
            'gradient_scope':'WITHIN_CUBIC_INTERVALS_PER_NEW_CURVE_ARCLENGTH_NOT_GLOBAL_EXACT_RATE_OR_RAD_PER_SECOND'},
        'clearance':{'minimum_floating_bound_m':minimum_clearance,'intervals':counts['clearance'],
            'full_rectangle_and_uncertainty_scope':'SYNTHETIC_NOT_MEASURED_BODY_OR_SURVEY'},
        'topology':dict(topology,adjacent_interval_count=len(intervals),
            minimum_adjacent_tangent_projection_bound=projection_minimum,
            required_model='SHARED_CYCLIC_UNIFORM_CUBIC_BSPLINE_NOT_INDEPENDENT_POWER_PIECES',
            floating_coefficient_join_position_residual_m=join_error,
            scope='FLOATING_SCREEN_FOR_STRUCTURALLY_PERIODIC_C2_MODEL_NOT_RIGOROUS_ROUNDOFF_OR_ACTUAL_TRAJECTORY_PROOF'),
        'sampling':{'intervals':counts['sampling'],'sample_cells':len(sampled),
            'maximum_cubic_to_view_error_bound_m':max(v[3] for v in intervals),
            'parameter_nodes':parameters+[knots[-1]],
            'parameter_units':'UNIFORM_SOURCE_SAMPLE_INDEX_NOT_METRES_OR_NEW_CURVE_ARCLENGTH',
            'parameter_is_new_curve_arclength':False},
        'geometry':{'model':'polyline_view_of_periodic_cubic','closed':True,'distance_m':distance,
            'x_m':[v[0] for v in xy],'y_m':[v[1] for v in xy],'curvature_per_m':previews,
            'curvature_scope':'CUBIC_MIDPOINT_PREVIEW_NOT_DISCRETE_POLYLINE_CURVATURE_OR_DRIVER_EVIDENCE'}}


def _source_nodes(track):
    knots = [i*(track.length_m/64) for i in range(65)]
    knots[-1] = track.length_m
    nodes = []
    for s in knots:
        i = min(bisect_right(track.distance_m,s)-1,track.cell_count-1)
        f = (s-track.distance_m[i])/track.cell_length_m[i]
        nodes.append([track.x_m[i]+f*(track.x_m[i+1]-track.x_m[i]),
                      track.y_m[i]+f*(track.y_m[i+1]-track.y_m[i])])
    adjustment = hypot(*g.sub(nodes[-1],nodes[0]))
    nodes[-1] = nodes[0][:]
    return knots,nodes,adjustment


def _parse(raw,schema):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,'Bounded immutable cubic artifact required')
    v = json.loads(raw,object_pairs_hook=_unique,parse_constant=_nonfinite)
    require(type(v) is dict and v.get('schema') == schema and g.canonical(v).encode() == raw,
        'Canonical cubic artifact schema required')
    return v


@dataclass(frozen=True,slots=True)
class FsgSmoothedCandidate:
    raw: bytes

    def __post_init__(self):
        v = _parse(self.raw,SCHEMA)
        require(v.get('status') == 'SMOOTH_GEOMETRY_SCREENED_DEVELOPMENT_UNQUALIFIED' and
            v.get('qualification_or_execution_authority') is False and
            v.get('actual_car_or_driver_or_native_qualified') is False and
            all(type(v.get(k)) is dict for k in ('proposal','screens','original_source_steering_proxy')) and
            v.get('original_producer_or_environment_authenticated') is False and
            v.get('heldout_results_used') is False and v.get('awards') is None,
            'Explicit unqualified candidate transport required; readback still required')
        require(type(v['proposal'].get('control_points_xy_m')) is list and
            len(v['proposal']['control_points_xy_m']) == 64,
            'Complete shared64control defining geometry required')
        _controls_to_coefficients(v['proposal']['control_points_xy_m'])

    def payload(self):
        return json.loads(self.raw)

    def evaluate(self,parameter,derivative=0):
        return evaluate_periodic_controls(self.payload()['proposal']['control_points_xy_m'],parameter,derivative)


def _screen_proposal(proposal_raw,bundle_raw,cones_raw,budget):
    try:
        budget.check()
        proposal = _parse(proposal_raw,PROPOSAL_SCHEMA)
        source = construct_fsg_course(bundle_raw,cones_raw)
        source_stations,nodes,adjustment = _source_nodes(source.source_track)
        knots = [float(i) for i in range(65)]
        expected = {'schema','source_bundle_sha256','source_cones_sha256','source_geometry_sha256',
            'frame','frame_sha256','parameters','source_fit_stations_m','parameter_knots','control_points_xy_m',
            'input_view_closure_adjustment_m','producer_algorithm','qualification_or_execution_authority'}
        require(proposal.keys() == expected and g.canonical(proposal['parameters']) == g.canonical(PARAMETERS) and
            proposal['qualification_or_execution_authority'] is False and
            proposal['source_bundle_sha256'] == source.bundle_raw_sha256 and
            proposal['source_cones_sha256'] == source.cones_raw_sha256 and
            proposal['source_geometry_sha256'] == source.geometry_sha256 and
            g.canonical(proposal['frame']) == g.canonical(source.frame_dict()) and
            proposal['frame_sha256'] == g.digest(proposal['frame']) == g.digest(source.frame_dict()) and
            g.canonical(proposal['source_fit_stations_m']) == g.canonical(source_stations) and
            g.canonical(proposal['parameter_knots']) == g.canonical(knots) and
            g.canonical(proposal['input_view_closure_adjustment_m']) == g.canonical(adjustment),
            'Exact local source/frame/fixed fit recipe required')
        require(proposal['producer_algorithm'] == 'BOUNDED_STDLIB_CYCLIC_CUBIC_INTERPOLATION_SOLVE_V1',
            'Fixed development producer recipe required, not authentication')
        coeff = _controls_to_coefficients(proposal['control_points_xy_m'])
        _validate_chain(knots,coeff)
        fit_residual = 0.
        system_residual = 0.
        controls = proposal['control_points_xy_m']
        for i,point in enumerate(nodes[:-1]):
            residual = hypot(*g.sub(evaluate_periodic_controls(controls,float(i)),point))
            fit_residual = max(fit_residual,residual)
            system_residual = max(system_residual,hypot(*tuple(controls[i-1][j]+4*controls[i][j]+
                controls[(i+1)%64][j]-6*point[j] for j in (0,1))))
            require(residual <= JOIN_TOLERANCE and hypot(*g.sub(_eval(coeff,i,0.),point)) <= JOIN_TOLERANCE,
                'Cubic does not interpolate declared source-station fit nodes')
        result = _screen_chain(knots,coeff,proposal['frame'],dict(PARAMETERS),budget)
        result['fit'] = {'maximum_source_node_residual_m':fit_residual,
            'maximum_cyclic_system_residual_m':system_residual,
            'matrix':'4I_PLUS_CYCLIC_NEIGHBOR_SHIFTS_SPD_EIGENVALUES_2_TO_6',
            'defining_geometry':'ONE_SHARED_CYCLIC_CONTROL_ARRAY_WITH_UNIFORM_CUBIC_BSPLINE_BASIS'}
        baseline = _steering_proxy(source.source_track,wheelbase_m=1.6,
            maximum_steering_rad=.4,curvature_limit_fraction=.95)
        value = {'schema':SCHEMA,'status':'SMOOTH_GEOMETRY_SCREENED_DEVELOPMENT_UNQUALIFIED',
            'method':'FIXED_64_SOURCE_STATION_SHARED_PERIODIC_CUBIC_BSPLINE_NOT_OPTIMIZATION',
            'proposal':proposal,'proposal_sha256':sha256(proposal_raw).hexdigest(),
            'screens':result,'geometry_sha256':g.digest(result['geometry']),
            'original_source_steering_proxy':baseline,'role':'development','heldout_results_used':False,
            'source_reference_or_native_contract_modified':False,
            'fit_parameter_is_new_curve_arclength':False,
            'analytic_model_periodic_C2_by_shared_cyclic_basis':True,
            'derived_float_coefficients_define_independent_joining_pieces':False,
            'reference_start_is_source_builder_seam_not_verified_timing_gate':True,
            'gate_phase_or_mission_semantics_supplied':False,'optimized_or_minimum_time_proven':False,
            'rigorous_roundoff_or_exact_machine_arithmetic_periodicity_proven':False,
            'steering_rate_in_time_or_vehicle_following_qualified':False,
            'actual_car_or_driver_or_native_qualified':False,
            'original_producer_or_environment_authenticated':False,
            'readback_scope':'LOCAL_NUMERICAL_SOURCE_CONSISTENCY_ONLY_NOT_CROSS_PLATFORM_QUALIFICATION',
            'awards':None,'qualification_or_execution_authority':False}
        raw = g.canonical(value).encode()
        require(len(raw) <= MAX_BYTES,'Screened cubic candidate exceeds transport capacity')
        candidate = FsgSmoothedCandidate(raw)
        budget.check()  # Includes serialization and transport parsing, on the original clock.
        return candidate
    except ValueError as exc:
        raise SplineScreenFailure(str(exc),proposal_raw) from exc


def screen_fsg_spline_proposal(proposal_raw,bundle_raw,cones_raw,*,work_wall_s=40.):
    return _screen_proposal(proposal_raw,bundle_raw,cones_raw,_Budget(work_wall_s))


def verify_fsg_smoothed_candidate(raw,bundle_raw,cones_raw,*,work_wall_s=40.):
    budget = _Budget(work_wall_s)
    value = _parse(raw,SCHEMA)
    require(type(value.get('proposal')) is dict,'Complete cubic proposal required for readback')
    rebuilt = _screen_proposal(g.canonical(value['proposal']).encode(),bundle_raw,cones_raw,budget)
    require(rebuilt.raw == raw,'Candidate differs from complete coefficient/source/screens readback')
    budget.check()
    return rebuilt


def produce_fsg_smoothed_candidate(bundle_raw,cones_raw,*,work_wall_s=40.):
    """Explicit finite stdlib producer; no install, fallback, vehicle model or I/O."""
    budget = _Budget(work_wall_s)
    source = construct_fsg_course(bundle_raw,cones_raw)
    source_stations,nodes,adjustment = _source_nodes(source.source_track)
    controls = _interpolating_controls(nodes[:-1],budget)
    proposal = {'schema':PROPOSAL_SCHEMA,'source_bundle_sha256':source.bundle_raw_sha256,
        'source_cones_sha256':source.cones_raw_sha256,'source_geometry_sha256':source.geometry_sha256,
        'frame':source.frame_dict(),'frame_sha256':g.digest(source.frame_dict()),
        'parameters':dict(PARAMETERS),'source_fit_stations_m':source_stations,
        'parameter_knots':[float(i) for i in range(65)],'control_points_xy_m':controls,
        'input_view_closure_adjustment_m':adjustment,
        'producer_algorithm':'BOUNDED_STDLIB_CYCLIC_CUBIC_INTERPOLATION_SOLVE_V1',
        'qualification_or_execution_authority':False}
    proposal_raw = g.canonical(proposal).encode()
    return _screen_proposal(proposal_raw,bundle_raw,cones_raw,budget)
