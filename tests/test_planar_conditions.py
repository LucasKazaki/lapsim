"""Wind and spatial-road checks for the Report II planar experiment inputs."""

from __future__ import annotations

from dataclasses import replace
from math import isclose, pi

import pytest

from lapsim.dynamics import (
    PlanarControls,
    PlanarEnvironment,
    PlanarRoad,
    PlanarState,
    PlanarVehicleConfig,
    RectangularGripPatch,
    RoadDomain,
    evaluate_planar_dynamics,
    run_planar_dynamics,
    step_planar_dynamics,
)


def synthetic_config() -> PlanarVehicleConfig:
    return PlanarVehicleConfig(
        mass_kg=300.0,
        yaw_inertia_kgm2=160.0,
        cg_to_front_axle_m=0.8,
        cg_to_rear_axle_m=0.8,
        front_track_m=1.2,
        rear_track_m=1.2,
        wheel_radius_m=0.2,
        wheel_inertia_kgm2=0.3,
        tire_mu=1.5,
        longitudinal_stiffness_n_per_slip=7000.0,
        cornering_stiffness_n_per_rad=8000.0,
    )


def rolling_state(speed_mps: float = 20.0, *, heading_rad: float = 0.0) -> PlanarState:
    return PlanarState(
        u_mps=speed_mps,
        heading_rad=heading_rad,
        wheel_speeds_rad_s=(speed_mps / 0.2,) * 4,
    )


def test_flat_still_air_and_zero_drag_area_recover_existing_core() -> None:
    config = synthetic_config()
    state = rolling_state(12.0)
    controls = PlanarControls(drive_torques_nm=(0.0, 0.0, 100.0, 100.0))
    explicit_default = PlanarEnvironment()
    assert evaluate_planar_dynamics(config, state, controls) == evaluate_planar_dynamics(
        config, state, controls, environment=explicit_default
    )
    default_run = run_planar_dynamics(config, state, (controls,) * 10, 0.01)
    explicit_run = run_planar_dynamics(
        config, state, (controls,) * 10, 0.01, environment=explicit_default
    )
    assert default_run == explicit_run
    assert default_run.road_valid
    assert default_run.invalid_road_queries == 0


