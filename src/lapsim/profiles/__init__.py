"""Named vehicle profiles and source-aware engineering evidence access."""

from .adapter import (
    ProfileInfo,
    ResolvedField,
    ResolvedManifest,
    browse_records,
    build_vehicle,
    list_profiles,
    preview_profile,
    snapshot_vehicle_config,
)
from .registry import EngineeringRegistry, default_bundle_dir, import_intake, load_intake

__all__ = [
    "EngineeringRegistry", "ProfileInfo", "ResolvedField", "ResolvedManifest",
    "browse_records", "build_vehicle", "default_bundle_dir", "import_intake",
    "list_profiles", "load_intake", "preview_profile", "snapshot_vehicle_config",
]
