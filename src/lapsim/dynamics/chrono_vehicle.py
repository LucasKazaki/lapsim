"""Optional CPU Chrono::Vehicle owner for the synthetic Sedan study.

Imports are lazy: ordinary LapSim startup never requires PyChrono. No forces
from the fast plants, electrical model or controller are added to this plant.
"""

from __future__ import annotations

import json
import re
import sys
from hashlib import file_digest, sha256
from importlib import import_module
from math import atan2, isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .native_plant import AxleCommand, PlantCapabilities, PlantObservation

VEHICLE_FILE = "sedan/vehicle/Sedan_Vehicle.json"
TIRE_FILE = "sedan/tire/Sedan_Pac02Tire.json"
BRAKE_FILE = "sedan/brake/Sedan_BrakeShafts.json"
PROFILE_ID = "chrono10_synthetic_sedan_shafts_brakes_v1"


def _vector(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def _asset_manifest(root: Path, vehicle_definition: dict) -> dict[str, str]:
    """Hash all recursively referenced JSON/TIR inputs, excluding unused meshes."""
    pending = [VEHICLE_FILE, TIRE_FILE]
    manifest: dict[str, str] = {}
    while pending:
        relative = pending.pop()
        if relative in manifest:
            continue
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Chrono asset reference escapes the installed data root")
        with path.open("rb") as stream:
            data = stream.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Chrono fixture asset exceeds 2 MB")
        manifest[relative] = sha256(data).hexdigest()
        if len(manifest) > 64:
            raise ValueError("Chrono fixture exceeds the 64-asset budget")
        if path.suffix == ".json":
            reference_text = (
                json.dumps(vehicle_definition)
                if relative == VEHICLE_FILE
                else data.decode("utf-8")
            )
            pending.extend(re.findall(r'"([^"\r\n]+\.(?:json|tir))"', reference_text))
    return dict(sorted(manifest.items()))


class ChronoVehiclePlant:
    """Headless double-wishbone vehicle, rear differential, flat rigid road.

    Commands are applied after ChWheeledVehicle.Synchronize, which otherwise
    sets driveshaft torque to zero when no engine/powertrain is installed.
    Observations read the reported force cache without synchronization or
    advancement. Its input-state timestamp is separate from chassis time.
    """

    capabilities = PlantCapabilities(
        backend_id="chrono_vehicle_10_cpu_v1",
        topology_id="synthetic_rear_driveshaft_open_differential",
        device="CPU",
        physical_state_owner="Chrono::Vehicle ChSystemNSC",
        suspension="front/rear double wishbone; rigid links, springs and dampers",
        tire="Pac02 combined slip; instantaneous handling slip; synthetic coefficients",
    )

    def __init__(self) -> None:
        try:
            chrono = import_module("pychrono")
            vehicle = import_module("pychrono.vehicle")
        except ImportError as exc:
            raise RuntimeError(
                "PyChrono is unavailable. Use the optional native environment in "
                "docs/chrono_suspension_study.md; no fast-model fallback is performed."
            ) from exc
        self._chrono = chrono
        self._vehicle_module = vehicle
        metadata = list((Path(sys.prefix) / "conda-meta").glob("pychrono-*.json"))
        if len(metadata) != 1:
            raise RuntimeError(
                "This study requires an identifiable official PyChrono conda build"
            )
        package = json.loads(metadata[0].read_text(encoding="utf-8"))
        expected_url = "https://conda.anaconda.org/projectchrono/label/release/win-64/pychrono-10.0.0-py312h418371c_0.conda"
        if (
            package.get("name") != "pychrono"
            or package.get("version") != "10.0.0"
            or package.get("build") != "py312h418371c_0"
            or package.get("url") != expected_url
        ):
            raise RuntimeError(
                "This study requires the pinned official Windows PyChrono 10.0.0 release build"
            )
        self._engine_identity = {
            key: package.get(key)
            for key in ("name", "version", "build", "subdir", "sha256")
        }
        native_modules = (chrono.core._core, vehicle._vehicle)
        binaries = {}
        for module in native_modules:
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(Path(sys.prefix).resolve()):
                raise RuntimeError(
                    "Imported Chrono native module is outside the selected environment"
                )
            with path.open("rb") as stream:
                binaries[path.name] = file_digest(stream, "sha256").hexdigest()
        self._engine_identity["native_modules_sha256"] = binaries
        self._data_root = Path(vehicle.GetVehicleDataPath())
        self._vehicle_definition = json.loads(
            (self._data_root / VEHICLE_FILE).read_text(encoding="utf-8")
        )
        for axle in self._vehicle_definition["Axles"]:
            axle["Left Brake Input File"] = BRAKE_FILE
            axle["Right Brake Input File"] = BRAKE_FILE
        self._definition_text = json.dumps(
            self._vehicle_definition, sort_keys=True, allow_nan=False
        )
        self._assets = _asset_manifest(self._data_root, self._vehicle_definition)
        self._assets["derived/synthetic_sedan_shafts.json"] = sha256(
            self._definition_text.encode("utf-8")
        ).hexdigest()
        self._temporary: TemporaryDirectory | None = None
        self._vehicle: Any = None
        self._terrain: Any = None
        self._inputs: Any = None
        self._command = AxleCommand()
        self._applied_command = AxleCommand()
        self._force_time_s: float | None = None
        try:
            self.reset()
        except BaseException:
            self.close()
            raise

    def reset(self) -> None:
        self.close()
        chrono, veh = self._chrono, self._vehicle_module
        scratch = Path.cwd() / "work" / "native-plant-inputs"
        scratch.mkdir(parents=True, exist_ok=True)
        self._temporary = TemporaryDirectory(prefix="chrono-", dir=scratch)
        vehicle_file = Path(self._temporary.name) / "vehicle.json"
        vehicle_file.write_text(self._definition_text, encoding="utf-8", newline="")
        self._vehicle = veh.WheeledVehicle(
            str(vehicle_file), chrono.ChContactMethod_NSC
        )
        self._vehicle.Initialize(
            chrono.ChCoordsysd(chrono.ChVector3d(0, 0, 0.7), chrono.QUNIT)
        )
        self._vehicle.GetSystem().SetGravitationalAcceleration(
            chrono.ChVector3d(0, 0, -9.81)
        )
        self._vehicle.GetSystem().SetNumThreads(1)
        solver = chrono.ChSolverBB()
        solver.SetMaxIterations(150)
        solver.SetTolerance(1e-10)
        self._vehicle.GetSystem().SetSolver(solver)
        self._vehicle.SetChassisVisualizationType(chrono.VisualizationType_NONE)
        self._vehicle.SetSuspensionVisualizationType(chrono.VisualizationType_NONE)
        self._vehicle.SetSteeringVisualizationType(chrono.VisualizationType_NONE)
        self._vehicle.SetWheelVisualizationType(chrono.VisualizationType_NONE)
        self._tires = []
        for axle in range(2):
            for side in (veh.LEFT, veh.RIGHT):
                tire = veh.ReadTireJSON(veh.GetVehicleDataFile(TIRE_FILE))
                self._vehicle.InitializeTire(
                    tire,
                    self._vehicle.GetWheel(axle, side),
                    chrono.VisualizationType_NONE,
                )
                tire.SetStepsize(0.001)
                self._tires.append(tire)
        if list(self._vehicle.GetDriveline().GetDrivenAxleIndexes()) != [1]:
            raise RuntimeError(
                "The selected fixture must have exactly one driven rear axle"
            )
        self._terrain = veh.RigidTerrain(self._vehicle.GetSystem())
        material = chrono.ChContactMaterialNSC()
        material.SetFriction(0.9)
        self._terrain.AddPatch(
            material,
            chrono.ChCoordsysd(chrono.ChVector3d(0, 0, 0), chrono.QUNIT),
            100,
            30,
        )
        self._terrain.Initialize()
        self._inputs = veh.DriverInputs()
        self._command = AxleCommand()
        self._applied_command = AxleCommand()
        self._force_time_s = None
        self._applied_force_time_s: float | None = None
        self._applied_geometry_time_s = 0.0
        self._applied_forces = ((0.0, 0.0, 0.0),) * 4
        self._synchronize()

    def _require_open(self) -> None:
        if self._vehicle is None:
            raise RuntimeError("Native plant is closed; call reset before reuse")

    def _synchronize(self) -> None:
        self._require_open()
        time_s = self._vehicle.GetSystem().GetChTime()
        self._inputs.m_steering = self._command.steering
        self._inputs.m_braking = self._command.braking
        self._inputs.m_throttle = 0.0
        self._terrain.Synchronize(time_s)
        self._vehicle.Synchronize(time_s, self._inputs, self._terrain)
        self._vehicle.GetDriveline().Synchronize(
            time_s, self._inputs, self._command.driveshaft_torque_nm
        )
        self._applied_force_time_s = self._force_time_s
        self._applied_geometry_time_s = float(time_s)
        self._applied_forces = tuple(
            _vector(
                self._vehicle.GetTire(axle, side).ReportTireForce(self._terrain).force
            )
            for axle in range(2)
            for side in (self._vehicle_module.LEFT, self._vehicle_module.RIGHT)
        )

    def set_command(self, command: AxleCommand) -> None:
        if not isinstance(command, AxleCommand):
            raise TypeError("native plant requires an AxleCommand")
        self._require_open()
        self._command = command

    def advance(self, step_s: float) -> None:
        if (
            type(step_s) not in (float, int)
            or not 0 < step_s <= 0.002
            or not isfinite(step_s)
        ):
            raise ValueError("native plant step must be in (0, 0.002] seconds")
        self._synchronize()
        source_time_s = float(self._vehicle.GetSystem().GetChTime())
        self._applied_command = self._command
        # Pac02's low-speed Dahl integrator uses m_stepsize, not Advance(step).
        # Keep its physical clock equal to the actual vehicle integration step.
        for tire in self._tires:
            tire.SetStepsize(step_s)
        self._vehicle.Advance(step_s)
        self._terrain.Advance(step_s)
        self._force_time_s = source_time_s

    def observe(self) -> PlantObservation:
        self._require_open()
        veh = self._vehicle_module
        car = self._vehicle
        slots = [(axle, side) for axle in range(2) for side in (veh.LEFT, veh.RIGHT)]
        # ReportSuspensionForce's std::vector is opaque in the official Windows
        # SWIG build. Use the wrapped double-wishbone accessors instead.
        suspension = [
            veh.CastToChDoubleWishbone(car.GetSuspension(axle)) for axle, _ in slots
        ]
        tires = [car.GetTire(axle, side) for axle, side in slots]
        chassis = car.GetChassisBody()
        forward_world = car.GetRot().Rotate(self._chrono.ChVector3d(1, 0, 0))
        return PlantObservation(
            time_s=float(car.GetSystem().GetChTime()),
            tire_force_source_time_s=self._force_time_s,
            tire_kinematics_source_time_s=self._force_time_s,
            applied_tire_force_source_time_s=self._applied_force_time_s,
            applied_tire_force_geometry_time_s=self._applied_geometry_time_s,
            position_m=_vector(chassis.GetPos()),
            velocity_mps=_vector(chassis.GetPosDt()),
            cardan_xyz_rad=_vector(car.GetRot().GetCardanAnglesXYZ()),
            heading_rad=atan2(forward_world.y, forward_world.x),
            angular_velocity_rad_s=_vector(chassis.GetAngVelParent()),
            mass_kg=float(car.GetMass()),
            wheel_position_m=tuple(
                _vector(car.GetSpindlePos(axle, side)) for axle, side in slots
            ),
            wheel_omega_rad_s=tuple(
                float(car.GetWheel(axle, side).GetState().omega) for axle, side in slots
            ),
            native_axle_shaft_omega_rad_s=tuple(
                float(car.GetSpindleOmega(axle, side)) for axle, side in slots
            ),
            wheel_force_world_n=tuple(
                _vector(tire.ReportTireForce(self._terrain).force) for tire in tires
            ),
            applied_wheel_force_world_n=self._applied_forces,
            tire_slip_ratio=tuple(float(tire.GetLongitudinalSlip()) for tire in tires),
            tire_slip_angle_rad=tuple(float(tire.GetSlipAngle()) for tire in tires),
            suspension_spring_length_m=tuple(
                float(part.GetSpringLength(side))
                for part, (_, side) in zip(suspension, slots)
            ),
            suspension_spring_force_n=tuple(
                float(part.GetSpringForce(side))
                for part, (_, side) in zip(suspension, slots)
            ),
            suspension_damper_force_n=tuple(
                float(part.GetShockForce(side))
                for part, (_, side) in zip(suspension, slots)
            ),
            driveline_wheel_torque_nm=tuple(
                float(car.GetDriveline().GetSpindleTorque(axle, side))
                for axle, side in slots
            ),
            command=self._applied_command,
        )

    def provenance(self) -> dict:
        return {
            "engine": self._engine_identity,
            "assets_sha256": self._assets,
            "profile_id": PROFILE_ID,
            "vehicle_variant": {
                "base": VEHICLE_FILE,
                "only_definition_override": "all four brake inputs use upstream Sedan_BrakeShafts.json",
                "brake_model": "torque-limited shaft clutch; upstream max 2000 N m, shaft inertia 0.4 kg m^2 per brake",
                "ideal_brake_locking": False,
                "brake_reaction_telemetry": "unavailable through selected public API; request is not achieved brake torque",
            },
            "solver": {
                "type": "ChSolverBB",
                "max_iterations": 150,
                "tolerance": 1e-10,
                "threads": 1,
            },
            "initial_height_m": 0.7,
            "gravity_mps2": 9.81,
            "terrain": {"type": "flat rigid", "size_m": [100, 30], "friction": 0.9},
            "observation_phase": "chassis COM after Advance; cached tire force carries its separate input-state time",
            "orientation_representation": "Cardan XYZ radians plus world XY heading of the chassis forward axis",
            "tire_force_coupling": "one plant-step cached tire force delay; contact frame/gating uses interval-start geometry",
            "tire_internal_step_policy": "Pac02 low-speed Dahl bristle step equals each actual plant step; normal-speed handling slip is instantaneous",
            "gpu_physics": False,
            "wheel_signs": "wheel-local +Y omega and driveline wheel torque are positive propulsion; native axle-shaft omega uses opposite axis",
            "torque_scope": "reported differential wheel output; excludes tire/brake torque and exact shaft-body connector inertia",
            "limitations": [
                "Upstream synthetic passenger Sedan; no Formula SAE geometry or vehicle calibration",
                "Ideal requested driveshaft torque; no motor, inverter, battery, regen, or traction controller",
                "Rigid links/chassis; no flexible structure, aero, thermal model or physical validation",
                "Pac02 parameter provenance is upstream synthetic data; no fitted team tire coefficients",
                "Selected TIR uses linear vertical stiffness/damping; no tire bottoming, rolling resistance or pressure dependence",
            ],
        }

    def close(self) -> None:
        self._tires = []
        self._inputs = None
        self._terrain = None
        self._vehicle = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
