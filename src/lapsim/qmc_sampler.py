"""Explicit SciPy random-generator API compatibility; no global RNG mutation."""
from inspect import signature
from typing import Any

from numpy.random import default_rng
from scipy.stats import qmc


def latin_hypercube(dimensions: int, seed: int):
    # Retain the legacy seed stream while that explicit parameter exists, so
    # saved design seeds keep their meaning. Newer rng-only versions get an
    # isolated generator; their dependency version belongs in the run receipt.
    arguments: dict[str, Any] = {'d': dimensions}
    if 'seed' in signature(qmc.LatinHypercube).parameters:
        arguments['seed'] = seed
    else:
        arguments['rng'] = default_rng(seed)
    return qmc.LatinHypercube(**arguments)
