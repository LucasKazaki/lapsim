"""Explicit FSG source-chord diagnostic, outside the admitted reference path.

No optimization, continuous vehicle clearance, original producer authentication,
mission completion or native execution is supplied by this geometry component.
"""
from dataclasses import dataclass
import json
from math import atan2, ceil, cos, hypot, isfinite, pi, remainder, sin

from .course import construct_fsg_course
from . import _fsi_geometry as g

SCHEMA = 'lapsim.fsg-source-chord-reference-candidate.v1'
MAX_BYTES = 2 * 1024 * 1024
MAX_SAMPLES = 5000
MAX_COARSE_PAIRS = 300000
MIN_CHORD_M = 1e-5


def require(value, message):
    if not value:
        raise ValueError(message)


def point(value):
    require(type(value) in (tuple, list) and len(value) == 2 and
        all(type(v) in (int, float) and isfinite(v) and abs(v) <= 10000 for v in value),
        'Two finite bounded builtin coordinates required')
    return tuple(value)


def metadata(raw):
    """Read only the fixed pinned file's two declared numeric metadata blocks."""
    lines = raw.decode('utf-8').splitlines()
    def block(name):
        start = lines.index(name + ':') + 1
        end = start
        while end < len(lines) and lines[end].startswith((' ', '-')):
            end += 1
        return lines[start:end]
    device = block('tk_device')
    require(len(device) == 4 and all(device[i].startswith('- - ') and
        device[i+1].startswith('  - ') for i in (0, 2)), 'Exact source timing-point structure required')
    ends = tuple(point((float(device[i][4:]), float(device[i+1][4:]))) for i in (0, 2))
    pose = block('starting_pose_front_wing')
    require(len(pose) == 3 and all(s.startswith('- ') for s in pose), 'Complete source front-wing pose required')
    pose = tuple(float(s[2:]) for s in pose)
    require(all(isfinite(v) and abs(v) <= 10000 for v in pose), 'Finite source pose values required')
    return ends, pose


def map_point(frame, value):
    transform = frame['source_to_course_SE2']
    angle = transform['rotation_rad']
    x, y = point(value)
    require(transform['scale'] == 1., 'Unscaled source frame required')
    return (cos(angle)*x-sin(angle)*y+transform['translation_x_m'],
            sin(angle)*x+cos(angle)*y+transform['translation_y_m'])


def source_crossing(points, ends):
    """Locate one transversal finite crossing; never a lap or timing receipt."""
    a, b = ends
    gate_delta = g.sub(b, a)
    require(hypot(*gate_delta) > MIN_CHORD_M, 'Nondegenerate source timing segment required')
    found = []
    for i, (p, q) in enumerate(g.segments(points)):
        delta = g.sub(q, p)
        require(hypot(*delta) >= MIN_CHORD_M, 'Nondegenerate saved source chord required')
        den = g.cross(delta, gate_delta)
        if abs(den) <= 1e-12 * max(1., hypot(*delta)*hypot(*gate_delta)):
            require(not g._hit(p, q, a, b), 'Timing segment overlaps/touches a nontransversal source chord')
            continue
        t = g.cross(g.sub(a, p), gate_delta)/den
        u = g.cross(g.sub(a, p), delta)/den
        if 0 <= t < 1 and 0 <= u <= 1:
            if t == 0.:
                before = g.cross(g.sub(points[i-1], a), gate_delta)
                after = g.cross(g.sub(q, a), gate_delta)
                require(before*after < 0., 'Source gate vertex touch is not a transversal crossing')
            found.append((i, t, (p[0]+t*delta[0], p[1]+t*delta[1])))
    require(len(found) == 1, 'Exactly one transversal finite source timing-segment crossing required')
    return found[0]


def screen_coarse_loop(points):
    require(3 <= len(points) <= 1000, 'Bounded coarse source loop required')
    edges = g.segments(points)
    lengths = tuple(hypot(*g.sub(b, a)) for a, b in edges)
    require(all(v >= MIN_CHORD_M for v in lengths), 'Degenerate source chord')
    for i, (a, b) in enumerate(edges):
        c, d = edges[i-1]
        require(g.dot(g.sub(b, a), g.sub(d, c))/(lengths[i]*lengths[i-1]) > -1+1e-8,
                'Source-chord loop folds back')
    pairs = 0
    for i, (a, b) in enumerate(edges):
        for j in range(i+2, len(edges)):
            if i == 0 and j == len(edges)-1:
                continue
            pairs += 1
            require(pairs <= MAX_COARSE_PAIRS, 'Coarse topology pair budget exhausted')
            c, d = edges[j]
            if (max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]) or
                max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1])):
                continue
            require(not g._hit(a, b, c, d), 'Nonlocal source chords intersect/touch')
    return pairs


