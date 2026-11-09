"""Bounded approximate-cone route/body screens, separate from course admission.

The cone-centre polygons, caller body dimensions and scalar uncertainties are
model assumptions. Floating geometry screens are not survey, dynamics, original
producer authentication, an admitted reference, or native execution authority.
"""
from hashlib import sha256
from math import atan2, ceil, hypot, isfinite, pi, remainder, sin

from . import _fsi_geometry as g, racing_geometry as rg
from .course import construct_fsg_course
from .fsg_reference import point, require, verify_fsg_source_chord_reference

MAX_PAIRS = 300000
ROUNDING_ALLOWANCE_M = 1e-9
MAX_ROTATION_INTERVALS = 8192
MAX_ROTATION_DEPTH = 10


def _rotation_screen(corridor,anchor,lo,hi,dimensions,padding,*,
        maximum_intervals,maximum_depth):
    """Internal floating bound for a specified static-yaw pose family.

    A body point at radius <=R moves at most 2 R sin(|hi-lo|/4)
    from the midpoint orientation anywhere in an interval of width <=pi.
    Positive midpoint footprint slack exceeding this displacement covers the
    entire interval. This supplies no physically feasible in-place manoeuvre.
    Inputs are bounded/validated by screen_closed_route.
    """
    front,rear,width = dimensions
    radius = hypot(max(front,rear),width/2)
    pending = [(lo,hi,0)]
    count = 0
    minimum = None
    witness = None
    status = 'CLEAR_FLOAT_BOUND'
    while pending:
        if count >= maximum_intervals:
            status = 'INTERVAL_BUDGET_EXHAUSTED'
            break
        a,b,depth = pending.pop()
        mid = a+(b-a)/2
        pose = (anchor[0],anchor[1],mid)
        slack = rg.footprint_clearance(corridor,pose,
            front_m=front,rear_m=rear,width_m=width,margin_m=padding)
        count += 1
        displacement = 2*radius*sin(abs(b-a)/4)
        bound = slack-displacement
        witness = list(pose)
        if slack <= 0:
            status = 'STATIC_POSE_SCREEN_FAILED'
            break
        if bound > 0:
            minimum = bound if minimum is None else min(minimum,bound)
            continue
        if depth >= maximum_depth:
            status = 'DEPTH_EXHAUSTED'
            break
        pending.extend(((mid,b,depth+1),(a,mid,depth+1)))
    return {'status':status,'clear':status == 'CLEAR_FLOAT_BOUND',
        'intervals_checked':count,'minimum_certified_slack_bound_m':minimum,
        'witness_pose_xy_yaw':witness}


