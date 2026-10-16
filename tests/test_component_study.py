"""Independent equation, scaling, sensitivity and adversarial record checks."""

import random
from copy import deepcopy
from dataclasses import replace
from math import pi

import pytest

from lapsim.experiments.component_study import (
    MATERIALS,
    GeometryCard,
    Interval,
    calculate,
    replay_component_comparison,
    replay_component_study,
    run_component_comparison,
    run_component_study,
)
from lapsim.experiments.dynamics_record import _content_id


def point(value):
    return Interval(value, value, value)


def solid():
    return GeometryCard(point(1), point(0.02), point(0))


def test_independent_solid_hand_calculation():
    # Hand reference: pi*d^4/64, m=rho*pi*r^2*L, unit F and torque.
    result = calculate(
        MATERIALS["synthetic_dense_v1"], solid(), force_y_n=1, torque_x_nm=1
    )
    out = result["nominal"]
    assert out["second_moment_m4"] == pytest.approx(7.853981633974484e-9, rel=1e-14)
    assert out["tip_deflection_m"] == pytest.approx(0.0002122065907891938, rel=1e-13)
    assert out["tip_twist_rad"] == pytest.approx(0.0008276057040778559, rel=1e-13)
    assert out["mass_kg"] == pytest.approx(2.4504422698000385, rel=1e-13)
    assert out["centroid_ix_kgm2"] == pytest.approx(0.00012252211349000194, rel=1e-13)
    assert out["centroid_iy_kgm2"] == pytest.approx(
        2.4504422698000385 * (1 / 12 + 0.0001 / 4), rel=1e-13
    )
    assert out["root_bending_stress_pa"] == pytest.approx(
        1.2732395447351627e6, rel=1e-13
    )
    assert out["root_torsional_stress_pa"] == pytest.approx(
        636619.7723675814, rel=1e-13
    )
    assert out["torsional_stiffness_nm_per_deg"] == pytest.approx(
        out["torsional_stiffness_nm_per_rad"] * pi / 180
    )


def test_material_only_changes_compliance_mass_but_not_load_controlled_stress():
    values = [calculate(card, GeometryCard())["nominal"] for card in MATERIALS.values()]
    assert values[0]["tip_deflection_m"] / values[1][
        "tip_deflection_m"
    ] == pytest.approx(200 / 70)
    assert values[1]["mass_kg"] / values[0]["mass_kg"] == pytest.approx(7800 / 2700)
    for name in (
        "root_bending_stress_pa",
        "root_torsional_stress_pa",
        "root_von_mises_pa",
    ):
        assert values[0][name] == values[1][name]


def test_geometry_scaling_and_solid_limit():
    material = MATERIALS["synthetic_light_v1"]
    a = calculate(material, solid())["nominal"]
    b = calculate(material, replace(solid(), length_m=point(2)))["nominal"]
    assert b["tip_deflection_m"] / a["tip_deflection_m"] == pytest.approx(8)
    assert b["tip_twist_rad"] / a["tip_twist_rad"] == pytest.approx(2)
    assert b["mass_kg"] / a["mass_kg"] == pytest.approx(2)
    assert b["centroid_ix_kgm2"] / a["centroid_ix_kgm2"] == pytest.approx(2)
    c = calculate(material, replace(solid(), outside_diameter_m=point(0.04)))["nominal"]
    assert c["tip_deflection_m"] / a["tip_deflection_m"] == pytest.approx(1 / 16)
    assert c["mass_kg"] / a["mass_kg"] == pytest.approx(4)
    assert c["centroid_ix_kgm2"] / a["centroid_ix_kgm2"] == pytest.approx(16)


@pytest.mark.parametrize("force,torque", [(0, 0), (-100, 20), (100, -20), (-100, -20)])
def test_zero_and_mirrored_loads(force, torque):
    base = calculate(MATERIALS["synthetic_light_v1"], GeometryCard())
    result = calculate(
        MATERIALS["synthetic_light_v1"],
        GeometryCard(),
        force_y_n=force,
        torque_x_nm=torque,
    )
    out = result["nominal"]
    assert out["tip_deflection_m"] == pytest.approx(
        base["nominal"]["tip_deflection_m"] * force / 100
    )
    assert out["tip_twist_rad"] == pytest.approx(
        base["nominal"]["tip_twist_rad"] * torque / 20
    )
    assert result["shape"][0]["deflection_y_m"] == 0
    assert result["shape"][-1]["deflection_y_m"] == pytest.approx(
        out["tip_deflection_m"]
    )
    if force == torque == 0:
        assert out["illustrative_yield_ratio"] is None
        assert result["bounds"]["illustrative_yield_ratio"] is None


def test_interval_bounds_cover_seeded_interior_values():
    material, geometry = MATERIALS["synthetic_light_v1"], GeometryCard()
    bounds = calculate(material, geometry)["bounds"]
    rng = random.Random(408)
    for _ in range(25):

        def sample(value):
            return point(rng.uniform(value.lower, value.upper))

        mat = replace(
            material,
            **{
                name: sample(getattr(material, name))
                for name in (
                    "young_pa",
                    "poisson",
                    "density_kg_m3",
                    "illustrative_yield_pa",
                )
            },
        )
        geo = replace(
            geometry,
            **{
                name: sample(getattr(geometry, name))
                for name in ("length_m", "outside_diameter_m", "inside_diameter_m")
            },
        )
        for name, value in calculate(mat, geo)["nominal"].items():
            assert bounds[name]["lower"] <= value <= bounds[name]["upper"]