def sample_chords(points, maximum_step_m):
    edges = g.segments(points)
    counts = tuple(max(1, ceil(hypot(*g.sub(b, a))/maximum_step_m)) for a, b in edges)
    require(sum(counts) <= MAX_SAMPLES, 'Sample cap exceeded before allocation; no coarser fallback')
    sampled = []
    for (a, b), count in zip(edges, counts):
        for i in range(count):
            # Preserve every existing vertex exactly, not a recomputed t=0 view.
            sampled.append(a if i == 0 else (a[0]+i*(b[0]-a[0])/count, a[1]+i*(b[1]-a[1])/count))
    xy = sampled + [sampled[0]]
    stations = [0.]
    lengths = []
    for a, b in zip(xy, xy[1:]):
        length = hypot(*g.sub(b, a))
        require(MIN_CHORD_M <= length <= maximum_step_m+1e-10, 'Degenerate/oversized sampled chord')
        lengths.append(length)
        stations.append(stations[-1]+length)
    headings = [atan2(b[1]-a[1], b[0]-a[0]) for a, b in zip(xy, xy[1:])]
    curvature = [remainder(h-headings[i-1], 2*pi)/(.5*(lengths[i]+lengths[i-1]))
                 for i, h in enumerate(headings)]
    return {'model': 'sampled_polyline', 'closed': True, 'distance_m': stations,
            'x_m': [p[0] for p in xy], 'y_m': [p[1] for p in xy], 'curvature_per_m': curvature}


