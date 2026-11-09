"""Pinned source-arc pose clearance and synthetic steering-proxy diagnostic.

No new racing line, car calibration, gate/mission/provider or execution authority.
The existing guidance uses chords; this separate arc pose family is not a claim
that its actual driver or vehicle follows the reconstructed analytic tangents.
"""
from math import atan, atan2, cos, hypot, isfinite, pi, remainder, sin, tan

from . import _fsi_geometry as g
from .course import SourceTrack, construct_fsg_course
from .fsg_clearance import screen_closed_route, MAX_PAIRS, MAX_ROTATION_INTERVALS
from .fsg_reference import require

MAX_CELLS = 1000
GRID_POSITION_TOLERANCE_M = 1e-7


def _validated_track(track):
    require(type(track) is SourceTrack and track.closed is True,
        'Closed bounded source arc track required')
    channels = (track.distance_m,track.x_m,track.y_m,track.curvature_per_m)
    require(all(type(v) is tuple for v in channels) and
        3 <= track.cell_count <= MAX_CELLS and
        len(track.distance_m) == len(track.x_m) == len(track.y_m) == track.cell_count+1 and
        all(type(v) in (int,float) and isfinite(v) and abs(v) <= 10000 for row in channels for v in row),
        'Finite bounded source arc channels required')
    require(track.distance_m[0] == track.x_m[0] == track.y_m[0] == 0. and
        all(0 < ds <= 10 and abs(k) <= 10 and abs(k*ds) < pi
            for ds,k in zip(track.cell_length_m,track.curvature_per_m)),
        'Initial tangent frame and bounded increasing arc stations required')


def _pose_at(start,curvature,station_m):
    """Stable exact-real constant-curvature formula, evaluated in floats."""
    x,y,heading = start
    half = .5*curvature*station_m
    chord = station_m*(sin(half)/half if half else 1.)
    return (x+chord*cos(heading+half),y+chord*sin(heading+half),heading+2*half)


def _arc_bounds(track,*,radius_m):
    """Integrate globally; bound every analytic arc against its saved chord.

    The linear interpolation error is <=|k|*ds^2/8 for unit-speed arcs. Endpoint
    discrepancy is added separately. The body transfer bound also includes the
    whole cell's tangent-heading difference, not merely its midpoint mismatch.
    Last parent chord ends at the first saved vertex; closure is not snapped in
    the analytic pose integration. These remain floating screens, not proofs of
    numerical roundoff or periodic exact closure.
    """
    _validated_track(track)
    require(type(radius_m) in (int,float) and isfinite(radius_m) and 0 <= radius_m <= 15,
        'Finite explicit body radius required')
    pose = (0.,0.,0.)
    rows = []
    maximum_grid_error = 0.
    for i,(ds,k) in enumerate(zip(track.cell_length_m,track.curvature_per_m)):
        end = _pose_at(pose,k,ds)
        saved_start = (track.x_m[i],track.y_m[i])
        saved_end = (track.x_m[i+1],track.y_m[i+1])
        parent_end = (track.x_m[(i+1)%track.cell_count],track.y_m[(i+1)%track.cell_count])
        start_error = hypot(pose[0]-saved_start[0],pose[1]-saved_start[1])
        end_error = hypot(end[0]-saved_end[0],end[1]-saved_end[1])
        maximum_grid_error = max(maximum_grid_error,start_error,end_error)
        chord = g.sub(parent_end,saved_start)
        require(hypot(*chord) >= 1e-5,'Nondegenerate saved parent chord required')
        chord_heading = atan2(chord[1],chord[0])
        midpoint_heading = pose[2]+k*ds/2
        midpoint_heading_error = abs(remainder(midpoint_heading-chord_heading,2*pi))
        heading_difference = midpoint_heading_error+abs(k)*ds/2
        endpoint_error = max(start_error,hypot(end[0]-parent_end[0],end[1]-parent_end[1]))
        spatial_bound = abs(k)*ds*ds/8+endpoint_error
        rotation_bound = 2*radius_m*sin(min(heading_difference,pi)/2)
        rows.append({'cell_index':i,'station_start_m':track.distance_m[i],'arc_length_m':ds,
            'curvature_per_m':k,'analytic_start_pose_xy_yaw':list(pose),
            'analytic_end_pose_xy_yaw':list(end),'parent_chord_heading_rad':chord_heading,
            'saved_grid_start_error_m':start_error,'saved_grid_end_error_m':end_error,
            'maximum_analytic_endpoint_to_parent_error_m':endpoint_error,
            'midpoint_heading_discrepancy_rad':midpoint_heading_error,
            'arc_heading_difference_bound_rad':heading_difference,
            'arc_to_parent_spatial_bound_m':spatial_bound,
            'body_rotation_displacement_bound_m':rotation_bound,
            'pose_transfer_bound_m':spatial_bound+rotation_bound})
        pose = end  # Carry the entire integrated pose; never reanchor to saved XY.
    require(maximum_grid_error <= GRID_POSITION_TOLERANCE_M,
        'Full saved source grid differs from global arc integration')
    return {'model':'GLOBAL_CONSTANT_CURVATURE_ARC_POSE_FAMILY_FROM_INITIAL_TANGENT',
        'initial_pose_xy_yaw':[0.,0.,0.],'cells':rows,
        'maximum_saved_grid_position_error_m':maximum_grid_error,
        'grid_position_tolerance_m':GRID_POSITION_TOLERANCE_M,
        'integrated_terminal_pose_xy_yaw':list(pose),'integrated_signed_turn_rad':pose[2],
        'closure_position_gap_m':hypot(pose[0],pose[1]),
        'wrapped_heading_seam_error_rad':remainder(pose[2],2*pi),
        'closure_snapped_or_exact_periodic_closure_proven':False,
        'body_radius_m':radius_m,
        'maximum_pose_transfer_bound_m':max(r['pose_transfer_bound_m'] for r in rows),
        'rigorous_roundoff_proof':False}