def test_wind_aware_drag_uses_air_speed_and_ground_speed_for_power() -> None:
    config = synthetic_config()
    state = rolling_state()
    headwind = evaluate_planar_dynamics(
        config, state, PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_x_mps=-5.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    assert headwind.apparent_air_speed_mps == pytest.approx(25.0)
    assert headwind.aero_body_force_x_n == pytest.approx(-562.5)
    assert headwind.aero_power_w == pytest.approx(-11_250.0)
    assert headwind.external_power_w == pytest.approx(headwind.aero_power_w)
    assert abs(headwind.energy_balance_residual_w) < 1e-8

    tailwind = evaluate_planar_dynamics(
        config, state, PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_x_mps=5.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    assert tailwind.apparent_air_speed_mps == pytest.approx(15.0)
    assert tailwind.aero_body_force_x_n == pytest.approx(-202.5)
    assert tailwind.aero_power_w == pytest.approx(-4050.0)

    faster_tailwind = evaluate_planar_dynamics(
        config, state, PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_x_mps=30.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    assert faster_tailwind.aero_body_force_x_n == pytest.approx(90.0)
    assert faster_tailwind.aero_power_w == pytest.approx(1800.0)
    assert abs(faster_tailwind.energy_balance_residual_w) < 1e-8

    matched_wind = evaluate_planar_dynamics(
        config, state, PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_x_mps=20.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    assert matched_wind.apparent_air_speed_mps == 0.0
    assert matched_wind.aero_body_force_x_n == 0.0
    assert matched_wind.aero_power_w == 0.0


def test_world_wind_rotation_and_crosswind_force() -> None:
    config = synthetic_config()
    straight = evaluate_planar_dynamics(
        config, rolling_state(), PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_x_mps=-5.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    rotated = evaluate_planar_dynamics(
        config, rolling_state(heading_rad=pi / 2), PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_y_mps=-5.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    assert rotated.aero_body_force_x_n == pytest.approx(straight.aero_body_force_x_n)
    assert rotated.aero_body_force_y_n == pytest.approx(0.0, abs=1e-10)
    assert rotated.aero_power_w == pytest.approx(straight.aero_power_w)

    crosswind = evaluate_planar_dynamics(
        config, rolling_state(), PlanarControls(),
        environment=PlanarEnvironment(
            wind_world_y_mps=5.0, air_density_kgpm3=1.2, drag_area_m2=1.5
        ),
    )
    assert crosswind.air_relative_body_y_mps == -5.0
    assert crosswind.aero_body_force_y_n > 0.0
    assert crosswind.aero_body_force_x_n < 0.0
    assert abs(crosswind.energy_balance_residual_w) < 1e-8


def test_per_wheel_patch_changes_only_local_force_cap_and_yaw() -> None:
    config = synthetic_config()
    state = PlanarState(u_mps=12.0, wheel_speeds_rad_s=(60.0, 60.0, 70.0, 70.0))
    patch = RectangularGripPatch(
        x_min_m=-0.95, x_max_m=-0.65,
        y_min_m=-0.75, y_max_m=-0.45,
        friction_multiplier=0.2, material_id="assumed_low_grip",
    )
    environment = PlanarEnvironment(road=PlanarRoad(patches=(patch,)))
    baseline = evaluate_planar_dynamics(config, state, PlanarControls())
    patched = evaluate_planar_dynamics(
        config, state, PlanarControls(), environment=environment
    )
    assert [wheel.road_material_id for wheel in patched.wheels] == [
        "reference_pavement", "reference_pavement",
        "reference_pavement", "assumed_low_grip",
    ]
    assert patched.wheels[3].world_contact_x_m == pytest.approx(-0.8)
    assert patched.wheels[3].world_contact_y_m == pytest.approx(-0.6)
    assert patched.wheels[3].friction_limit_n == pytest.approx(
        0.2 * baseline.wheels[3].friction_limit_n
    )
    assert patched.wheels[2].friction_limit_n == baseline.wheels[2].friction_limit_n
    assert patched.wheels[3].local_force_x_n < baseline.wheels[3].local_force_x_n
    assert isclose(baseline.total_yaw_moment_nm, 0.0, abs_tol=1e-10)
    assert patched.total_yaw_moment_nm < 0.0
    assert abs(patched.energy_balance_residual_w) < 1e-8


def test_patch_query_uses_rotated_world_contact_position() -> None:
    config = synthetic_config()
    state = rolling_state(12.0, heading_rad=pi / 2)
    patch = RectangularGripPatch(
        x_min_m=0.45, x_max_m=0.75,
        y_min_m=-0.95, y_max_m=-0.65,
        friction_multiplier=0.5, material_id="rotated_patch",
    )
    result = evaluate_planar_dynamics(
        config, state, PlanarControls(),
        environment=PlanarEnvironment(road=PlanarRoad(patches=(patch,))),
    )
    rear_right = result.wheels[3]
    assert rear_right.world_contact_x_m == pytest.approx(0.6)
    assert rear_right.world_contact_y_m == pytest.approx(-0.8)
    assert rear_right.road_material_id == "rotated_patch"
    assert sum(w.road_material_id == "rotated_patch" for w in result.wheels) == 1


def test_invalid_domain_is_visible_even_when_initial_sample_is_valid() -> None:
    config = synthetic_config()
    state = rolling_state()
    environment = PlanarEnvironment(
        road=PlanarRoad(valid_domain=RoadDomain(-1.0, 0.95, -1.0, 1.0))
    )
    start = evaluate_planar_dynamics(
        config, state, PlanarControls(), environment=environment
    )
    assert start.road_valid
    run = run_planar_dynamics(
        config, state, (PlanarControls(),), 0.01, environment=environment
    )
    assert run.evaluations[0].road_valid
    assert not run.road_valid
    assert run.invalid_road_queries > 0
    with pytest.raises(ValueError, match="valid domain"):
        step_planar_dynamics(
            config, state, PlanarControls(), 0.01, environment=environment
        )


def test_road_violation_only_during_rk_substages_is_retained() -> None:
    # A nearly force-free car rotates one full turn in the output interval.
    # Its accepted boundary states are inside the rectangular road, while
    # intermediate wheel contact points leave it.  No stage may be discarded.
    config = replace(synthetic_config(), tire_mu=1e-9)
    state = PlanarState(yaw_rate_rad_s=2 * pi / 0.01)
    environment = PlanarEnvironment(
        road=PlanarRoad(valid_domain=RoadDomain(-0.9, 0.9, -0.7, 0.7))
    )
    run = run_planar_dynamics(
        config, state, (PlanarControls(),), 0.01, environment=environment
    )
    assert run.evaluations[0].road_valid
    assert evaluate_planar_dynamics(
        config, run.states[-1], PlanarControls(), environment=environment
    ).road_valid
    assert not run.road_valid
    assert run.invalid_road_queries > 0


def test_repeated_environment_run_is_deterministic() -> None:
    config = synthetic_config()
    controls = PlanarControls(drive_torques_nm=(0.0, 0.0, 100.0, 100.0))
    environment = PlanarEnvironment(
        wind_world_x_mps=-2.0,
        drag_area_m2=0.8,
        road=PlanarRoad(patches=(RectangularGripPatch(
            x_min_m=-1.0, x_max_m=2.0,
            y_min_m=-1.0, y_max_m=0.0,
            friction_multiplier=0.7,
        ),)),
    )
    first = run_planar_dynamics(
        config, rolling_state(12.0), (controls,) * 20, 0.01,
        environment=environment,
    )
    second = run_planar_dynamics(
        config, rolling_state(12.0), (controls,) * 20, 0.01,
        environment=environment,
    )
    assert first == second
    assert first.road_valid


@pytest.mark.parametrize("factory", [
    lambda: PlanarEnvironment(air_density_kgpm3=0.0),
    lambda: PlanarEnvironment(drag_area_m2=-1.0),
    lambda: PlanarRoad(base_friction_multiplier=-0.1),
    lambda: RectangularGripPatch(0.0, 0.0, 0.0, 1.0, 0.5),
    lambda: RectangularGripPatch(0.0, 1.0, 0.0, 1.0, -0.5),
    lambda: RoadDomain(0.0, 1.0, 2.0, 2.0),
])
def test_invalid_environment_inputs_rejected(factory) -> None:
    with pytest.raises(ValueError):
        factory()