def screen_closed_route(points, frame, *, front_m, rear_m, width_m,
        safety_margin_m, map_uncertainty_m, tracking_allowance_m,
        source_arc_allowance_m, maximum_pairs=MAX_PAIRS,
        maximum_rotation_intervals=MAX_ROTATION_INTERVALS):
    """Screen every coarse chord, without claiming a drivable yaw transition.

    A disk of radius hypot(max(front,rear),width/2) encloses the rectangle at
    every heading. Its swept capsule covers all chord positions and junction
    headings. Separately a rectangle extended by half the chord length at each
    longitudinal end is the exact fixed-heading translation envelope on that
    chord. If necessary, a separate bounded midpoint-displacement screen checks
    each shortest incoming-to-outgoing static-yaw family at the exact junction.
    This is not a feasible in-place car turn or a smooth moving trajectory.
    Failure of a sufficient disk bound does not prove rectangle collision.
    """
    require(type(points) in (tuple,list) and 3 <= len(points) <= 1000,
        'Bounded unclosed route vertices required')
    path = tuple(point(p) for p in points)
    edges = g.segments(path)
    lengths = tuple(hypot(*g.sub(b,a)) for a,b in edges)
    require(all(length >= 1e-5 for length in lengths), 'Nondegenerate route chords required')
    dimensions = (front_m,rear_m,width_m)
    margins = (safety_margin_m,map_uncertainty_m,tracking_allowance_m,source_arc_allowance_m)
    require(all(type(v) in (int,float) and isfinite(v) and 0 < v <= 10 for v in dimensions) and
        all(type(v) in (int,float) and isfinite(v) and 0 <= v <= 10 for v in margins),
        'Explicit finite bounded rectangle dimensions and nonnegative uncertainty allowances required')
    require(type(maximum_pairs) is int and 1 <= maximum_pairs <= MAX_PAIRS,
        'Finite route/boundary pair budget required')
    require(type(maximum_rotation_intervals) is int and
        1 <= maximum_rotation_intervals <= MAX_ROTATION_INTERVALS,
        'Finite shared junction rotation interval budget required')
    require(type(frame) is dict and all(k in frame for k in ('left_xy_m','right_xy_m')),
        'Complete approximate cone boundaries required')
    left,right = (tuple(g.checked_polygon(frame[k])) for k in ('left_xy_m','right_xy_m'))
    boundaries = (g.segments(left),g.segments(right))
    pair_count = len(edges)*(len(left)+len(right))
    require(pair_count <= maximum_pairs, 'Route/boundary pair budget exhausted before clearance loops')
    for a,b in boundaries[0]:
        for c,d in boundaries[1]:
            require(not g._hit(a,b,c,d), 'Cone boundaries cross or touch')
    require(rg._point_inside(left[0],right) != rg._point_inside(right[0],left),
        'Nested nonintersecting cone boundaries required, not disjoint polygons')
    corridor = {'left_xy_m':left,'right_xy_m':right}
    inside = all(rg._point_inside(p,left) != rg._point_inside(p,right) for p in path)
    minimum = float('inf')
    nearest = None
    minimum_rectangle = float('inf')
    rectangle_witness = None
    padding = sum(margins)+ROUNDING_ALLOWANCE_M
    for i,((a,b),length) in enumerate(zip(edges,lengths)):
        for side,boundary in zip(('left','right'),boundaries):
            for j,(c,d) in enumerate(boundary):
                distance = rg._segment_distance(a,b,c,d)
                if distance < minimum:
                    minimum = distance
                    nearest = {'route_chord_index':i,'boundary':side,'boundary_edge_index':j,
                        'route_chord_xy_m':[list(a),list(b)],'boundary_edge_xy_m':[list(c),list(d)]}
        # Union of all fixed-chord-heading translated rectangles, including
        # both endpoints. This is not interpolation of yaw across junctions.
        heading = atan2(b[1]-a[1],b[0]-a[0])
        pose = ((a[0]+b[0])/2,(a[1]+b[1])/2,heading)
        slack = rg.footprint_clearance(corridor,pose,front_m=front_m+length/2,
            rear_m=rear_m+length/2,width_m=width_m,margin_m=padding)
        if slack < minimum_rectangle:
            minimum_rectangle = slack
            rectangle_witness = {'route_chord_index':i,'midpoint_pose_xy_yaw':list(pose),
                'swept_front_extent_m':front_m+length/2,'swept_rear_extent_m':rear_m+length/2,
                'width_m':width_m,'slack_m':slack}
    # A positive whole-segment distance plus one interior point per connected
    # path component excludes crossing the simple, disjoint boundaries.
    route_inside = inside and minimum > ROUNDING_ALLOWANCE_M
    radius = hypot(max(front_m,rear_m),width_m/2)
    disk_slack = minimum-radius-padding
    disk_clear = route_inside and disk_slack > 0
    rectangles_clear = route_inside and minimum_rectangle > 0
    rotations = []
    rotation_count = 0
    rotations_clear = disk_clear
    if rectangles_clear and not disk_clear:
        for i,p in enumerate(path):
            previous = path[i-1]
            following = path[(i+1)%len(path)]
            incoming = atan2(p[1]-previous[1],p[0]-previous[0])
            outgoing = atan2(following[1]-p[1],following[0]-p[0])
            turn = remainder(outgoing-incoming,2*pi)
            if abs(abs(turn)-pi) <= 1e-12:
                rotations.append({'status':'AMBIGUOUS_HALF_TURN','clear':False,
                    'intervals_checked':0,'minimum_certified_slack_bound_m':None,
                    'witness_pose_xy_yaw':None,'vertex_index':i,'shortest_yaw_change_rad':turn})
                break
            result = _rotation_screen(corridor,p,incoming,incoming+turn,dimensions,padding,
                maximum_intervals=maximum_rotation_intervals-rotation_count,
                maximum_depth=MAX_ROTATION_DEPTH)
            rotation_count += result['intervals_checked']
            rotations.append(dict(result,vertex_index=i,shortest_yaw_change_rad=turn))
            if not result['clear']:
                break
        rotations_clear = len(rotations) == len(path) and all(v['clear'] for v in rotations)
    status = ('ROUTE_OUTSIDE_OR_TOUCHES_CORRIDOR' if not route_inside else
        'TANGENT_TRANSLATION_SCREEN_FAILED' if not rectangles_clear else
        'ALL_HEADING_DISK_ENVELOPE_CLEAR_FLOAT_SCREEN' if disk_clear else
        'TANGENT_TRANSLATION_AND_SPECIFIED_YAW_FAMILY_CLEAR_FLOAT_SCREEN' if rotations_clear else
        'ROTATION_ENVELOPE_UNRESOLVED')
    return {'schema':'lapsim.approximate-cone-route-clearance-diagnostic.v1',
        'status':status,'scope':'APPROXIMATE_CONE_POLYLINE_CHORD_ROUTE_DIAGNOSTIC_ONLY',
        'route_chords_checked':len(edges),'boundary_edges':len(left)+len(right),
        'route_boundary_pairs_checked':pair_count,'maximum_route_boundary_pairs':maximum_pairs,
        'maximum_tangent_translation_checks':1000,'route_inside_approximate_corridor':route_inside,
        'minimum_route_boundary_distance_m':minimum,'nearest_boundary_pair':nearest,
        'body_dimensions_scope':'CALLER_DECLARED_NOT_MEASURED_OR_PROFILE_QUALIFIED',
        'front_extent_m':front_m,'rear_extent_m':rear_m,'vehicle_width_m':width_m,
        'safety_margin_m':safety_margin_m,'map_uncertainty_m':map_uncertainty_m,
        'tracking_allowance_m':tracking_allowance_m,'source_arc_allowance_m':source_arc_allowance_m,
        'numerical_allowance_m':ROUNDING_ALLOWANCE_M,'total_scalar_padding_m':padding,
        'disk_radius_m':radius,'disk_envelope_slack_m':disk_slack,
        'all_heading_disk_envelope_clear':disk_clear,
        'collision_proven_by_disk_bound_failure':False,
        'minimum_tangent_translation_slack_m':minimum_rectangle,
        'tangent_translation_witness':rectangle_witness,
        'tangent_translation_envelopes_clear':rectangles_clear,
        'specified_junction_rotations_clear':rotations_clear,
        'tangent_and_junction_heading_basis':'PARENT_CHORD_HEADINGS_NOT_FLOATING_SUBDIVISION_HEADINGS',
        'junction_rotation_scope':'STATIC_SHORTEST_YAW_FAMILIES_AT_EXACT_VERTICES_NOT_DRIVABLE_TURNS',
        'junction_rotations_covered_by_all_heading_disk':disk_clear,
        'maximum_rotation_intervals':maximum_rotation_intervals,
        'maximum_rotation_depth':MAX_ROTATION_DEPTH,'rotation_intervals_checked':rotation_count,
        'junction_rotation_records':rotations,
        'junction_yaw_dynamics_provided':False,'continuous_source_arc_clearance_proven':False,
        'rigorous_roundoff_proof':False,'cone_base_radius_or_survey_accuracy_verified':False,
        'qualification_or_execution_authority':False}


