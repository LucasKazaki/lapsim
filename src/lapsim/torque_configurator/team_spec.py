"""Provisional team facts and explicitly assumed, separate synthetic probes."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from lapsim.resources import repository_root

from .profile import (
    VehicleProfile, canonical, drive_availability, keys, load_profile, number, require,
)

SCHEMA = 'lapsim.team-vehicle-spec.v1'
UNKNOWN_FIELDS = (
    'gear_efficiency', 'motor_base_speed_rad_s', 'motor_maximum_speed_rad_s',
    'vehicle_top_speed_mps', 'topology_id',
)
RATIO_UNIT = 'motor_revolutions_per_driven_wheel_revolution'


@dataclass(frozen=True, slots=True)
class TeamVehicleSpec:
    payload_json: str

    @property
    def gear_ratio(self) -> float:
        return float(self.to_dict()['drivetrain']['gear_ratio'])

    @property
    def sha256(self) -> str:
        return sha256(self.payload_json.encode()).hexdigest()

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        return UNKNOWN_FIELDS

    @property
    def simulation_ready(self) -> bool:
        return False

    def to_dict(self) -> dict:
        return json.loads(self.payload_json)

    @classmethod
    def from_dict(cls, value: dict) -> TeamVehicleSpec:
        keys(value, ('schema', 'vehicle_id', 'season', 'evidence_status', 'source', 'drivetrain', 'limitations'), 'team spec')
        require(value['schema'] == SCHEMA, 'Unsupported team specification schema')
        require(value['evidence_status'] == 'user_report_provisional', 'Team input must remain provisional')
        for name in ('vehicle_id', 'season'):
            require(type(value[name]) is str and 1 <= len(value[name]) <= 100, 'Invalid ' + name)
        keys(value['source'], ('kind', 'reported_by', 'reported_at_utc', 'statement'), 'team source')
        require(value['source']['kind'] == 'user_team_update', 'Explicit team-update provenance required')
        for name in ('reported_by', 'reported_at_utc', 'statement'):
            require(type(value['source'][name]) is str and 1 <= len(value['source'][name]) <= 1000, 'Invalid source ' + name)
        timestamp = value['source']['reported_at_utc']
        require(timestamp.endswith('Z') and datetime.fromisoformat(timestamp.replace('Z', '+00:00')).tzinfo is not None, 'UTC source timestamp required')
        drivetrain = value['drivetrain']
        keys(drivetrain, ('gear_ratio', 'gear_ratio_unit', 'ratio_convention_status', *UNKNOWN_FIELDS), 'team drivetrain')
        number(drivetrain['gear_ratio'], 'gear_ratio', 1e-08, 1000000.0)
        require(drivetrain['gear_ratio_unit'] == RATIO_UNIT, 'Unsupported or inverse gear-ratio convention')
        require(drivetrain['ratio_convention_status'] == 'model_interpretation_requires_team_confirmation', 'The total-reduction convention requires team confirmation')
        require(all((drivetrain[name] is None for name in UNKNOWN_FIELDS)), 'This partial-spec schema retains unknown fields as null; do not insert synthetic team facts')
        require(type(value['limitations']) is list and 1 <= len(value['limitations']) <= 20 and all((type(v) is str and 1 <= len(v) <= 1000 for v in value['limitations'])), 'Explicit limitations required')
        return cls(canonical(value))


def load_team_spec(path: Path | str | None = None) -> TeamVehicleSpec:
    path = (
        Path(path) if path is not None else
        repository_root() / 'configs/team_specs/team-2027-2028-provisional-v1.json'
    )
    with path.open('rb') as stream:
        blob = stream.read(65537)
    require(len(blob) <= 65536, 'Team specification exceeds 64 KiB')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate specification key: ' + key)
            result[key] = value
        return result
    value = json.loads(blob, object_pairs_hook=unique)
    return TeamVehicleSpec.from_dict(value)


def ratio_probe(
    spec: TeamVehicleSpec, base: VehicleProfile, *,
    accept_synthetic_assumptions: bool = False,
) -> tuple[VehicleProfile, dict]:
    require(type(spec) is TeamVehicleSpec and type(base) is VehicleProfile, 'Validated spec and base profile required')
    require(accept_synthetic_assumptions is True, 'Explicit synthetic assumptions are required for a ratio-only probe')
    value = base.to_dict()
    value['profile_id'] = 'synthetic-' + spec.sha256[:12] + '-ratio-probe'
    value['revision'] = 1
    value['actuation']['gear_ratio'] = spec.gear_ratio
    value['provenance'] = (
        f'Synthetic ratio-only diagnostic: provisional team spec {spec.sha256}; '
        f'ratio {spec.gear_ratio}:1 uses motor/wheel angular-speed convention '
        'pending team confirmation. All other inputs, including efficiency, motor '
        'speeds, topology and controller, are assumptions inherited from synthetic '
        f'profile {base.sha256}. Not a calibrated team vehicle.'
    )
    derived = VehicleProfile.from_dict(value)
    manifest = {
        'schema': 'lapsim.team-ratio-probe.v1',
        'team_spec_sha256': spec.sha256,
        'base_profile_sha256': base.sha256,
        'derived_profile_sha256': derived.sha256,
        'team_claims': spec.to_dict()['drivetrain'],
        'assumed_values': {
            k: v for k, v in base.to_dict()['actuation'].items() if k != 'gear_ratio'
        },
        'other_assumptions': 'All vehicle and controller settings are inherited from the explicit synthetic base profile',
        'historical_profile_modified': False,
        'controller_optimality_for_new_ratio': 'not_established',
        'physical_vehicle_or_firmware_ready': False,
    }
    return (derived, manifest)


def actuation_diagnostics(base: VehicleProfile, probe: VehicleProfile) -> dict:
    """Fixed-speed actuator checks, not lap or real-car top-speed predictions."""
    from lapsim.dynamics.actuation import constrain_actuation
    require(base.actuation.topology_id == probe.actuation.topology_id, 'Ratio comparison must keep topology fixed')
    available = drive_availability(base)
    rows = []
    cases = (
        ('propulsion_inactive_limits', 50.0, 10.0),
        ('regeneration_inactive_limits', -50.0, 10.0),
        ('low_speed_current_cap', 10000.0, 0.0),
        ('synthetic_motor_speed_cutoff', 50.0, 60.0),
    )
    for label, command, speed in cases:
        request = tuple((command if enabled else 0.0 for enabled in available))
        values = [
            constrain_actuation(
                profile.actuation, request, (speed,) * 4,
                0.7 * profile.actuation.pack_capacity_j, 0.01, available,
            )
            for profile in (base, probe)
        ]
        rows.append({
            'case': label, 'requested_wheel_torque_nm': request,
            'wheel_speed_rad_s': speed,
            'baseline': asdict(values[0]), 'ratio_probe': asdict(values[1]),
        })
    return {
        'schema': 'lapsim.synthetic-ratio-actuation-check.v1',
        'base_profile_sha256': base.sha256, 'probe_profile_sha256': probe.sha256,
        'rows': rows, 'simulation_only': True,
        'scope': (
            'Fixed-speed actuation only; donor efficiency/motor limits/topology are '
            'synthetic assumptions. Equal wheel outputs are expected when limits are '
            'inactive. No car top speed or controller optimality claim.'
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--synthetic-base', type=Path)
    parser.add_argument('--assume-synthetic-unknowns', action='store_true')
    parser.add_argument('--actuation-probe', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    spec = load_team_spec(args.spec)
    result: dict[str, Any] = {
        'spec': spec.to_dict(), 'spec_sha256': spec.sha256,
        'simulation_ready': False, 'unknown_fields': spec.unknown_fields,
    }
    if args.synthetic_base:
        base = load_profile(args.synthetic_base)
        profile, manifest = ratio_probe(spec, base, accept_synthetic_assumptions=args.assume_synthetic_unknowns)
        result.update(derived_profile=profile.to_dict(), probe_manifest=manifest)
        if args.actuation_probe:
            result['actuation_diagnostics'] = actuation_diagnostics(base, profile)
    else:
        require(not args.actuation_probe, 'Actuation probe requires an explicit synthetic base and assumptions')
    if args.output_dir:
        require(args.synthetic_base is not None, 'Output profile requires an explicit synthetic base and assumptions')
        args.output_dir.mkdir(parents=True, exist_ok=False)
        outputs = (
            ('profile.json', result['derived_profile']),
            ('provenance.json', result['probe_manifest']),
            ('source-spec.json', spec.to_dict()),
        )
        for name, value in outputs:
            (args.output_dir / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        if args.actuation_probe:
            (args.output_dir / 'diagnostics.json').write_text(json.dumps(result['actuation_diagnostics'], indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
