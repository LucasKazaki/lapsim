"""User-created Prius benchmark profiles, kept outside the repository."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from .presets import VehicleSetup


CAR_INPUT_KEYS = (
    "mass_kg",
    "peak_power_kw",
    "wheelbase_m",
    "tire_radius_m",
    "tire_mu",
    "drag_area_m2",
    "top_speed_kph",
)


def default_profile_path() -> Path:
    app_data = os.environ.get("LOCALAPPDATA")
    base = Path(app_data) if app_data else Path.home() / ".lapsim"
    return base / "LapSim" / "car_profiles.json" if app_data else base / "car_profiles.json"


@dataclass(frozen=True, slots=True)
class SavedCarProfile:
    profile_id: str
    name: str
    inputs: dict[str, float]

    def setup(self, torque_request_fraction: float = 1.0) -> VehicleSetup:
        return VehicleSetup(
            **self.inputs,
            torque_request_fraction=torque_request_fraction,
        )


class ProfileStore:
    """Versioned local profile store with validated, atomic writes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_profile_path()

    def list_profiles(self) -> tuple[SavedCarProfile, ...]:
        if not self.path.exists():
            return ()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("profiles"), list):
            raise ValueError("Unsupported saved car profile file")
        profiles: list[SavedCarProfile] = []
        seen: set[str] = set()
        for item in data["profiles"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid saved car profile")
            profile_id = item.get("profile_id")
            name = item.get("name")
            values = item.get("inputs")
            if (
                not isinstance(profile_id, str)
                or not profile_id.startswith("user:")
                or not isinstance(name, str)
                or not name.strip()
                or not isinstance(values, dict)
                or set(values) != set(CAR_INPUT_KEYS)
                or profile_id in seen
            ):
                raise ValueError("Invalid saved car profile")
            setup = VehicleSetup(**values)
            profiles.append(
                SavedCarProfile(
                    profile_id,
                    name.strip(),
                    {key: float(getattr(setup, key)) for key in CAR_INPUT_KEYS},
                )
            )
            seen.add(profile_id)
        return tuple(profiles)

    def save(self, name: str, setup: VehicleSetup) -> SavedCarProfile:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Profile name must contain 1–80 characters")
        profiles = list(self.list_profiles())
        if any(profile.name.casefold() == clean_name.casefold() for profile in profiles):
            raise ValueError("A saved profile already has that name")
        profile = SavedCarProfile(
            f"user:{uuid4().hex}",
            clean_name,
            {key: float(getattr(setup, key)) for key in CAR_INPUT_KEYS},
        )
        profiles.append(profile)
        self._write(profiles)
        return profile

    def delete(self, profile_id: str) -> None:
        profiles = list(self.list_profiles())
        remaining = [profile for profile in profiles if profile.profile_id != profile_id]
        if len(remaining) == len(profiles):
            raise KeyError(profile_id)
        self._write(remaining)

    def _write(self, profiles: list[SavedCarProfile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 1,
            "profiles": [asdict(profile) for profile in profiles],
        }
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=self.path.parent,
            prefix=".car_profiles_",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(document, file, indent=2, allow_nan=False)
            file.write("\n")
        temporary_path.replace(self.path)
