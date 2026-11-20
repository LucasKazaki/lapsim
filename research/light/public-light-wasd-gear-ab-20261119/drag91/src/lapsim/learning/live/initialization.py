"""Exact retained RWD-LSD initialization recipe using the genuine Light classes.

This is a simulation assumption set, not hardware calibration. No constructor
runs on import. Input bytes must match the independent source pins below.
"""
from dataclasses import asdict, dataclass, fields, MISSING
from hashlib import sha256
import json
from math import atan2

from lapsim_light_core.actuation import ActuationConfig
from lapsim_light_core.lsd_contract import ARITHMETIC_CONTRACT
from lapsim_light_core.conditions import PlanarEnvironment, PlanarRoad
from lapsim_light_core.planar import PlanarState, PlanarVehicleConfig
from lapsim_light_core.powered_planar import PoweredState
from lapsim_light_core.torque_light_forces import AeroAreas, LightForceConfig
from lapsim_light_core.torque_light_powered import LightPoweredConfig
from lapsim_light_core.torque_light_thermal import LumpedTireThermalConfig
from lapsim_light_core.torque_light_drs import AutomaticDrsPolicy
from lapsim_light_core.torque_light_combined import initialize_combined_light
from lapsim.courses.spatial_track import SpatialTrack
from ..cone_data import SideConeMap
from .lap_gate import MichiganGate, GEOMETRY_SHA256

PINS = {'profile': (1585, '40e18808696bea07a689580939df53fc933b8e316665a39ed4e82d1bfc230dda'), 'retained_fixture': (2107, '029e7894bbf113cd641648d3e9d2bc83c6d1d31caa102b90d86a2c10598bbd29'), 'course': (698, 'a4ed7fbcc850ab5ba9e03407990fee9b1daca720f26c1780f2b5cb78f5f4f3c8'), 'historical_case_data': (972, '7b813012ccbe0055526b87e850cac024772074436a8c50581f3732893eff5ca7'), 'cones': (3934, 'fbb250b366a314823931fb1081fc086b80472769fc36dc80475f8c017202170c')}
TOPOLOGY = 'synthetic_viscous_regularized_torque_bias_rwd_lsd_r38'
ZERO_LEDGERS = (
    'wheel_work_j', 'conversion_loss_j', 'contact_dissipation_j',
    'friction_brake_work_j', 'external_work_j', 'driver_proxy_impulse_ns',
    'tire_longitudinal_impulse_ns', 'absolute_contact_force_error_ns',
    'wheel_stop_dissipation_j', 'integration_substeps', 'integration_trials',
    'wheel_stop_events', 'differential_heat_j',
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, default=asdict)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def _object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate input field')
        obj[key] = value
    return obj


def _decode(name, raw):
    size, pin = PINS[name]
    if type(raw) is not bytes or len(raw) != size or sha256(raw).hexdigest() != pin:
        raise ValueError('independent input pin differs: ' + name)
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def _complete(cls, values):
    if set(values) != {f.name for f in fields(cls)}:
        raise ValueError('complete explicit constructor schema differs: ' + cls.__name__)
    result = cls(**values)
    # The genuine constructors may validate but must not supply or change values.
    if canonical(asdict(result)) != canonical(values):
        raise ValueError('constructor changed selected values: ' + cls.__name__)
    return result


@dataclass(frozen=True, slots=True)
class InitialPlant:
    settings: LightPoweredConfig
    thermal: LumpedTireThermalConfig
    drs: AutomaticDrsPolicy
    actuation: ActuationConfig
    environment: PlanarEnvironment
    state: object
    track: SpatialTrack
    gate: MichiganGate
    cone_map: SideConeMap
    profile: dict
    context_sha256: str
    construction_record: dict


