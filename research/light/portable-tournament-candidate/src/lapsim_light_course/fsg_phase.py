"""Unqualified FSG timing-segment geometry and phase over an unchanged spline.

Exact rational predicates concern the serialized digital controls/gate only.
They provide no survey, CG/start state, lap/time/energy, producer authentication
or native admission. Existing FSI mission/receipt contracts are not adapted here.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
import heapq
from math import hypot,isfinite,nextafter,inf

from . import _fsi_geometry as g, fsg_smoothing as sm
from .course import construct_fsg_course
from .fsg_reference import metadata,map_point,source_crossing,point,require

SCHEMA = 'lapsim.fsg-smoothed-reference-gate-phase.v1'
MAX_BYTES = 128*1024
MAX_ROOT_NODES = 8192
MAX_ROOT_DEPTH = 48
ROOT_WIDTH = F(1,2**36)
MARGIN_NODES = 8192
MARGIN_DEPTH = 20
MARGIN_GAP_PER_M = 1e-4


def _exact_point(p):
    return tuple(F(v) for v in point(p))


def _ratio(v):
    return {'numerator':str(v.numerator),'denominator':str(v.denominator)}


def _ratio_value(v):
    require(type(v) is dict and v.keys() == {'numerator','denominator'} and
        all(type(v[k]) is str and len(v[k]) <= 128 for k in v),'Bounded canonical parameter ratio required')
    try:result = F(int(v['numerator']),int(v['denominator']))
    except (ValueError,ZeroDivisionError) as exc:raise ValueError('Canonical parameter ratio required') from exc
    require(v == _ratio(result),'Reduced canonical parameter ratio required')
    return result


def _representative_radius(lo,hi,representative):
    """Outward float radius includes midpoint conversion, even for exact roots."""
    centre = F(representative)
    exact = max(abs(centre-lo),abs(hi-centre))
    radius = float(exact)
    return nextafter(radius,inf) if F(radius) < exact else radius


def _beziers(controls):
    # Convert defining binary64 controls BEFORE rational linear combinations.
    require(type(controls) in (list,tuple) and 4 <= len(controls) <= 64,
        'Bounded shared periodic controls required')
    p = tuple(_exact_point(v) for v in controls)
    result = []
    for i,b in enumerate(p):
        a,c,d = p[i-1],p[(i+1)%len(p)],p[(i+2)%len(p)]
        result.append((tuple((a[j]+4*b[j]+c[j])/6 for j in (0,1)),
            tuple((2*b[j]+c[j])/3 for j in (0,1)),
            tuple((b[j]+2*c[j])/3 for j in (0,1)),
            tuple((b[j]+4*c[j]+d[j])/6 for j in (0,1))))
    return tuple(result)


def _split(points):
    a,b,c,d = points
    ab,bc,cd = (tuple((x+y)/2 for x,y in zip(p,q)) for p,q in ((a,b),(b,c),(c,d)))
    abc,bcd = (tuple((x+y)/2 for x,y in zip(p,q)) for p,q in ((ab,bc),(bc,cd)))
    middle = tuple((x+y)/2 for x,y in zip(abc,bcd))
    return (a,ab,abc,middle),(middle,bcd,cd,d)


def _isolate_beziers(beziers,ends,orientation,budget,*,max_nodes=MAX_ROOT_NODES,max_depth=MAX_ROOT_DEPTH):
    require(type(orientation) is int and orientation in (-1,1) and
        type(max_nodes) is int and 0 < max_nodes <= MAX_ROOT_NODES and
        type(max_depth) is int and 0 <= max_depth <= MAX_ROOT_DEPTH,'Bounded exact root recipe required')
    a,b = tuple(_exact_point(p) for p in ends)
    direction = g.sub(b,a);length2 = g.dot(direction,direction)
    require(length2 > 0,'Nondegenerate digital gate required')
    period = len(beziers)
    require(1 <= period <= 64,'Bounded cubic cell count required')
    exact = {};brackets = [];nodes = 0;deduplications = 0

    def projections(points):
        return tuple(orientation*g.cross(direction,g.sub(p,a)) for p in points),tuple(
            g.dot(g.sub(p,a),direction) for p in points)

    def consume(depth):
        nonlocal nodes
        budget.check();nodes += 1
        require(nodes <= max_nodes and depth <= max_depth,'Exact gate root node/depth budget exhausted')

    def record_at(parameter,h,derivative):
        nonlocal deduplications
        if h < 0 or h > length2:return
        require(0 < h < length2,'Digital gate endpoint root is unsupported')
        require(derivative != 0,'Nontransverse/tangent digital gate root is unsupported')
        key = parameter%period
        sign = 1 if derivative > 0 else -1
        if key in exact:
            require(exact[key][0] == h and exact[key][1] == sign,
                'Shared knot root position/direction conflict')
            deduplications += 1
            return
        exact[key] = (h,sign,derivative)

    def root_record(i,lo,hi,f,h,df):
        middle = (lo+hi)/2
        representative = float(middle)
        return {'cell_index':i,'parameter_bracket':[_ratio(lo),_ratio(hi)],
            'representative_parameter_index':representative,
            'parameter_radius_index':_representative_radius(lo,hi,representative),
            'exact_dyadic_parameter_known':lo == hi,
            'direction':1 if min(df) > 0 else -1,
            'supporting_line_values_at_bracket_m2':[float(f[0]),float(f[-1])],
            'segment_coordinate_hull_m2':[float(min(h)),float(max(h))],
            'transverse_derivative_hull_m2_per_index':[float(min(df)),float(max(df))],
            'root_is_for_exact_serialized_digital_model':True}

    def refine(i,points,lo,hi,depth):
        while True:
            consume(depth)
            f,h = projections(points)
            df = tuple(3*(y-x)/(hi-lo) for x,y in zip(f,f[1:]))
            require(min(df) > 0 or max(df) < 0,'Transverse derivative enclosure lost')
            require(f[0]*f[-1] < 0,'Strict opposite-sign root bracket required')
            if max(h) < 0 or min(h) > length2:return
            if hi-lo <= ROOT_WIDTH and min(h) > 0 and max(h) < length2:
                brackets.append(root_record(i,F(i)+lo,F(i)+hi,f,h,df));return
            require(depth < max_depth,'Finite gate/root bracket refinement unresolved')
            left,right = _split(points);mid = (lo+hi)/2
            fm,hm = projections(left)
            if fm[-1] == 0:
                derivative = 3*(fm[-1]-fm[-2])/(mid-lo)
                record_at(F(i)+mid,hm[-1],derivative);return
            if f[0]*fm[-1] < 0:points,hi = left,mid
            else:points,lo = right,mid
            depth += 1

    def visit(i,points,lo,hi,depth):
        consume(depth)
        f,h = projections(points)
        if max(h) < 0 or min(h) > length2:return  # Exact finite-extent exclusion.
        if f[0] == 0:record_at(F(i)+lo,h[0],3*(f[1]-f[0])/(hi-lo))
        if f[-1] == 0:record_at(F(i)+hi,h[-1],3*(f[-1]-f[-2])/(hi-lo))
        require(any(v != 0 for v in f),'Digital curve overlaps supporting gate line')
        # Strictly positive interior Bernstein weights exclude any further
        # interior root when the hull has only one sign (zeros already owned).
        if min(f) >= 0 or max(f) <= 0:return
        df = tuple(3*(y-x)/(hi-lo) for x,y in zip(f,f[1:]))
        if min(df) > 0 or max(df) < 0:
            if f[0]*f[-1] < 0:refine(i,points,lo,hi,depth)
            return
        require(depth < max_depth,'Digital gate crossing/tangency unresolved')
        left,right = _split(points);mid = (lo+hi)/2
        visit(i,left,lo,mid,depth+1);visit(i,right,mid,hi,depth+1)

    for i,points in enumerate(beziers):visit(i,points,F(0),F(1),0)
    for parameter,(h,sign,derivative) in sorted(exact.items()):
        brackets.append(root_record(int(parameter),parameter,parameter,(F(0),F(0)),(h,h),(derivative,derivative)))
    brackets.sort(key=lambda r:_ratio_value(r['parameter_bracket'][0]))
    return {'roots':brackets,'nodes_visited':nodes,'cells_resolved':period,
        'identical_endpoint_roots_deduplicated':deduplications,
        'maximum_nodes':max_nodes,'maximum_depth':max_depth,
        'root_width_limit_index':float(ROOT_WIDTH),
        'predicates':'EXACT_RATIONAL_BEZIER_FOR_STORED_BINARY64_CONTROLS_AND_GATE_ENDPOINTS',
        'physical_source_transform_or_survey_certified':False}


def _digital_roots(controls,ends,orientation,budget,**limits):
    return _isolate_beziers(_beziers(controls),ends,orientation,budget,**limits)


def _curvature_margin(value,budget,*,max_nodes=MARGIN_NODES,max_depth=MARGIN_DEPTH):
    require(type(max_nodes) is int and 1 <= max_nodes <= MARGIN_NODES and
        type(max_depth) is int and 0 <= max_depth <= MARGIN_DEPTH,'Bounded margin refinement recipe required')
    controls = value['proposal']['control_points_xy_m']
    coeff = sm._controls_to_coefficients(controls)
    old = value['screens']['curvature']['maximum_floating_bound_per_m']
    limit = value['screens']['curvature']['limit_per_m']
    require(all(type(v) in (int,float) and isfinite(v) and v > 0 for v in (old,limit)),
        'Verified finite coarse curvature certificate required')
    nodes = 0;observed = 0.;witness = None
    def make(i,a,b,depth,inherited):
        nonlocal nodes,observed,witness
        budget.check();nodes += 1
        require(nodes <= max_nodes,'Curvature margin node budget exhausted')
        mid,h = (a+b)/2,(b-a)/2
        v,acc,j = (sm._eval(coeff,i,mid,n) for n in (1,2,3))
        raw = sm.rg.cubic_curvature_upper_bound(v,acc,j,h)
        upper = min(inherited,raw)  # Every inherited bound covers the whole child.
        require(isfinite(upper) and upper >= 0,'Finite covering curvature bound required')
        for u in (a,mid,b):
            vel,aa = sm._eval(coeff,i,u,1),sm._eval(coeff,i,u,2)
            require(hypot(*vel) > 1e-9,'Regular point required for observed curvature')
            sample = abs(g.cross(vel,aa))/hypot(*vel)**3
            if sample > observed:observed = sample;witness = [i,u]
        return (-upper,i,a,b,depth)
    heap = [make(i,0.,1.,0,old) for i in range(len(controls))]
    heapq.heapify(heap)
    while -heap[0][0]-observed > MARGIN_GAP_PER_M:
        require(nodes+2 <= max_nodes,'Curvature margin node budget exhausted')
        neg,i,a,b,depth = heapq.heappop(heap)
        require(depth < max_depth,'Curvature margin depth budget exhausted')
        mid = (a+b)/2
        left,right = make(i,a,mid,depth+1,-neg),make(i,mid,b,depth+1,-neg)
        heapq.heappush(heap,left);heapq.heappush(heap,right)
    upper = -heap[0][0]
    guard = value['proposal']['parameters']['curvature_rounding_per_m']
    require(observed <= upper+guard,'Observed curvature contradicts covering certificate')
    coverage = [{'cell_index':i,'left_index':a,'right_index':b,'upper_bound_per_m':-neg}
                for neg,i,a,b,d in sorted(heap,key=lambda v:(v[1],v[2]))]
    return {'coarse_upper_bound_per_m':old,'refined_upper_bound_per_m':upper,
        'unchanged_limit_per_m':limit,'guard_per_m':guard,
        'guarded_margin_per_m':limit-upper-guard,
        'maximum_observed_point_curvature_per_m':observed,'observed_point_cell_local_parameter':witness,
        'bound_minus_observed_point_per_m':upper-observed,'target_gap_per_m':MARGIN_GAP_PER_M,
        'covering_intervals':coverage,'nodes_visited':nodes,'leaf_count':len(heap),
        'maximum_nodes':max_nodes,'maximum_depth':max_depth,'coverage_complete':True,
        'method':'MAX_UPPER_OVER_COMPLETE_PARTITION_WITH_VALID_INHERITED_PARENT_BOUNDS',
        'rigorous_roundoff_or_actual_steering_margin_proven':False}


def _verified_base(raw,bundle_raw,cones_raw,budget):
    budget.check()
    value = sm._parse(raw,sm.SCHEMA)
    require(type(value.get('proposal')) is dict,'Complete unchanged base reference required')
    base = sm._screen_proposal(g.canonical(value['proposal']).encode(),bundle_raw,cones_raw,budget)
    require(base.raw == raw,'Base reference differs from complete original readback')
    budget.check()
    return base


def _source_gate(source,cones_raw):
    frame = source.frame_dict()
    upstream,front_wing = metadata(cones_raw)
    ends = tuple(map_point(frame,p) for p in upstream)
    points = tuple(zip(source.source_track.x_m[:-1],source.source_track.y_m[:-1]))
    i,_,_ = source_crossing(points,ends)
    delta = g.sub(_exact_point(points[(i+1)%len(points)]),_exact_point(points[i]))
    a,b = tuple(_exact_point(p) for p in ends)
    direction = g.sub(b,a);sign = g.cross(direction,delta)
    require(sign != 0,'Original ordered source must cross digital gate transversely')
    orientation = 1 if sign > 0 else -1
    dx,dy = tuple(float(v) for v in direction);length = hypot(dx,dy)
    return {'schema':'lapsim.fsg-source-tk-device-finite-gate.v1',
        'upstream_endpoints_xy_m':[list(p) for p in upstream],'endpoints_xy_m':[list(p) for p in ends],
        'origin_xy_m':[(a+b)/2 for a,b in zip(*ends)],
        'forward_unit':[-orientation*dy/length,orientation*dx/length],
        'finite_half_width_m':length/2,'digital_orientation':orientation,
        'orientation_source_cell':i,'orientation_basis':'ORDERED_ORIGINAL_SOURCE_CHORD_SIGN_ONLY_NOT_OLD_PHASE',
        'source_starting_pose_front_wing_raw':list(front_wing),
        'front_wing_pose_used_as_vehicle_state':False,'official_timing_or_vehicle_start_verified':False}


def _parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,'Bounded immutable phase bytes required')
    return sm._parse(raw,SCHEMA)


@dataclass(frozen=True,slots=True)
class FsgSmoothedPhaseView:
    raw: bytes
    reference: sm.FsgSmoothedCandidate

    def __post_init__(self):
        value = _parse(self.raw)
        require(type(self.reference) is sm.FsgSmoothedCandidate and
            value.get('status') == 'GEOMETRIC_GATE_PHASE_DEVELOPMENT_ONLY' and
            value.get('base_reference_sha256') == sha256(self.reference.raw).hexdigest() and
            value.get('base_geometry_sha256') == self.reference.payload()['geometry_sha256'] and
            value.get('qualification_or_execution_authority') is False and
            value.get('actual_car_or_native_or_mission_qualified') is False and
            value.get('root_midpoint_is_exact_machine_gate_pose') is False and
            value.get('old_fsi_gate_ledger_or_worker_compatible') is False and
            value.get('source_or_reference_or_clearance_or_steering_caps_modified') is False and
            value.get('phase_units') == 'TRANSLATED_SOURCE_SAMPLE_INDEX0_TO64_NOT_METRES_TIME_OR_LAPS' and
            all(type(value.get(k)) is dict for k in ('gate','root','root_search','curvature_margin')),
            'Unqualified phase transport must bind unchanged reference bytes; readback still required')
        require(type(value['root_search'].get('roots')) is list and len(value['root_search']['roots']) == 1 and
            g.canonical(value['root_search']['roots'][0]) == g.canonical(value['root']),
            'Phase root must match its single retained digital intersection')
        proposal = self.reference.payload()['proposal']
        require(all(value.get(key) == proposal[original] for key,original in (
            ('source_bundle_sha256','source_bundle_sha256'),('source_cones_sha256','source_cones_sha256'),
            ('source_geometry_sha256','source_geometry_sha256'),('source_frame_sha256','frame_sha256'))) and
            value.get('awards') is None and value.get('heldout_results_used') is False and
            value.get('event_departure_progress_or_lap_receipt_supplied') is False,
            'Phase transport source/frame and non-event scope must match base')
        lo,hi = tuple(_ratio_value(v) for v in value['root']['parameter_bracket'])
        representative = value['root']['representative_parameter_index']
        require(0 <= lo <= hi <= 64 and type(representative) in (int,float) and
            isfinite(representative) and 0 <= representative < 64 and
            g.canonical(representative) == g.canonical(float((lo+hi)/2)),
            'Bounded single-period root phase required')
        require(type(value['root'].get('parameter_radius_index')) in (int,float) and
            g.canonical(value['root']['parameter_radius_index']) ==
                g.canonical(_representative_radius(lo,hi,representative)),
            'Outward representative-to-root-bracket radius required')

    def payload(self):
        return sm.json.loads(self.raw)

    def evaluate(self,progress_index,derivative=0):
        require(type(progress_index) in (int,float) and isfinite(progress_index) and 0 <= progress_index <= 64,
            'Phase progress is bounded source-sample index0..64, not metres/time/laps')
        offset = self.payload()['root']['representative_parameter_index']
        parameter = offset if progress_index in (0.,64.) else (offset+progress_index)%64
        return self.reference.evaluate(parameter,derivative)

    def finite_segment_crossing(self,before_xy,after_xy):
        """Geometry only; initial departure/progress/state/timing remain external."""
        gate = self.payload()['gate']
        a,b = tuple(_exact_point(p) for p in gate['endpoints_xy_m'])
        before,after = _exact_point(before_xy),_exact_point(after_xy)
        direction = g.sub(b,a);orientation = gate['digital_orientation']
        require(type(orientation) is int and orientation in (-1,1),'Exact digital orientation required')
        f0,f1 = tuple(orientation*g.cross(direction,g.sub(p,a)) for p in (before,after))
        if not f0 < 0 <= f1:return None
        fraction = -f0/(f1-f0)
        crossing = tuple(x+fraction*(y-x) for x,y in zip(before,after))
        h = g.dot(g.sub(crossing,a),direction);length2 = g.dot(direction,direction)
        if h < 0 or h > length2:return None
        require(0 < h < length2,'Digital gate endpoint crossing is unsupported')
        return {'fraction':float(fraction),'fraction_exact':_ratio(fraction),
            'point_xy_m':[float(v) for v in crossing],
            'scope':'GEOMETRY_ONLY_NOT_LAP_TIME_ENERGY_STATE_OR_ADMISSION','awards':None,
            'lap_completion_or_initial_departure_verified':False}


def _build_phase_from_verified(reference,bundle_raw,cones_raw,budget):
    budget.check()
    source = construct_fsg_course(bundle_raw,cones_raw)
    gate = _source_gate(source,cones_raw)
    roots = _digital_roots(reference.payload()['proposal']['control_points_xy_m'],
        gate['endpoints_xy_m'],gate['digital_orientation'],budget)
    require(len(roots['roots']) == 1 and roots['roots'][0]['direction'] == 1,
        'Exactly one forward finite transverse FSG gate crossing required')
    root = roots['roots'][0]
    require(min(root['transverse_derivative_hull_m2_per_index']) > 1e-6,
        'Well-conditioned forward phase required for finite float evaluation')
    pose = reference.evaluate(root['representative_parameter_index'])
    origin,normal = gate['origin_xy_m'],gate['forward_unit']
    residual = abs(g.dot(g.sub(pose,origin),normal))
    require(residual <= 1e-8,'Representative root pose residual exceeds numerical check')
    margin = _curvature_margin(reference.payload(),budget)
    value = {'schema':SCHEMA,'status':'GEOMETRIC_GATE_PHASE_DEVELOPMENT_ONLY',
        'base_reference_sha256':sha256(reference.raw).hexdigest(),
        'base_geometry_sha256':reference.payload()['geometry_sha256'],
        'source_bundle_sha256':source.bundle_raw_sha256,'source_cones_sha256':source.cones_raw_sha256,
        'source_geometry_sha256':source.geometry_sha256,'source_frame_sha256':g.digest(source.frame_dict()),
        'gate':gate,'root':root,'root_search':roots,'curvature_margin':margin,
        'representative_root_pose_xy_m':list(pose),'representative_plane_residual_m':residual,
        'phase_units':'TRANSLATED_SOURCE_SAMPLE_INDEX0_TO64_NOT_METRES_TIME_OR_LAPS',
        'root_midpoint_is_exact_machine_gate_pose':False,
        'source_or_reference_or_clearance_or_steering_caps_modified':False,
        'event_departure_progress_or_lap_receipt_supplied':False,
        'old_fsi_gate_ledger_or_worker_compatible':False,'heldout_results_used':False,'awards':None,
        'actual_car_or_native_or_mission_qualified':False,'qualification_or_execution_authority':False}
    raw = g.canonical(value).encode()
    require(len(raw) <= MAX_BYTES,'Phase transport capacity exceeded')
    result = FsgSmoothedPhaseView(raw,reference)
    budget.check()
    return result


def construct_fsg_gate_phase(reference_raw,bundle_raw,cones_raw,*,work_wall_s=40.):
    budget = sm._Budget(work_wall_s)
    reference = _verified_base(reference_raw,bundle_raw,cones_raw,budget)
    return _build_phase_from_verified(reference,bundle_raw,cones_raw,budget)


def verify_fsg_gate_phase(raw,reference_raw,bundle_raw,cones_raw,*,work_wall_s=40.):
    budget = sm._Budget(work_wall_s)
    _parse(raw)
    # Pass the same absolute budget into the complete construction, not a
    # restarted allowance. Public constructor owns no OS worker or native lease.
    reference = _verified_base(reference_raw,bundle_raw,cones_raw,budget)
    rebuilt = _build_phase_from_verified(reference,bundle_raw,cones_raw,budget)
    require(rebuilt.raw == raw,'Phase differs from unchanged reference/gate/covering audit readback')
    budget.check()
    return rebuilt
