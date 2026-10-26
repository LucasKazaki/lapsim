"""New contact radii preserve old pose records and reject malformed values."""
from dataclasses import asdict
import json
import pytest
from lapsim.dynamics.planar import PlanarControls
from lapsim.experiments.pose_run_record import _parse_control

def payload():return json.loads(json.dumps(asdict(PlanarControls())))

def test_missing_and_null_radii_keep_nominal_vehicle_radius():
    value=payload();assert _parse_control(value).wheel_radii_m is None
    value.pop('wheel_radii_m');assert _parse_control(value).wheel_radii_m is None

def test_four_explicit_positive_radii_are_preserved():
    value=payload();value['wheel_radii_m']=[.2,.2,.199,.201]
    assert _parse_control(value).wheel_radii_m==(.2,.2,.199,.201)

@pytest.mark.parametrize('radii',[[.2,.2,.2],[.2,.2,0.,.2],[.2,.2,-.1,.2],[.2,.2,float('nan'),.2]])
def test_invalid_radii_are_rejected(radii):
    value=payload();value['wheel_radii_m']=radii
    with pytest.raises(ValueError):_parse_control(value)