@pytest.mark.parametrize(
    "value", [True, float("nan"), float("inf"), -float("inf"), "3"]
)
def test_bad_numeric_card_or_load(value):
    with pytest.raises((ValueError, TypeError)):
        Interval(value, value, value)
    with pytest.raises((ValueError, TypeError)):
        run_component_study(force_y_n=value)


def test_invalid_geometry_and_model_limits():
    with pytest.raises(ValueError):
        GeometryCard(inside_diameter_m=point(0.025))
    with pytest.raises(ValueError):
        replace(MATERIALS["synthetic_light_v1"], poisson=point(0.5))
    result = calculate(
        MATERIALS["synthetic_light_v1"], GeometryCard(), force_y_n=100000
    )
    assert not result["validity"]["within_declared_linear_domain"]
    assert len(result["validity"]["warnings"]) >= 3
    assert calculate(MATERIALS["synthetic_light_v1"], GeometryCard())["validity"][
        "within_declared_linear_domain"
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_id", "fake"),
        ("boundary", "free"),
        ("units", "mm"),
        ("solver", {"backend": "FE"}),
        ("configuration_sha256", "0" * 64),
        ("extra", 1),
    ],
)
def test_rehashed_record_metadata_tamper_rejected(field, value):
    record = run_component_study()
    record[field] = value
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError):
        replay_component_study(record)


def test_replay_results_cards_unknowns_and_comparison_policy():
    original = run_component_study()
    assert replay_component_study(original)["model_agreement"]
    record = deepcopy(original)
    record["result"]["nominal"]["mass_kg"] *= 2
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError):
        replay_component_study(record)
    record = deepcopy(original)
    record["configuration"]["material"]["private_unknown"] = "unsupported"
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError):
        replay_component_study(record)
    pair = run_component_comparison()
    assert pair["geometry_policy"] == "fixed_geometry"
    assert replay_component_comparison(pair)["runs_replayed"] == 2
    changed = run_component_comparison(geometry_b=solid())
    assert changed["geometry_policy"] == "manual_geometry_change"
    assert replay_component_comparison(changed)["model_agreement"]
    pair["geometry_policy"] = "optimized"
    pair["run_id"] = _content_id({k: v for k, v in pair.items() if k != "run_id"})
    with pytest.raises(ValueError):
        replay_component_comparison(pair)


def test_bounded_file_reader_rejects_large_and_duplicate_inputs(tmp_path):
    from lapsim.experiments.component_study import MAX_BYTES, load_component_json

    path = tmp_path / "record.json"
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        load_component_json(path)
    path.write_text('{"schema":1,"schema":2}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_component_json(path)
    path.write_text("[1,2]", encoding="utf-8")
    with pytest.raises(TypeError, match="object"):
        load_component_json(path)


def test_actual_cli_comparison_round_trip(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "comparison.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "lapsim.experiments.component_study",
            "--comparison",
            "--output",
            str(path),
        ],
        check=True,
        timeout=30,
    )
    outcome = subprocess.run(
        [
            sys.executable,
            "-m",
            "lapsim.experiments.component_study",
            "--replay",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    import json

    assert json.loads(outcome.stdout)["runs_replayed"] == 2


@pytest.mark.parametrize(
    "path",
    [
        ("result", "nominal", "second_moment_m4"),
        ("result", "nominal", "polar_moment_m4"),
        ("result", "nominal", "centroid_ix_kgm2"),
        ("result", "bounds", "second_moment_m4", "lower"),
    ],
)
def test_valid_thin_section_cannot_replay_zeroed_small_inertias(path):
    geometry = GeometryCard(point(0.03), point(0.001002), point(0.001))
    record = run_component_study(geometry=geometry, force_y_n=1e-4, torque_x_nm=1e-6)
    assert record["result"]["validity"]["within_declared_linear_domain"]
    assert replay_component_study(record)["model_agreement"]
    owner = record
    for key in path[:-1]:
        owner = owner[key]
    assert 0 < owner[path[-1]] < 1e-12
    owner[path[-1]] = 0.0
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError, match="replay disagrees"):
        replay_component_study(record)


@pytest.mark.parametrize("force,forgery", [(1e-20, 0.0), (0.0, 1e-15)])
def test_tiny_load_response_and_zero_do_not_have_a_universal_absolute_escape(
    force, forgery
):
    record = run_component_study(force_y_n=force, torque_x_nm=0.0)
    assert replay_component_study(record)["model_agreement"]
    record["result"]["nominal"]["tip_deflection_m"] = forgery
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError, match="replay disagrees"):
        replay_component_study(record)


def test_rehashed_fractional_corner_count_is_rejected():
    record = run_component_study()
    record["result"]["interval_corners"] = 128.000000001
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})
    with pytest.raises(ValueError, match="replay disagrees"):
        replay_component_study(record)
