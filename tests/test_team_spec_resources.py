"""Declared package resources must support profiles without checkout fallback."""

import importlib.util
import shutil
from pathlib import Path

from lapsim import resources
from lapsim.torque_configurator.profile import PROFILE_FILES, example_profile
from lapsim.torque_configurator.team_spec import load_team_spec, ratio_probe


def test_resource_allowlist_and_installed_lookup_preserve_unknown_team_inputs(
    tmp_path, monkeypatch
):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "readiness_build_support", root / "packaging/build_support.py"
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    selected = {path.relative_to(builder.ROOT).as_posix() for path in builder.resource_files()}
    required = {
        "docs/evidence/ev-readiness-20261027.json",
        "configs/team_specs/team-2027-2028-provisional-v1.json",
        *("configs/torque_profiles/" + name for name in PROFILE_FILES.values()),
    }
    assert required <= selected

    module = tmp_path / "installed/lapsim/resources.py"
    bundle = module.parent / "_resources"
    bundle.mkdir(parents=True)
    (bundle / "build-info.json").write_text("{}", encoding="utf-8")
    for name in required:
        destination = bundle / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
    monkeypatch.setattr(resources, "__file__", str(module))
    assert resources.repository_root() == bundle

    team = load_team_spec()
    assert team.gear_ratio == 12.48 and not team.simulation_ready
    assert all(team.to_dict()["drivetrain"][key] is None for key in team.unknown_fields)
    for architecture in PROFILE_FILES:
        baseline = example_profile(architecture)
        assert baseline.actuation.gear_ratio == 4.0
        probe, provenance = ratio_probe(
            team, baseline, accept_synthetic_assumptions=True
        )
        assert probe.actuation.gear_ratio == 12.48
        assert provenance["team_claims"]["gear_efficiency"] is None
