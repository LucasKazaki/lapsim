"""Versioned numerical convention shared with the portable C prototype.

Version 1 implicitly inherited the interpreter's builtin sum implementation.
Version 2 adds four validated float values in slot order, rounding each binary64
addition. Never replace this with sum/fsum, reassociation, or a float32 total.
"""
from __future__ import annotations

from typing import Sequence

NUMERIC_CONTRACT_VERSION = 2


def wheel_total(values: Sequence[float]) -> float:
    """Total exactly four already-normalized binary64 wheel values in order."""
    if len(values) != 4:
        raise ValueError("wheel_total requires exactly four values")
    total = 0.0
    for index in range(4):
        total = total + values[index]
    return total