def construct(raws):
    """One physical construction, with no candidate-supplied expected state."""
    if type(raws) is not dict or set(raws) != set(PINS):
        raise ValueError('exact complete pinned input set required')
    parsed = {name: _decode(name, raw) for name, raw in raws.items()}
    p, donor, course, historical = (parsed[k] for k in
                                  ('profile', 'retained_fixture', 'course', 'historical_case_data'))
    case = historical['case']
    if case['course_bundle'] != course:
        raise ValueError('retained Case/course mismatch')
    if p['architecture'] != TOPOLOGY or p['actuation']['topology_id'] != TOPOLOGY:
        raise ValueError('explicit LSD baseline required; old open evidence is not reusable')
    if not (case['grip'] == 1 and case['patch'] is False and case['reverse'] is False
            and case['mirror'] is False and case['initial_offset_m'] == 0
            and case['regen_available'] is True and case['friction_fallback'] is True
            and case['initial_soc'] == p['policy']['initial_soc']
            and case['pack_voltage_v'] == p['actuation']['pack_voltage_v']):
        raise ValueError('unsupported Case; no implicit perturbation recipe')
    # This exact geometry is shared by construction, private scoring and cones.
    g = course['geometry']
    geometry = {k: g[k] for k in ('closed', 'distance_m', 'x_m', 'y_m', 'curvature_per_m')}
    if g['model'] != 'piecewise_constant_curvature_arcs' or g['closed'] is not True:
        raise ValueError('closed coherent-arc course required')
    if digest(geometry) != course['geometry_sha256'] or course['geometry_sha256'] != GEOMETRY_SHA256:
        raise ValueError('normalized geometry mismatch')
    track = SpatialTrack(**{k: tuple(v) if isinstance(v, list) else v for k, v in geometry.items()})
    cone_map = SideConeMap.from_bytes(raws['cones'])
    if (cone_map.reference_course_sha256 != PINS['course'][1]
            or cone_map.course_id != course['course_id']
            or cone_map.direction != course['travel_direction'] or cone_map.reversed):
        raise ValueError('cone frame/direction/course mismatch')
    gate = MichiganGate(raws['course'])
    v = json.loads(canonical(donor['values']))
    label = ('r07 RWD profile projection with retained provisional FSI Light extras; '
             'no measured RWD calibration; donor ' + PINS['retained_fixture'][1])
    s = v['settings']
    s['forces']['plant'] = p['vehicle']
    s['provenance'] = s['forces']['provenance'] = label
    v['thermal']['provenance'] = v['drs_policy']['provenance'] = label
    car = _complete(PlanarVehicleConfig, p['vehicle'])
    act = _complete(ActuationConfig, p['actuation'])
    force = s['forces']
    forces = LightForceConfig(car, _complete(AeroAreas, force['closed']),
                             _complete(AeroAreas, force['open']), force['cg_height_m'],
                             force['front_roll_moment_fraction'], force['provenance'])
    settings = LightPoweredConfig(forces, s['load_feedback_time_constant_s'],
                                  s['provenance'], s['feedback_period_s'])
    if settings.feedback_period_s != .001:
        raise ValueError('genuine 1ms feedback clock required')
    thermal = _complete(LumpedTireThermalConfig, v['thermal'])
    drs = _complete(AutomaticDrsPolicy, v['drs_policy'])
    env = v['environment']
    if env['drag_area_m2'] != 0 or env['road']['patches'] != [] or env['road']['valid_domain'] is not None:
        raise ValueError('retained one-owner aero/uniform-road recipe differs')
    road = _complete(PlanarRoad, {**env['road'], 'patches': tuple()})
    environment = _complete(PlanarEnvironment, {**env, 'road': road})
    heading = atan2(track.y_m[1] - track.y_m[0], track.x_m[1] - track.x_m[0]) - (
        track.curvature_per_m[0] * track.cell_length_m[0] / 2)
    speed, radius = p['policy']['initial_speed_mps'], car.wheel_radius_m
    # This new recipe is explicitly standing; retained rolling results stay historical.
    if type(speed) not in (int, float) or speed != 0.:
        raise ValueError('standing-start profile requires exactly zero initial speed')
    # Freeze the complete original literal-zero state schema, never infer from a candidate snapshot.
    fs = {f.name: f for f in fields(PoweredState)}
    if set(fs) != {'plant', 'actuator_memory_nm', 'pack_energy_j', *ZERO_LEDGERS}:
        raise ValueError('unsupported complete powered-state schema')
    if any(type(fs[k].default) not in (float, int) or fs[k].default != 0 for k in ZERO_LEDGERS):
        raise ValueError('source fresh-zero ledger defaults changed')
    for k in ('v_mps', 'yaw_rate_rad_s'):
        f = next(f for f in fields(PlanarState) if f.name == k)
        if f.default != 0 or type(f.default) not in (float, int):
            raise ValueError('source initial planar defaults differ')
    plant = _complete(PlanarState, dict(x_m=track.x_m[0], y_m=track.y_m[0],
        heading_rad=heading, u_mps=speed, v_mps=0., yaw_rate_rad_s=0.,
        wheel_speeds_rad_s=(speed / radius,) * 4))
    if (plant.u_mps != 0. or plant.v_mps != 0. or plant.yaw_rate_rad_s != 0.
            or plant.wheel_speeds_rad_s != (0.,) * 4):
        raise ValueError('standing-start body and wheels must all be at rest')
    powered = PoweredState(plant=plant, actuator_memory_nm=(0.,) * 4,
        pack_energy_j=case['initial_soc'] * act.pack_capacity_j,
        **{k: fs[k].default for k in ZERO_LEDGERS})
    initial = donor['standing_initial']
    if (initial['load_longitudinal_mps2'] != 0 or initial['load_lateral_mps2'] != 0
            or initial['actuator_memory_nm'] != [0., 0., 0., 0.]):
        raise ValueError('retained fresh load/motor memory changed')
    state = initialize_combined_light(settings, thermal, drs, act, powered, environment,
        initial_temperature_c=initial['temperature_c'], automatic_drs_enabled=True,
        wheel_radii_m=(radius,) * 4, load_longitudinal_mps2=0., load_lateral_mps2=0.)
    if (asdict(state.thermal.light.powered) != asdict(powered)
            or state.thermal.light.feedback_ticks != 0 or state.drs.ticks != 0
            or state.thermal.thermal.ticks != 0 or state.last_signals is not None):
        raise ValueError('fresh complete initial state changed')
    record = dict(schema='lapsim.driver-lsd-construction.standing.v1', input_pins=PINS,
        start_mode='standing', timing_origin='initial seam at feedback tick zero; launch included',
        lsd_arithmetic_contract=ARITHMETIC_CONTRACT,
        settings=asdict(settings), thermal=asdict(thermal), drs=asdict(drs),
        actuation=asdict(act), environment=asdict(environment), state=asdict(state),
        geometry_sha256=GEOMETRY_SHA256, cones_sha256=cone_map.sha256,
        cone_labeling_sha256=cone_map.labeling_sha256,
        command_model='held_equal_half_carrier_input; passive_LSD_transfer_output_only',
        qualification='synthetic_unvalidated; source identity is not runtime admission')
    return InitialPlant(settings, thermal, drs, act, environment, state, track, gate,
                        cone_map, p, digest(record), record)