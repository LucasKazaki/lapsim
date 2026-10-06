"""Content-identified evidence for one four-wheel A/B dynamics experiment.

The record freezes the actual time-domain inputs, state boundaries, wheel and
force evaluations, equation residuals, and road-domain status. It describes a
synthetic model calculation, not a validated vehicle or a scored lap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
from math import isclose, isfinite
import os
from pathlib import Path
import platform
import subprocess
from typing import Any, Sequence
from uuid import uuid4

from lapsim.dynamics import (
    WHEEL_NAMES,
    PlanarControls,
    PlanarEnvironment,
    PlanarRoad,
    PlanarRun,
    PlanarState,
    PlanarVehicleConfig,
    RectangularGripPatch,
    RoadDomain,
    evaluate_planar_dynamics,
    run_planar_dynamics,
)


DYNAMICS_RECORD_SCHEMA_VERSION = 1
_DEPENDENCIES = ("numpy", "scipy", "matplotlib")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _content_id(payload: dict[str, Any]) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON constant is forbidden: {value}")


def _code_identity() -> dict[str, str | bool | None]:
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root, check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip())
        return {"code_commit": commit, "dirty_worktree": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"code_commit": None, "dirty_worktree": None}


def _runtime_identity() -> dict[str, Any]:
    dependencies: dict[str, str] = {}
    for package in _DEPENDENCIES:
        try:
            dependencies[package] = distribution_version(package)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"required distribution {package!r} is unavailable") from exc
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "dependencies": dependencies,
        "source": _code_identity(),
    }


def _equation_residuals(
    config: PlanarVehicleConfig, run: PlanarRun
) -> dict[str, list[float]]:
    """Evaluate the body force, yaw, and mechanical-power balances at samples."""

    residuals: dict[str, list[float]] = {
        "longitudinal_force_n": [],
        "lateral_force_n": [],
        "yaw_moment_nm": [],
        "mechanical_power_w": [],
    }
    for state, evaluation in zip(run.states, run.evaluations, strict=False):
        derivative = evaluation.derivative
        residuals["longitudinal_force_n"].append(
            config.mass_kg * (
                derivative.u_dot_mps2 - state.yaw_rate_rad_s * state.v_mps
            ) - evaluation.total_body_force_x_n
        )
        residuals["lateral_force_n"].append(
            config.mass_kg * (
                derivative.v_dot_mps2 + state.yaw_rate_rad_s * state.u_mps
            ) - evaluation.total_body_force_y_n
        )
        residuals["yaw_moment_nm"].append(
            config.yaw_inertia_kgm2 * derivative.yaw_rate_dot_rad_s2
            - evaluation.total_yaw_moment_nm
        )
        residuals["mechanical_power_w"].append(
            evaluation.energy_balance_residual_w
        )
    return residuals


def _run_payload(config: PlanarVehicleConfig, run: PlanarRun) -> dict[str, Any]:
    residuals = _equation_residuals(config, run)
    return {
        "times_s": list(run.times_s),
        "states": [asdict(state) for state in run.states],
        "evaluations": [asdict(evaluation) for evaluation in run.evaluations],
        "equation_residuals": residuals,
        "max_abs_equation_residuals": {
            name: max((abs(value) for value in values), default=0.0)
            for name, values in residuals.items()
        },
        "road_valid": run.road_valid,
        "invalid_road_queries": run.invalid_road_queries,
    }


def _validate_run_inputs(
    *, config: PlanarVehicleConfig, environment: PlanarEnvironment,
    initial_state: PlanarState, controls_a: Sequence[PlanarControls],
    controls_b: Sequence[PlanarControls], output_step_s: float,
    run_a: PlanarRun, run_b: PlanarRun, equal_total_required: bool,
) -> None:
    if not isinstance(config, PlanarVehicleConfig):
        raise TypeError("config must be PlanarVehicleConfig")
    if not isinstance(environment, PlanarEnvironment):
        raise TypeError("environment must be PlanarEnvironment")
    if not isinstance(initial_state, PlanarState):
        raise TypeError("initial_state must be PlanarState")
    if not isinstance(equal_total_required, bool):
        raise TypeError("equal_total_required must be bool")
    if not isfinite(output_step_s) or output_step_s <= 0.0:
        raise ValueError("output_step_s must be finite and positive")
    if not controls_a or len(controls_a) != len(controls_b):
        raise ValueError("A and B must have the same nonzero number of control steps")
    if equal_total_required and any(
        not isclose(
            sum(first.drive_torques_nm), sum(second.drive_torques_nm),
            rel_tol=0.0, abs_tol=1e-9,
        )
        for first, second in zip(controls_a, controls_b, strict=True)
    ):
        raise ValueError("A and B must request equal total wheel torque at every step")
    for label, controls, run in (
        ("A", controls_a, run_a), ("B", controls_b, run_b),
    ):
        if not isinstance(run, PlanarRun):
            raise TypeError(f"run {label} must be PlanarRun")
        if any(not isinstance(control, PlanarControls) for control in controls):
            raise TypeError(f"controls {label} must contain PlanarControls")
        if (
            len(run.states) != len(controls) + 1
            or len(run.times_s) != len(run.states)
            or len(run.evaluations) != len(controls)
            or run.states[0] != initial_state
        ):
            raise ValueError(f"run {label} is not aligned with its inputs")
        if any(
            not isclose(time_s, index * output_step_s, rel_tol=1e-12, abs_tol=1e-12)
            for index, time_s in enumerate(run.times_s)
        ):
            raise ValueError(f"run {label} has a different output time grid")
        if (
            run.invalid_road_queries < 0
            or run.road_valid is not (run.invalid_road_queries == 0)
        ):
            raise ValueError(f"run {label} has inconsistent road validity")
        sampled_invalid_queries = 0
        for index, (state, control, evaluation) in enumerate(
            zip(run.states, controls, run.evaluations, strict=False)
        ):
            expected = evaluate_planar_dynamics(
                config, state, control, environment=environment,
            )
            if evaluation != expected:
                raise ValueError(
                    f"run {label} evaluation {index} disagrees with its frozen inputs"
                )
            sampled_invalid_queries += evaluation.invalid_road_queries
        if run.invalid_road_queries < sampled_invalid_queries:
            raise ValueError(f"run {label} omits invalid road queries")
        replayed = run_planar_dynamics(
            config, initial_state, controls, output_step_s,
            environment=environment,
        )
        if run != replayed:
            raise ValueError(
                f"run {label} trajectory or integration-stage road status "
                "disagrees with deterministic replay"
            )


def _validate_serialized_payload(
    payload: dict[str, Any], *, verify_replay: bool = True
) -> None:
    """Reject a damaged or internally contradictory record after hash checking."""

    try:
        inputs = payload["inputs"]
        config = PlanarVehicleConfig(**inputs["vehicle_config"])
        environment_data = inputs["environment"]
        road_data = environment_data["road"]
        domain_data = road_data["valid_domain"]
        road = PlanarRoad(
            base_material_id=road_data["base_material_id"],
            base_friction_multiplier=road_data["base_friction_multiplier"],
            patches=tuple(
                RectangularGripPatch(**patch) for patch in road_data["patches"]
            ),
            valid_domain=None if domain_data is None else RoadDomain(**domain_data),
        )
        environment = PlanarEnvironment(
            wind_world_x_mps=environment_data["wind_world_x_mps"],
            wind_world_y_mps=environment_data["wind_world_y_mps"],
            air_density_kgpm3=environment_data["air_density_kgpm3"],
            drag_area_m2=environment_data["drag_area_m2"],
            road=road,
        )
        step_s = inputs["output_step_s"]
        initial = inputs["initial_state"]
        runs = payload["runs"]
        count = len(inputs["controls"]["A"])
        if (
            not isinstance(step_s, (int, float)) or isinstance(step_s, bool)
            or not isfinite(step_s) or step_s <= 0.0 or count == 0
            or len(inputs["controls"]["B"]) != count
        ):
            raise ValueError("dynamics record has invalid time or controls")
        if inputs["equal_total_required"] and any(
            not isclose(
                sum(first["drive_torques_nm"]), sum(second["drive_torques_nm"]),
                rel_tol=0.0, abs_tol=1e-9,
            )
            for first, second in zip(
                inputs["controls"]["A"], inputs["controls"]["B"], strict=True,
            )
        ):
            raise ValueError("dynamics record has unequal A/B torque requests")
        mass_kg = inputs["vehicle_config"]["mass_kg"]
        yaw_inertia_kgm2 = inputs["vehicle_config"]["yaw_inertia_kgm2"]
        for label in ("A", "B"):
            run = runs[label]
            controls = tuple(
                PlanarControls(**control) for control in inputs["controls"][label]
            )
            if (
                len(run["states"]) != count + 1
                or len(run["times_s"]) != count + 1
                or len(run["evaluations"]) != count
                or run["states"][0] != initial
                or type(run["road_valid"]) is not bool
                or type(run["invalid_road_queries"]) is not int
                or run["invalid_road_queries"] < 0
                or run["road_valid"] is not (run["invalid_road_queries"] == 0)
            ):
                raise ValueError(f"dynamics record run {label} has inconsistent alignment")
            if any(
                not isclose(time_s, index * step_s, rel_tol=1e-12, abs_tol=1e-12)
                for index, time_s in enumerate(run["times_s"])
            ):
                raise ValueError(f"dynamics record run {label} has inconsistent times")
            for name, values in run["equation_residuals"].items():
                if len(values) != count or not isclose(
                    max((abs(value) for value in values), default=0.0),
                    run["max_abs_equation_residuals"][name],
                    rel_tol=1e-12, abs_tol=1e-12,
                ):
                    raise ValueError(f"dynamics record run {label} has inconsistent residuals")
            for index, (state, evaluation) in enumerate(
                zip(run["states"], run["evaluations"], strict=False)
            ):
                expected_evaluation = evaluate_planar_dynamics(
                    config,
                    PlanarState(**state),
                    controls[index],
                    environment=environment,
                )
                if _canonical_json(asdict(expected_evaluation)) != _canonical_json(evaluation):
                    raise ValueError(
                        f"dynamics record run {label} evaluation {index} disagrees with inputs"
                    )
                derivative = evaluation["derivative"]
                expected = {
                    "longitudinal_force_n": mass_kg * (
                        derivative["u_dot_mps2"]
                        - state["yaw_rate_rad_s"] * state["v_mps"]
                    ) - evaluation["total_body_force_x_n"],
                    "lateral_force_n": mass_kg * (
                        derivative["v_dot_mps2"]
                        + state["yaw_rate_rad_s"] * state["u_mps"]
                    ) - evaluation["total_body_force_y_n"],
                    "yaw_moment_nm": (
                        yaw_inertia_kgm2 * derivative["yaw_rate_dot_rad_s2"]
                        - evaluation["total_yaw_moment_nm"]
                    ),
                    "mechanical_power_w": evaluation["energy_balance_residual_w"],
                }
                if any(not isclose(
                    run["equation_residuals"][name][index], value,
                    rel_tol=1e-10, abs_tol=1e-9,
                ) for name, value in expected.items()):
                    raise ValueError(
                        f"dynamics record run {label} residuals disagree with the saved states"
                    )
            if verify_replay:
                replayed = run_planar_dynamics(
                    config,
                    PlanarState(**initial),
                    controls,
                    step_s,
                    environment=environment,
                )
                if _canonical_json(_run_payload(config, replayed)) != _canonical_json(run):
                    raise ValueError(
                        f"dynamics record run {label} differs from deterministic replay"
                    )
        if payload["validity"]["both_runs_within_declared_road_domain"] is not (
            runs["A"]["road_valid"] and runs["B"]["road_valid"]
        ):
            raise ValueError("dynamics record has inconsistent road validity")
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError("dynamics record has missing or invalid fields") from exc


@dataclass(frozen=True, slots=True)
class DynamicsComparisonRecord:
    """Immutable-by-value, content-identified A/B run payload."""

    run_id: str
    _payload_json: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self._payload_json)
        payload["run_id"] = self.run_id
        return payload

    def save(self, path: str | Path) -> Path:
        """Atomically save one complete JSON record under the requested path."""

        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @classmethod
    def load(cls, path: str | Path) -> DynamicsComparisonRecord:
        with Path(path).open("r", encoding="utf-8") as stream:
            payload = json.load(stream, parse_constant=_reject_json_constant)
        if (
            not isinstance(payload, dict)
            or type(payload.get("schema_version")) is not int
            or payload["schema_version"] != DYNAMICS_RECORD_SCHEMA_VERSION
            or payload.get("record_type") != "four_wheel_ab_comparison"
        ):
            raise ValueError("unsupported dynamics-record schema")
        run_id = payload.pop("run_id", None)
        if not isinstance(run_id, str) or run_id != _content_id(payload):
            raise ValueError("dynamics-record content hash does not match")
        _validate_serialized_payload(payload)
        return cls(run_id, _canonical_json(payload))


def capture_dynamics_comparison(
    *, config: PlanarVehicleConfig, environment: PlanarEnvironment,
    initial_state: PlanarState, controls_a: Sequence[PlanarControls],
    controls_b: Sequence[PlanarControls], output_step_s: float,
    run_a: PlanarRun, run_b: PlanarRun, equal_total_required: bool = True,
) -> DynamicsComparisonRecord:
    """Freeze exact A/B commands and all time-aligned model outputs."""

    commands_a = tuple(controls_a)
    commands_b = tuple(controls_b)
    _validate_run_inputs(
        config=config, environment=environment, initial_state=initial_state,
        controls_a=commands_a, controls_b=commands_b, output_step_s=output_step_s,
        run_a=run_a, run_b=run_b, equal_total_required=equal_total_required,
    )
    payload = {
        "schema_version": DYNAMICS_RECORD_SCHEMA_VERSION,
        "record_type": "four_wheel_ab_comparison",
        "simulation_mode": "time_domain_four_wheel",
        "evidence_level": "synthetic_model_estimate",
        "runtime": _runtime_identity(),
        "alignment": (
            "times_s and states are interval boundaries including the initial and "
            "final state; controls and evaluations correspond to interval starts"
        ),
        "wheel_order": list(WHEEL_NAMES),
        "inputs": {
            "vehicle_config": asdict(config),
            "environment": asdict(environment),
            "initial_state": asdict(initial_state),
            "controls": {
                "A": [asdict(control) for control in commands_a],
                "B": [asdict(control) for control in commands_b],
            },
            "output_step_s": output_step_s,
            "equal_total_required": equal_total_required,
        },
        "runs": {
            "A": _run_payload(config, run_a),
            "B": _run_payload(config, run_b),
        },
        "validity": {
            "both_runs_within_declared_road_domain": (
                run_a.road_valid and run_b.road_valid
            ),
            "road_data_status": "synthetic_user_defined_flat_road",
            "vehicle_validation": "not_established_by_this_run",
            "limitations": [
                "Road-domain validity indicates configured domain coverage, not a measured surface.",
                "No motor, inverter, pack, thermal, or actuator limits are modeled by this run.",
            ],
        },
    }
    # The typed runs have already been replayed by _validate_run_inputs.
    _validate_serialized_payload(payload, verify_replay=False)
    return DynamicsComparisonRecord(_content_id(payload), _canonical_json(payload))


def default_dynamics_run_directory() -> Path:
    """Keep dynamics experiments in a per-user directory outside Git."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "LapSim" / "dynamics_runs"


__all__ = [
    "DYNAMICS_RECORD_SCHEMA_VERSION",
    "DynamicsComparisonRecord",
    "capture_dynamics_comparison",
    "default_dynamics_run_directory",
]
