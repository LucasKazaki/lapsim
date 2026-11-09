"""UNTESTED byte-pinned synthetic fixture construction, without plant evolution.

The historical moving initializer is provenance only. No course is selected,
line admitted, environment qualified or physical state advanced by this module.
"""
from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
from importlib.resources import files
from math import ceil, isfinite

from lapsim_light_core.actuation import ActuationConfig, AWD_TOPOLOGY_ID
from lapsim_light_core.conditions import PlanarEnvironment, PlanarRoad
from lapsim_light_core.planar import PlanarVehicleConfig
from lapsim_light_core.torque_light_drs import AutomaticDrsPolicy
from lapsim_light_core.torque_light_forces import AeroAreas, LightForceConfig
from lapsim_light_core.torque_light_powered import LightPoweredConfig
from lapsim_light_core.torque_light_thermal import LumpedTireThermalConfig
from lapsim_light_guidance.driver import StandingPoseDriverSettings

from .input_contracts import decode, digest, encode, exact, is_sha256, require


BASELINE_RAW_SHA256 = "cef3c04c808f3ab8dc0f767ec4a0f24865dcd67371ac45f52689c67a0e145d22"
BASELINE_CONFIGURATION_SHA256 = "782eaf45732856e77c77affa25d79b0aefbd7d62ebee8ce37e7835c7a52dfb9f"
FAMILY = "lapsim.portable-light-standing-fixture.v1"
MAX_BASELINE_BYTES = 128 * 1024
PARTIAL_PROFILE_FAMILY = "lapsim.portable-light-partial-profile-standing-fixture.v1"


def fixture_resource_bytes():
    """Read the explicit packaged resource when requested; no private lookup."""
    resource = files("lapsim_light_campaign").joinpath("baseline-configuration.json")
    with resource.open("rb") as stream:
        raw = stream.read(MAX_BASELINE_BYTES + 1)
    require(len(raw) <= MAX_BASELINE_BYTES and sha256(raw).hexdigest() == BASELINE_RAW_SHA256,
            "Packaged baseline resource identity differs")
    return raw


def _construct(cls, values, **typed):
    exact(values, {field.name for field in fields(cls)}, cls.__name__)
    require(typed.keys() <= values.keys(), "Unknown typed fixture override")
    return cls(**{**values, **typed})


@dataclass(frozen=True, slots=True)
class StandingFixture:
    settings: LightPoweredConfig
    thermal: LumpedTireThermalConfig
    drs_policy: AutomaticDrsPolicy
    actuation: ActuationConfig
    environment: PlanarEnvironment
    driver: StandingPoseDriverSettings
    configuration_sha256: str
    configuration_json: bytes

    @property
    def qualification_or_execution_authority(self):
        return False