def _steering_proxy(track,*,wheelbase_m,maximum_steering_rad,curvature_limit_fraction):
    """Single-track amplitude arithmetic only; not actual CG/wheel steering.

    Shape validation does not authenticate or geometrically validate a track;
    the public FSG wrapper separately enforces source pins and full arc-grid
    consistency. Source anchor is not established as a rear-axle path.
    """
    _validated_track(track)
    require(type(wheelbase_m) in (int,float) and isfinite(wheelbase_m) and 0 < wheelbase_m <= 10 and
        type(maximum_steering_rad) in (int,float) and isfinite(maximum_steering_rad) and
        0 < maximum_steering_rad < pi/2 and
        type(curvature_limit_fraction) in (int,float) and isfinite(curvature_limit_fraction) and
        0 < curvature_limit_fraction <= 1,
        'Explicit finite synthetic steering proxy recipe required')
    hard_limit = tan(maximum_steering_rad)/wheelbase_m
    margin_limit = curvature_limit_fraction*hard_limit
    require(isfinite(hard_limit) and hard_limit > 0 and
        isfinite(margin_limit) and margin_limit > 0,
        'Derived finite positive steering proxy limits required')
    angles = tuple(atan(wheelbase_m*k) for k in track.curvature_per_m)
    margin_failures = []
    hard_failures = []
    jumps = []
    for i,(k,ds,angle) in enumerate(zip(track.curvature_per_m,track.cell_length_m,angles)):
        row = {'cell_index':i,'station_start_m':track.distance_m[i],
            'station_end_m':track.distance_m[i+1],'arc_length_m':ds,
            'signed_curvature_per_m':k,'signed_proxy_angle_rad':angle}
        if abs(k) > margin_limit:
            margin_failures.append(row)
        if abs(k) > hard_limit:
            hard_failures.append(dict(row))
        previous = (i-1)%track.cell_count
        if k != track.curvature_per_m[previous]:
            jumps.append({'from_cell_index':previous,'to_cell_index':i,
                'station_m':track.distance_m[i],'previous_curvature_per_m':track.curvature_per_m[previous],
                'next_curvature_per_m':k,'signed_proxy_angle_jump_rad':angle-angles[previous]})
    return {'model':'SINGLE_TRACK_GEOMETRIC_PROXY_NOT_PARALLEL_FRONT_OR_ACTUAL_CAR_STEERING',
        'wheelbase_m':wheelbase_m,'maximum_steering_rad':maximum_steering_rad,
        'curvature_limit_fraction':curvature_limit_fraction,
        'formula':'kappa_margin=fraction*tan(maximum_steering_rad)/wheelbase_m; proxy_angle=atan(wheelbase_m*kappa)',
        'hard_curvature_limit_per_m':hard_limit,'margin_curvature_limit_per_m':margin_limit,
        'maximum_absolute_source_curvature_per_m':max(abs(k) for k in track.curvature_per_m),
        'maximum_absolute_proxy_angle_rad':max(abs(a) for a in angles),
        'margin_violations':margin_failures,'hard_limit_violations':hard_failures,
        'margin_violating_arc_length_m':sum(r['arc_length_m'] for r in margin_failures),
        'margin_amplitude_screen_passed':not margin_failures,
        'curvature_jump_records':jumps,'finite_steering_rate_path_qualified':False,
        'path_anchor_established_as_rear_axle_or_cg':False,'actual_vehicle_steering_qualified':False}