@dataclass(frozen=True, slots=True)
class FsgSourceChordReference:
    """Immutable diagnostic bytes; neither NumericalReference nor an admission."""
    raw: bytes

    def __post_init__(self):
        require(type(self.raw) is bytes and 0 < len(self.raw) <= MAX_BYTES,
                'Bounded immutable diagnostic bytes required; direct construction grants no trust')
        value = json.loads(self.raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
        require(type(value) is dict and value.get('schema') == SCHEMA and
            value.get('status') == 'SOURCE_CHORD_DIAGNOSTIC_UNQUALIFIED' and
            value.get('role') == 'development' and value.get('qualification_or_execution_authority') is False and
            all(type(value.get(k)) is dict for k in ('geometry', 'gate_candidate', 'phase', 'recipe', 'qualification')) and
            all(value['qualification'].get(k) is False for k in (
                'optimized', 'vehicle_clearance_screened', 'steering_or_dynamics_qualified',
                'rigorous_roundoff_proven', 'authenticated_original_producer', 'native_reference_compatible')) and
            g.canonical(value).encode() == self.raw,
            'Canonical unqualified diagnostic schema required; verify against source before trusting consistency')

    def payload(self):
        return json.loads(self.raw)

    def forward_crossing(self, before, after):
        """Finite directed intersection only: no time, state, energy or lap award."""
        a, b = point(before), point(after)
        gate = self.payload()['gate_candidate']
        origin, normal = point(gate['origin_xy_m']), point(gate['forward_unit'])
        require(abs(hypot(*normal)-1) <= 1e-12 and
            type(gate['finite_half_width_m']) in (int, float) and
            isfinite(gate['finite_half_width_m']) and gate['finite_half_width_m'] > 0,
            'Finite unit source gate required')
        d0, d1 = g.dot(g.sub(a, origin), normal), g.dot(g.sub(b, origin), normal)
        if not d0 < 0 <= d1:
            return None
        fraction = -d0/(d1-d0)
        p = (a[0]+fraction*(b[0]-a[0]), a[1]+fraction*(b[1]-a[1]))
        tangent = (-normal[1], normal[0])
        if abs(g.dot(g.sub(p, origin), tangent)) > gate['finite_half_width_m']:
            return None
        return {'fraction': fraction, 'point_xy_m': list(p),
                'scope': 'DIAGNOSTIC_GEOMETRY_ONLY_NOT_MISSION_COMPLETION'}


def construct_fsg_source_chord_reference(bundle_raw, cones_raw, *, maximum_step_m=.1):
    require(type(maximum_step_m) in (int, float) and isfinite(maximum_step_m) and
        .05 <= maximum_step_m <= .5, 'Explicit finite 0.05 to 0.5 m maximum chord step required')
    source = construct_fsg_course(bundle_raw, cones_raw)
    frame = source.frame_dict()
    upstream, pose = metadata(cones_raw)
    ends = tuple(map_point(frame, p) for p in upstream)
    track = source.source_track
    points = tuple(zip(track.x_m[:-1], track.y_m[:-1]))
    i, fraction, intersection = source_crossing(points, ends)
    delta = g.sub(points[(i+1) % len(points)], points[i])
    gate_delta = g.sub(ends[1], ends[0]);span = hypot(*gate_delta)
    normal = (-gate_delta[1]/span, gate_delta[0]/span)
    if g.dot(delta, normal) < 0:
        normal = (-normal[0], -normal[1])
    require(g.dot(delta, normal) > 1e-8, 'Transversal ordered-source gate direction required')
    # Rotate a separate closed chord view; original arrays remain untouched.
    loop = (intersection,) + points[i+1:] + points[:i+1]
    if fraction == 0.:
        loop = loop[:-1]  # Exact existing vertex, not a snapped near-vertex crossing.
    pairs = screen_coarse_loop(loop)
    geometry = sample_chords(loop, maximum_step_m)
    seam_gap = hypot(track.x_m[-1]-track.x_m[0], track.y_m[-1]-track.y_m[0])
    bound = max(abs(k)*ds*ds/8 for k, ds in zip(track.curvature_per_m, track.cell_length_m))
    bound += frame['maximum_grid_xy_error_m'] + seam_gap
    gate = {'schema': 'lapsim.fsg-source-tk-device-gate-candidate.v1',
        'upstream_endpoints_xy_m': [list(p) for p in upstream], 'endpoints_xy_m': [list(p) for p in ends],
        'origin_xy_m': [.5*(a+b) for a, b in zip(*ends)], 'forward_unit': list(normal),
        'finite_half_width_m': .5*span,
        'orientation_basis': 'ORDERED_SAVED_SOURCE_CHORD_AT_UNIQUE_TRANSVERSAL_CROSSING',
        'source_starting_pose_front_wing_raw': list(pose), 'front_wing_pose_used_as_vehicle_state': False,
        'official_or_vehicle_start_semantics_verified': False,
        'scope': 'SOURCE_TK_DEVICE_SEGMENT_INTERPRETATION_NOT_SURVEY_OR_OFFICIAL_TIMING_AUTHORITY'}
    value = {'schema': SCHEMA, 'status': 'SOURCE_CHORD_DIAGNOSTIC_UNQUALIFIED', 'role': 'development',
        'source_bundle_sha256': source.bundle_raw_sha256, 'source_cones_sha256': source.cones_raw_sha256,
        'source_geometry_sha256': source.geometry_sha256, 'source_frame': frame, 'source_frame_sha256': g.digest(frame),
        'geometry': geometry, 'geometry_sha256': g.digest(geometry), 'gate_candidate': gate,
        'phase': {'source_cell_index': i, 'source_cell_fraction': fraction,
            'source_arc_station_estimate_at_chord_crossing_m': track.distance_m[i]+fraction*track.cell_length_m[i],
            'station_estimate_basis': 'LINEAR_ARC_STATION_INTERPOLATION_AT_CHORD_FRACTION_NOT_ANALYTIC_ARC_GATE_INTERSECTION',
            'source_arc_phase_is_exact': False,
            'source_arc_station_error_bound_supplied': False,
            'source_gate_cell_curvature_per_m': track.curvature_per_m[i],
            'source_gate_cell_arc_length_m': track.cell_length_m[i],
            'reference_start_xy_m': list(intersection), 'reference_start_station_m': 0.,
            'source_seam_is_timing_gate': False, 'source_gate_cell_is_straight': track.curvature_per_m[i] == 0.},
        'recipe': {'method': 'SAVED_SOURCE_CHORDS_LINEAR_SUBDIVISION_AND_GATE_ROTATION_V1',
            'maximum_step_m': maximum_step_m, 'maximum_cells': MAX_SAMPLES,
            'source_endpoint_closure_adjustment_m': seam_gap,
            'source_arc_to_saved_chord_floating_bound_m': bound,
            'subdivision_improves_source_arc_error_bound': False,
            'curvature': 'WRAPPED_ADJACENT_CHORD_HEADING_CHANGE_OVER_MEAN_CHORD_LENGTH',
            'coarse_self_intersection_pairs_checked': pairs, 'maximum_coarse_pairs': MAX_COARSE_PAIRS},
        'qualification': {'optimized': False, 'vehicle_clearance_screened': False,
            'steering_or_dynamics_qualified': False, 'rigorous_roundoff_proven': False,
            'authenticated_original_producer': False, 'native_reference_compatible': False},
        'heldout_results_used': False, 'awards': None, 'qualification_or_execution_authority': False}
    raw = g.canonical(value).encode()
    require(0 < len(raw) <= MAX_BYTES, 'Bounded source reference diagnostic required')
    return FsgSourceChordReference(raw)


def verify_fsg_source_chord_reference(raw, bundle_raw, cones_raw):
    """Rebuild exact local data consistency; not authentication or qualification."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'Bounded immutable candidate required')
    value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
    require(type(value) is dict and value.get('schema') == SCHEMA and
            g.canonical(value).encode() == raw, 'Canonical diagnostic schema required')
    require(type(value.get('recipe')) is dict, 'Complete candidate recipe required')
    step = value['recipe'].get('maximum_step_m')
    rebuilt = construct_fsg_source_chord_reference(bundle_raw, cones_raw, maximum_step_m=step)
    require(rebuilt.raw == raw, 'Candidate differs from exact source/gate/sampling recipe')
    return rebuilt


def _unique(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, 'Duplicate candidate JSON key')
        result[name] = value
    return result


def _nonfinite(value):
    raise ValueError('Nonfinite candidate JSON constant')