def construct_standing_fixture(baseline_raw, *, reference_length_m, reference_geometry_sha256):
    """Construct exact synthetic parameters plus archived one-lap driver changes.

    The separately admitted reference identity is an input binding, not proof
    of authentication here. Neither an initial plant state nor a runner is
    constructed. Complete numerical environment/admission checks remain outside.
    """
    require(type(baseline_raw) is bytes and len(baseline_raw) <= MAX_BASELINE_BYTES and
            sha256(baseline_raw).hexdigest() == BASELINE_RAW_SHA256,
            "Exact retained parameter snapshot bytes required")
    require(type(reference_length_m) in (int, float) and 0 < reference_length_m <= 2200 and
            isfinite(reference_length_m) and is_sha256(reference_geometry_sha256),
            "Bounded explicit reference length and geometry identity required")
    saved = decode(baseline_raw, MAX_BASELINE_BYTES)
    exact(saved, {"schema", "body", "baseline_configuration_sha256", "provenance"}, "baseline snapshot")
    require(saved["schema"] == "ev.qualified-awd-configuration-parameter-copy.v1" and
            saved["baseline_configuration_sha256"] == BASELINE_CONFIGURATION_SHA256 and
            digest(saved["body"]) == BASELINE_CONFIGURATION_SHA256,
            "Historical parameter identity differs; no qualification is inherited")
    baseline = saved["body"]
    require(baseline["topology_id"] == AWD_TOPOLOGY_ID and baseline["availability"] == [True] * 4 and
            all(type(v) is bool for v in baseline["availability"]) and
            baseline["steering"] == "parallel_front_v1" and baseline["total_drive_cap_nm"] == 190.0 and
            baseline["equal_weights"] == [.25] * 4, "Exact independent four-motor AWD fixture required")
    values = baseline["values"]
    exact(values, {"settings", "thermal", "drs_policy", "actuation", "environment", "driver"},
          "baseline component inventory")
    force_values = values["settings"]["forces"]
    car = _construct(PlanarVehicleConfig, force_values["plant"])
    force = _construct(LightForceConfig, force_values, plant=car,
                       closed=_construct(AeroAreas, force_values["closed"]),
                       open=_construct(AeroAreas, force_values["open"]))
    settings = _construct(LightPoweredConfig, values["settings"], forces=force)
    thermal = _construct(LumpedTireThermalConfig, values["thermal"])
    drs = _construct(AutomaticDrsPolicy, values["drs_policy"])
    actuation = _construct(ActuationConfig, values["actuation"])
    road_values = values["environment"]["road"]
    require(road_values["patches"] == [] and road_values["valid_domain"] is None,
            "Pinned nominal road has no imported patch/domain")
    road = _construct(PlanarRoad, road_values, patches=())
    environment = _construct(PlanarEnvironment, values["environment"], road=road)
    physical = {"settings": asdict(settings), "thermal": asdict(thermal), "drs_policy": asdict(drs),
                "actuation": asdict(actuation), "environment": asdict(environment)}
    require(encode(physical) == encode({key: values[key] for key in physical}),
            "Constructed physical parameters differ from the pinned snapshot")
    # Same finite one-lap heuristic/overrides as the archived racing fixture.
    ticks = (ceil(reference_length_m / 3.) + 30) * 1000
    driver_values = dict(values["driver"])
    driver_values.update(initial_speed_mps=0., target_progress_m=reference_length_m,
                         maximum_simulated_time_s=ticks * .001,
                         maximum_control_steps=max(1, ceil(ticks / 10)),
                         maximum_internal_substeps=50000, reference_geometry="sampled_polyline")
    driver = _construct(StandingPoseDriverSettings, driver_values)
    body = {
        "family": FAMILY, "baseline_configuration_sha256": BASELINE_CONFIGURATION_SHA256,
        "values": {**physical, "driver": asdict(driver)},
        "reference": {"geometry_sha256": reference_geometry_sha256, "length_m": reference_length_m},
        "standing_initial": {"u_mps": 0., "v_mps": 0., "yaw_rate_rad_s": 0.,
                             "wheel_omega_rad_s": [0.] * 4, "actuator_memory_nm": [0.] * 4,
                             "pack_energy_j": 9000000., "temperature_c": 70.,
                             "load_longitudinal_mps2": 0., "load_lateral_mps2": 0., "clock_s": 0.},
        "historical_initializer_role": "PROVENANCE_ONLY_NEVER_USED_FOR_STANDING_START",
        "qualification_or_execution_authority": False,
    }
    return StandingFixture(settings, thermal, drs, actuation, environment, driver, digest(body), encode(body))