def screen_fsg_source_chord_reference(reference_raw,bundle_raw,cones_raw,*,
        front_m,rear_m,width_m,safety_margin_m,map_uncertainty_m,
        tracking_allowance_m,maximum_pairs=MAX_PAIRS,
        maximum_rotation_intervals=MAX_ROTATION_INTERVALS):
    """Verify exact local source recipe, then screen its unchanged coarse route.

    Linear subdivision leaves this swept route unchanged. The inherited arc
    spatial estimate is an extra declared allowance, not a proved arc envelope
    or station/heading-error bound. No replacement line or admission is created.
    """
    candidate = verify_fsg_source_chord_reference(reference_raw,bundle_raw,cones_raw)
    value = candidate.payload()
    source = construct_fsg_course(bundle_raw,cones_raw)
    track = source.source_track
    points = tuple(zip(track.x_m[:-1],track.y_m[:-1]))
    index = value['phase']['source_cell_index']
    loop = (tuple(value['phase']['reference_start_xy_m']),)+points[index+1:]+points[:index+1]
    if value['phase']['source_cell_fraction'] == 0.:
        loop = loop[:-1]
    # Verified reference cells are subdivisions of these very same saved
    # chords, not a new fitted/downsampled route. Account for the observed
    # floating residual when using the parent chords for the bounded screen.
    geometry = value['geometry']
    sampled = tuple(zip(geometry['x_m'][:-1],geometry['y_m'][:-1]))
    counts = tuple(max(1,ceil(hypot(*g.sub(b,a))/value['recipe']['maximum_step_m']))
                   for a,b in g.segments(loop))
    require(sum(counts) == len(sampled), 'Exact verified parent-chord subdivision count required')
    cursor = 0
    residual = 0.
    for (a,b),count in zip(g.segments(loop),counts):
        for p in sampled[cursor:cursor+count]:
            residual = max(residual,rg._point_segment_distance(p,a,b))
        cursor += count
    require(residual <= ROUNDING_ALLOWANCE_M,
        'Verified sampled route differs from parent chords beyond numerical allowance')
    result = screen_closed_route(loop,source.frame_dict(),front_m=front_m,rear_m=rear_m,
        width_m=width_m,safety_margin_m=safety_margin_m,map_uncertainty_m=map_uncertainty_m,
        tracking_allowance_m=tracking_allowance_m,maximum_pairs=maximum_pairs,
        maximum_rotation_intervals=maximum_rotation_intervals,
        source_arc_allowance_m=value['recipe']['source_arc_to_saved_chord_floating_bound_m'])
    result.update(reference_raw_sha256=sha256(reference_raw).hexdigest(),
        reference_geometry_sha256=value['geometry_sha256'],source_geometry_sha256=source.geometry_sha256,
        source_frame_sha256=value['source_frame_sha256'],source_bundle_sha256=source.bundle_raw_sha256,
        source_cones_sha256=source.cones_raw_sha256,
        sampled_reference_cells_checked=len(sampled),
        route_representation='EXACT_SOURCE_RECIPE_PARENT_CHORDS_NOT_FITTED_OR_DOWNSAMPLED',
        maximum_sample_to_parent_chord_residual_m=residual,
        source_arc_allowance_is_spatial_estimate_not_proof=True,
        source_arc_or_dynamics_qualified=False,reference_is_modified=False,
        native_reference_compatible=False,heldout_results_used=False,awards=None)
    return result
