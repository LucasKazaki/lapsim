"""Exact scalar validation helper port; candidate is unqualified."""
from math import isfinite
from numbers import Real

def _finite(value: object, name: str) -> None:
    try:
        valid = (
            not isinstance(value, bool) and isinstance(value, Real) and isfinite(value)
        )
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite number")