def construct_partial_profile_fixture(baseline_raw, *, resolved_manifest_raw,
        reviewed_resolved_manifest_raw_sha256, reference_length_m, reference_geometry_sha256):
    """Project only reviewed mass/geometry/density onto the unchanged baseline recipe.

    Ordinary defaults are consumed with their inherited labels. Closed-only aero
    and every unmapped field remain metadata; no ordinary model is imported.
    The resulting exact configuration needs its own native admission.
    """
    from .profile_projection import resolve_partial_profile, MAX_PROFILE_FIXTURE_BYTES

    projection = resolve_partial_profile(resolved_manifest_raw,
        reviewed_resolved_manifest_raw_sha256=reviewed_resolved_manifest_raw_sha256)
    baseline = construct_standing_fixture(baseline_raw, reference_length_m=reference_length_m,
        reference_geometry_sha256=reference_geometry_sha256)
    values = projection.values()
    length, front = values["chassis.wheelbase_m"], values["chassis.static_front_weight_fraction"]
    car = replace(baseline.settings.forces.plant, mass_kg=values["mass_kg"],
        cg_to_front_axle_m=length*(1-front), cg_to_rear_axle_m=length*front,
        front_track_m=values["chassis.front_track_width_m"], rear_track_m=values["chassis.rear_track_width_m"])
    forces = replace(baseline.settings.forces, plant=car, cg_height_m=values["chassis.cg_height_m"],
        provenance="PARTIAL explicit resolved-manifest mass/geometry projection; all other force assumptions synthetic baseline")
    settings = replace(baseline.settings, forces=forces)
    environment = replace(baseline.environment, air_density_kgpm3=values["air_density_kgpm3"])
    body = decode(baseline.configuration_json, MAX_BASELINE_BYTES)
    body["family"] = PARTIAL_PROFILE_FAMILY
    body["values"]["settings"] = asdict(settings)
    body["values"]["environment"] = asdict(environment)
    payload = projection.payload()
    # Every unchanged leaf is named, with its exact value still in body.values.
    changed = {target for field in payload["field_accounting"] for target in field["target_paths"]}
    changed.add("settings.forces.provenance")
    def leaves(value, prefix=""):
        if type(value) is dict and value:
            return [path for name, child in value.items()
                    for path in leaves(child, prefix + ("." if prefix else "") + name)]
        return [prefix]
    payload["retained_synthetic_baseline_paths"] = sorted(set(leaves(body["values"])) - changed)
    body["partial_profile_projection"] = payload
    raw = encode(body)
    require(len(raw) <= MAX_PROFILE_FIXTURE_BYTES, "Complete profiled fixture exceeds bounded metadata budget")
    return replace(baseline, settings=settings, environment=environment,
                   configuration_sha256=sha256(raw).hexdigest(), configuration_json=raw)


def validate_standing_fixture(fixture):
    """Rebuild the fixed recipe, including full profiled provenance; no stepping."""
    from .profile_projection import MAX_PROFILE_FIXTURE_BYTES

    require(type(fixture) is StandingFixture, "Exact standing fixture required")
    record = decode(fixture.configuration_json, MAX_PROFILE_FIXTURE_BYTES, canonical=True)
    require(digest(record) == fixture.configuration_sha256, "Fixture configuration digest differs")
    require(type(record.get("reference")) is dict, "Explicit fixture reference required")
    reference = record["reference"]
    exact(reference, {"geometry_sha256", "length_m"}, "fixture reference")
    arguments = dict(reference_length_m=reference["length_m"],
                     reference_geometry_sha256=reference["geometry_sha256"])
    if record.get("family") == PARTIAL_PROFILE_FAMILY:
        payload = record.get("partial_profile_projection")
        require(type(payload) is dict and type(payload.get("resolved_manifest_json")) is str,
                "Complete partial profile provenance required")
        rebuilt = construct_partial_profile_fixture(fixture_resource_bytes(),
            resolved_manifest_raw=payload["resolved_manifest_json"].encode("utf-8"),
            reviewed_resolved_manifest_raw_sha256=payload.get("resolved_manifest_raw_sha256"), **arguments)
    else:
        require(record.get("family") == FAMILY, "Unknown standing fixture family")
        rebuilt = construct_standing_fixture(fixture_resource_bytes(), **arguments)
    require(rebuilt.configuration_json == fixture.configuration_json,
            "Fixture declaration differs from exact baseline/partial-profile recipe")
    actual = {name: asdict(getattr(fixture, name)) for name in record["values"]}
    require(encode(actual) == encode(record["values"]), "Fixture objects differ from configuration")
    return record
