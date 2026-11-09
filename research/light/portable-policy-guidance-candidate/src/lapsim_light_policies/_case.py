"""Fixed OFF metadata for the portable adapter; no course/runner dependency.

UNTESTED source candidate. This is not the legacy tournament Case type and
must not be used to decode its checkpoints or claim campaign admission.
"""
from dataclasses import dataclass
from math import isfinite


def number(value, name, low, high):
    if type(value) not in (float, int) or not isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite in [{low}, {high}]")


@dataclass(frozen=True)
class OffActuationCase:
    """Only metadata read by the fixed 10 ms AWD/OFF adapter.

    The scalar ranges and defaults used by archived case_for are preserved.
    Name, duration and OFF/friction flags are fixed explicitly in this new DTO.
    """
    name: str = "awd_fixed_total_demand_10ms"
    initial_soc: float = 0.5
    pack_voltage_v: float = 300.0
    motor_temperature_c: float = 40.0
    regen_available: bool = False
    friction_fallback: bool = True
    duration_s: float = 0.01

    def __post_init__(self):
        if self.name != "awd_fixed_total_demand_10ms":
            raise ValueError("Exact fixed AWD/OFF allocation metadata required")
        for key, low, high in (("initial_soc", 0, 1),
                               ("pack_voltage_v", 100, 650),
                               ("motor_temperature_c", -20, 150),
                               ("duration_s", 0.01, 0.01)):
            number(getattr(self, key), key, low, high)
        if self.regen_available is not False or self.friction_fallback is not True:
            raise ValueError("Only explicit regen OFF with common friction fallback is supported")
