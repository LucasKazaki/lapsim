"""Bounded isotropic circular component study, with shared record/replay rules."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
from math import hypot, isclose, pi
from pathlib import Path
from typing import Any

from lapsim.dynamics.bicycle import _finite
from lapsim.resources import repository_root

from .basic_dynamics import decode_json
from .dynamics_record import _canonical_json, _content_id, _runtime_identity

SCHEMA = "lapsim.component-study.v1"
MODEL = "isotropic_circular_cantilever_v1"
MAX_BYTES = 256_000


@dataclass(frozen=True, slots=True)
class Interval:
    nominal: float
    lower: float
    upper: float

    def __post_init__(self):
        for name in ("nominal", "lower", "upper"):
            _finite(getattr(self, name), name)
        if not self.lower <= self.nominal <= self.upper:
            raise ValueError("interval must contain nominal")


@dataclass(frozen=True, slots=True)
class MaterialCard:
    card_id: str
    young_pa: Interval
    poisson: Interval
    density_kg_m3: Interval
    illustrative_yield_pa: Interval
    version: int = 1
    provenance: str = (
        "LapSim E15 synthetic assumptions; no certified alloy or team measurement"
    )
    validity: str = (
        "Uniform linear isotropic material, 273–333 K; no thermal property dependence"
    )

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1:
            raise ValueError("unsupported material card version")
        for text in (self.card_id, self.provenance, self.validity):
            if not isinstance(text, str) or not 1 <= len(text) <= 512:
                raise ValueError("material text must be bounded and nonempty")
        for name, low, high in (
            ("young_pa", 1e6, 1e12),
            ("poisson", -0.99, 0.499),
            ("density_kg_m3", 10, 30000),
            ("illustrative_yield_pa", 1e3, 1e10),
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, Interval)
                or not low <= value.lower <= value.upper <= high
            ):
                raise ValueError(name + " outside numerical card domain")


@dataclass(frozen=True, slots=True)
class GeometryCard:
    length_m: Interval = Interval(0.6, 0.599, 0.601)
    outside_diameter_m: Interval = Interval(0.025, 0.0249, 0.0251)
    inside_diameter_m: Interval = Interval(0.021, 0.0209, 0.0211)
    version: int = 1
    card_id: str = "synthetic_circular_tube_v1"
    provenance: str = (
        "LapSim E15 illustrative dimensions and independent manufacturing bounds"
    )

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1:
            raise ValueError("unsupported geometry card version")
        for text in (self.card_id, self.provenance):
            if not isinstance(text, str) or not 1 <= len(text) <= 512:
                raise ValueError("geometry text must be bounded and nonempty")
        for name, low, high in (
            ("length_m", 0.01, 10),
            ("outside_diameter_m", 0.001, 1),
            ("inside_diameter_m", 0, 1),
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, Interval)
                or not low <= value.lower <= value.upper <= high
            ):
                raise ValueError(name + " outside numerical geometry domain")
        if self.outside_diameter_m.lower - self.inside_diameter_m.upper < 1e-6:
            raise ValueError(
                "all geometry bounds require at least 1 micrometre diameter difference"
            )


MATERIALS = {
    "synthetic_light_v1": MaterialCard(
        "synthetic_light_v1",
        Interval(70e9, 65e9, 75e9),
        Interval(0.33, 0.31, 0.35),
        Interval(2700, 2650, 2750),
        Interval(250e6, 200e6, 280e6),
    ),
    "synthetic_dense_v1": MaterialCard(
        "synthetic_dense_v1",
        Interval(200e9, 190e9, 210e9),
        Interval(0.3, 0.28, 0.32),
        Interval(7800, 7700, 7900),
        Interval(300e6, 250e6, 350e6),
    ),
}


def _evaluate(*values: float) -> dict[str, Any]:
    length, outside, inside, young, poisson, density, strength, force, torque = values
    area = pi * (outside - inside) * (outside + inside) / 4
    inertia = area * (outside * outside + inside * inside) / 16
    polar = 2 * inertia
    shear = young / (2 * (1 + poisson))
    mass = density * area * length
    displacement = force * length**3 / (3 * young * inertia)
    slope = force * length**2 / (2 * young * inertia)
    twist = torque * length / (shear * polar)
    bending = abs(force) * length * outside / (2 * inertia)
    torsion = abs(torque) * outside / (2 * polar)
    equivalent = hypot(bending, 3**0.5 * torsion)
    return {
        "area_m2": area,
        "second_moment_m4": inertia,
        "polar_moment_m4": polar,
        "shear_modulus_pa": shear,
        "tip_deflection_m": displacement,
        "tip_slope_rad": slope,
        "tip_twist_rad": twist,
        "bending_stiffness_n_per_m": 3 * young * inertia / length**3,
        "torsional_stiffness_nm_per_rad": shear * polar / length,
        "torsional_stiffness_nm_per_deg": shear * polar / length * pi / 180,
        "root_bending_stress_pa": bending,
        "root_torsional_stress_pa": torsion,
        "root_von_mises_pa": equivalent,
        "illustrative_yield_ratio": strength / equivalent if equivalent else None,
        "mass_kg": mass,
        "centroid_ix_kgm2": mass * (outside**2 + inside**2) / 8,
        "centroid_iy_kgm2": mass * (3 * (outside**2 + inside**2) / 4 + length**2) / 12,
        "centroid_iz_kgm2": mass * (3 * (outside**2 + inside**2) / 4 + length**2) / 12,
        "slenderness": length / outside,
        "deflection_over_length": abs(displacement) / length,
    }


def calculate(
    material: MaterialCard, geometry: GeometryCard, *, force_y_n=100.0, torque_x_nm=20.0
) -> dict:
    if not isinstance(material, MaterialCard) or not isinstance(geometry, GeometryCard):
        raise TypeError("explicit material and geometry cards required")
    for name, value in (("force_y_n", force_y_n), ("torque_x_nm", torque_x_nm)):
        _finite(value, name)
        if abs(value) > 1e6:
            raise ValueError(name + " outside numerical load domain")
    intervals = (
        geometry.length_m,
        geometry.outside_diameter_m,
        geometry.inside_diameter_m,
        material.young_pa,
        material.poisson,
        material.density_kg_m3,
        material.illustrative_yield_pa,
    )
    nominal = _evaluate(*(value.nominal for value in intervals), force_y_n, torque_x_nm)
    corners = [
        _evaluate(*values, force_y_n, torque_x_nm)
        for values in product(*((value.lower, value.upper) for value in intervals))
    ]
    bounds: dict[str, Any] = {
        name: {"lower": min(values), "upper": max(values)} if values else None
        for name in nominal
        for values in (
            [corner[name] for corner in corners if corner[name] is not None],
        )
    }
    warnings = []
    if bounds["slenderness"]["lower"] < 20:
        warnings.append("L/Do < 20: shear deformation can matter")
    if bounds["deflection_over_length"]["upper"] > 0.05:
        warnings.append("deflection/L > 0.05: small-deflection limit exceeded")
    if any(
        abs(bounds[name][side]) > 0.1
        for name in ("tip_slope_rad", "tip_twist_rad")
        for side in ("lower", "upper")
    ):
        warnings.append("rotation > 0.1 rad: linear-rotation limit exceeded")
    if (
        bounds["illustrative_yield_ratio"] is not None
        and bounds["illustrative_yield_ratio"]["lower"] < 1
    ):
        warnings.append("combined stress exceeds an illustrative yield assumption")
    length = geometry.length_m.nominal
    shapes = [
        {
            "x_m": x,
            "deflection_y_m": force_y_n
            * x
            * x
            * (3 * length - x)
            / (6 * material.young_pa.nominal * nominal["second_moment_m4"]),
            "twist_x_rad": torque_x_nm
            * x
            / (nominal["shear_modulus_pa"] * nominal["polar_moment_m4"]),
        }
        for x in (length * i / 40 for i in range(41))
    ]
    return {
        "nominal": nominal,
        "bounds": bounds,
        "interval_corners": len(corners),
        "shape": shapes,
        "validity": {
            "within_declared_linear_domain": not warnings,
            "warnings": warnings,
        },
    }


def _card(cls: type[Any], value: Any) -> Any:
    if not isinstance(value, dict):
        raise TypeError("card must be an object")
    interval_names = (
        {"young_pa", "poisson", "density_kg_m3", "illustrative_yield_pa"}
        if cls is MaterialCard
        else {"length_m", "outside_diameter_m", "inside_diameter_m"}
    )
    if set(value) != set(cls.__dataclass_fields__):
        raise ValueError("missing or unknown card field")
    try:
        arguments: dict[str, Any] = {
            key: Interval(**item) if key in interval_names else item
            for key, item in value.items()
        }
        return cls(**arguments)
    except (TypeError, KeyError) as exc:
        raise ValueError("invalid card structure") from exc


def _source():
    root = repository_root()
    names = ("src/lapsim/experiments/component_study.py",)
    return {
        "hash_scope": "source bytes normalized CRLF to LF only",
        "files_sha256": {
            name: sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in names
        },
    }


def run_component_study(
    material: MaterialCard | None = None,
    geometry: GeometryCard | None = None,
    *,
    force_y_n=100.0,
    torque_x_nm=20.0,
) -> dict:
    material = MATERIALS["synthetic_light_v1"] if material is None else material
    geometry = GeometryCard() if geometry is None else geometry
    result = calculate(material, geometry, force_y_n=force_y_n, torque_x_nm=torque_x_nm)
    configuration = {
        "material": asdict(material),
        "geometry": asdict(geometry),
        "loads": {"force_y_n": force_y_n, "torque_x_nm": torque_x_nm},
    }
    record = {
        "schema": SCHEMA,
        "model_id": MODEL,
        "configuration": configuration,
        "configuration_sha256": _content_id(configuration),
        "solver": {
            "backend": "analytic_python",
            "version": 1,
            "bending": "Euler-Bernoulli",
            "torsion": "Saint-Venant circular",
        },
        "boundary": "root fully clamped; tip Fy and Mx; uniform unloaded span",
        "frame": "right-handed component frame; x along centroid, y along force",
        "units": "SI; radian rotations; torsional Nm/degree explicitly converted",
        "uncertainty": "128 independent property/dimension corners; sensitivity bounds, not confidence intervals",
        "coupling": "standalone component; no chassis/joint or vehicle/lap mapping",
        "result": result,
        "runtime": _runtime_identity(),
        "source": _source(),
    }
    record["run_id"] = _content_id(record)
    return record


def replay_component_study(record: dict) -> dict:
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unsupported component record")
    if record.get("run_id") != _content_id(
        {key: value for key, value in record.items() if key != "run_id"}
    ):
        raise ValueError("component record content hash mismatch")
    try:
        config = record["configuration"]
        if set(config) != {"material", "geometry", "loads"} or set(config["loads"]) != {
            "force_y_n",
            "torque_x_nm",
        }:
            raise ValueError("unknown configuration field")
        actual = run_component_study(
            _card(MaterialCard, config["material"]),
            _card(GeometryCard, config["geometry"]),
            **config["loads"],
        )
    except (TypeError, KeyError) as exc:
        raise ValueError("invalid component configuration") from exc

    def compare(expected, observed):
        if isinstance(expected, dict):
            return (
                isinstance(observed, dict)
                and set(expected) == set(observed)
                and all(
                    compare(value, observed[key]) for key, value in expected.items()
                )
            )
        if isinstance(expected, list):
            return (
                isinstance(observed, list)
                and len(expected) == len(observed)
                and all(compare(a, b) for a, b in zip(expected, observed))
            )
        if type(expected) is int:
            return type(observed) is int and expected == observed
        if type(expected) is float:
            return type(observed) in (int, float) and isclose(
                expected, observed, rel_tol=1e-10, abs_tol=0.0
            )
        return type(expected) is type(observed) and expected == observed

    if set(record) != set(actual) or any(
        not compare(value, record[key])
        for key, value in actual.items()
        if key not in {"run_id", "runtime", "source"}
    ):
        raise ValueError(
            "component replay disagrees with recorded results or model metadata"
        )
    # Source/runtime are provenance; they never authorize a different model.
    if not isinstance(record["runtime"], dict) or not isinstance(
        record["source"], dict
    ):
        raise TypeError("invalid recorded provenance")
    return {
        "model_agreement": True,
        "source_agreement": record["source"] == actual["source"],
        "relative_tolerance": 1e-10,
        "absolute_tolerance_si": 0.0,
        "zero_and_integer_policy": "exact; nonzero fields use relative tolerance only",
    }


def run_component_comparison(
    geometry: GeometryCard | None = None,
    *,
    geometry_b: GeometryCard | None = None,
    force_y_n=100.0,
    torque_x_nm=20.0,
) -> dict:
    geometry = GeometryCard() if geometry is None else geometry
    geometry_b = geometry if geometry_b is None else geometry_b
    runs = {
        key: run_component_study(
            material, shape, force_y_n=force_y_n, torque_x_nm=torque_x_nm
        )
        for key, material, shape in (
            ("A", MATERIALS["synthetic_light_v1"], geometry),
            ("B", MATERIALS["synthetic_dense_v1"], geometry_b),
        )
    }
    record = {
        "schema": "lapsim.component-comparison.v1",
        "runs": runs,
        "geometry_policy": "fixed_geometry"
        if geometry == geometry_b
        else "manual_geometry_change",
        "comparison_policy": "same imposed loads; two synthetic materials; no geometry optimization or vehicle coupling",
    }
    record["run_id"] = _content_id(record)
    return record


def replay_component_comparison(record: dict) -> dict:
    if not isinstance(record, dict) or set(record) != {
        "schema",
        "runs",
        "geometry_policy",
        "comparison_policy",
        "run_id",
    }:
        raise ValueError("invalid component comparison fields")
    if record["schema"] != "lapsim.component-comparison.v1" or record[
        "run_id"
    ] != _content_id({key: value for key, value in record.items() if key != "run_id"}):
        raise ValueError("invalid component comparison identity")
    runs = record["runs"]
    if not isinstance(runs, dict) or set(runs) != {"A", "B"}:
        raise ValueError("exactly two comparison runs required")
    verified = {key: replay_component_study(run) for key, run in runs.items()}
    if runs["A"]["configuration"]["loads"] != runs["B"]["configuration"]["loads"]:
        raise ValueError("comparison loads must match")
    expected = run_component_comparison(
        _card(GeometryCard, runs["A"]["configuration"]["geometry"]),
        geometry_b=_card(GeometryCard, runs["B"]["configuration"]["geometry"]),
        **runs["A"]["configuration"]["loads"],
    )
    for key in ("geometry_policy", "comparison_policy"):
        if record[key] != expected[key]:
            raise ValueError("comparison policy mismatch")
    for key in runs:
        if (
            runs[key]["configuration"]["material"]
            != expected["runs"][key]["configuration"]["material"]
        ):
            raise ValueError("comparison material card mismatch")
    return {
        "model_agreement": True,
        "runs_replayed": 2,
        "source_agreement": all(item["source_agreement"] for item in verified.values()),
    }


def load_component_json(path: Path) -> dict:
    """Bound the actual read, including a file growing after an earlier stat."""
    with path.open("rb") as stream:
        value = decode_json(stream.read(MAX_BYTES + 1), maximum_bytes=MAX_BYTES)
    if not isinstance(value, dict):
        raise TypeError("component JSON must be an object")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--comparison", action="store_true")
    parser.add_argument(
        "--material", choices=tuple(MATERIALS), default="synthetic_light_v1"
    )
    args = parser.parse_args()
    if (
        args.replay
        and args.output
        and (
            args.replay.resolve() == args.output.resolve()
            or (args.output.exists() and args.output.samefile(args.replay))
        )
    ):
        parser.error("output must not overwrite the replay input or its aliases")
    if args.replay:
        record = load_component_json(args.replay)
        value = (
            replay_component_comparison(record)
            if record.get("schema") == "lapsim.component-comparison.v1"
            else replay_component_study(record)
        )
    elif args.comparison:
        value = run_component_comparison()
    else:
        value = run_component_study(MATERIALS[args.material])
    text = _canonical_json(value) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
