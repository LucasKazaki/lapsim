"""The SciPy adapter repeats deterministically without changing global RNG."""
import numpy as np
from inspect import signature
from scipy.stats import qmc
from lapsim.qmc_sampler import latin_hypercube


def test_isolated_seeded_sampler_repeats_and_covers_strata():
    before=np.random.get_state()
    first=latin_hypercube(3,4082025).random(8)
    second=latin_hypercube(3,4082025).random(8)
    assert np.array_equal(first,second)
    assert np.all((first>=0)&(first<1))
    for column in first.T:assert len(set((column*8).astype(int)))==8
    after=np.random.get_state()
    assert before[0]==after[0] and np.array_equal(before[1],after[1]) and before[2:]==after[2:]
    if 'seed' in signature(qmc.LatinHypercube).parameters:
        legacy=qmc.LatinHypercube(d=3,**{'seed':4082025}).random(8)
        assert np.array_equal(first,legacy)