def _clearance_transfer(parent_clear,slack,bound):
    require(type(parent_clear) is bool and
        all(type(v) in (int,float) and isfinite(v) for v in (slack,bound)) and bound >= 0,
        'Finite established parent clearance and nonnegative transfer bound required')
    lower = slack-bound
    return {'parent_translation_envelope_clear':parent_clear,
        'minimum_parent_translation_slack_m':slack,'maximum_pose_transfer_bound_m':bound,
        'minimum_arc_pose_clearance_lower_bound_m':lower,
        'continuous_arc_pose_clearance_float_screen_passed':parent_clear and lower > 0,
        'existing_inherited_spatial_arc_padding_retained_in_addition_to_transfer_bound':True,
        'static_vertex_rotation_results_used_as_trajectory':False,
        'rigorous_roundoff_proof':False,'actual_vehicle_or_native_qualified':False}


def screen_fsg_source_arcs(bundle_raw,cones_raw,*,front_m,rear_m,width_m,
        safety_margin_m,map_uncertainty_m,tracking_allowance_m,wheelbase_m,
        maximum_steering_rad,curvature_limit_fraction,maximum_pairs=MAX_PAIRS,
        maximum_rotation_intervals=MAX_ROTATION_INTERVALS):
    """Diagnostic only: real pinned geometry with explicitly assumed car inputs."""
    source = construct_fsg_course(bundle_raw,cones_raw)
    track = source.source_track
    proxy = _steering_proxy(track,wheelbase_m=wheelbase_m,
        maximum_steering_rad=maximum_steering_rad,curvature_limit_fraction=curvature_limit_fraction)
    frame = source.frame_dict()
    inherited = max(abs(k)*ds*ds/8 for k,ds in zip(track.curvature_per_m,track.cell_length_m))
    inherited += frame['maximum_grid_xy_error_m']+hypot(track.x_m[-1],track.y_m[-1])
    parent = screen_closed_route(tuple(zip(track.x_m[:-1],track.y_m[:-1])),frame,
        front_m=front_m,rear_m=rear_m,width_m=width_m,safety_margin_m=safety_margin_m,
        map_uncertainty_m=map_uncertainty_m,tracking_allowance_m=tracking_allowance_m,
        source_arc_allowance_m=inherited,maximum_pairs=maximum_pairs,
        maximum_rotation_intervals=maximum_rotation_intervals)
    geometry = _arc_bounds(track,radius_m=hypot(max(front_m,rear_m),width_m/2))
    require(abs(geometry['integrated_signed_turn_rad']+2*pi) <= 1e-8 and
        geometry['closure_position_gap_m'] <= GRID_POSITION_TOLERANCE_M,
        'Pinned clockwise source turn and floating closure checks required')
    transfer = _clearance_transfer(parent['tangent_translation_envelopes_clear'],
        parent['minimum_tangent_translation_slack_m'],geometry['maximum_pose_transfer_bound_m'])
    status = ('SOURCE_ARC_DIAGNOSTIC_UNQUALIFIED_STEERING_PROXY_FAILED'
        if not proxy['margin_amplitude_screen_passed'] else
        'SOURCE_ARC_DIAGNOSTIC_UNQUALIFIED_CLEARANCE_UNRESOLVED'
        if not transfer['continuous_arc_pose_clearance_float_screen_passed'] else
        'SOURCE_ARC_DIAGNOSTIC_UNQUALIFIED_RATE_MISSION_AND_NATIVE_REQUIREMENTS_OPEN')
    return {'schema':'lapsim.fsg-source-arc-pose-proxy-diagnostic.v1','status':status,
        'role':'development','source_bundle_sha256':source.bundle_raw_sha256,
        'source_cones_sha256':source.cones_raw_sha256,'source_geometry_sha256':source.geometry_sha256,
        'source_frame_sha256':g.digest(frame),'arc_geometry':geometry,
        'parent_chord_clearance':parent,'clearance_transfer':transfer,'steering_proxy':proxy,
        'scope':'SYNTHETIC_BODY_AND_SINGLE_TRACK_PROXY_ON_APPROXIMATE_CONE_SOURCE_GEOMETRY_ONLY',
        'source_or_existing_reference_modified':False,'source_arc_anchor_is_measured_vehicle_state':False,
        'existing_guidance_arc_following_verified':False,'arc_gate_phase_verified':False,
        'canonical_reference_or_native_mission_provider_supplied':False,
        'heldout_results_used':False,'awards':None,'qualification_or_execution_authority':False}
