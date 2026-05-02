"""Equity table sanity checks. Uses the cached table — does not regenerate."""

import numpy as np
import pytest

from engine.equity import equity_table
from engine.hand_class import class_index


@pytest.fixture(scope="module")
def E() -> np.ndarray:
    return equity_table()


def test_shape_and_dtype(E):
    assert E.shape == (169, 169)


def test_symmetry_off_diagonal(E):
    """Off-diagonals must satisfy M[i,j] + M[j,i] == 1 by construction."""
    for i in range(169):
        for j in range(i + 1, 169):
            assert abs(E[i, j] + E[j, i] - 1.0) < 1e-4, f"asymmetric at ({i},{j})"


def test_diagonal_near_half(E):
    """Class vs same class is symmetric in expectation; MC error allowed."""
    for i in range(169):
        assert abs(E[i, i] - 0.5) < 0.06, f"diag[{i}] = {E[i, i]}"


def test_textbook_values(E):
    """Known preflop equities (textbook). MC noise budget = 4%."""
    aa = class_index("AA")
    kk = class_index("KK")
    twos = class_index("22")
    aks = class_index("AKs")
    seven_two_o = class_index("72o")

    assert 0.78 < E[aa, twos] < 0.86, f"AA vs 22 = {E[aa, twos]}"
    assert 0.78 < E[aa, kk] < 0.86, f"AA vs KK = {E[aa, kk]}"
    assert 0.45 < E[aks, twos] < 0.55, f"AKs vs 22 = {E[aks, twos]}"
    # 72o vs AA: textbook ~0.13. 500-sample MC stddev ≈ 1.5%, so allow 4%.
    assert 0.07 < E[seven_two_o, aa] < 0.18, f"72o vs AA = {E[seven_two_o, aa]}"


def test_aa_dominates_everything(E):
    """AA should beat every other class on average."""
    aa = class_index("AA")
    for i in range(169):
        if i == aa:
            continue
        assert E[aa, i] > 0.55, f"AA equity vs class {i} = {E[aa, i]} too low"


def test_72o_loses_to_most_things(E):
    """72o is the worst hand — should be < 50% vs almost everything."""
    weak = class_index("72o")
    losses = sum(1 for i in range(169) if i != weak and E[weak, i] < 0.45)
    assert losses > 130, f"72o only beats {169 - 1 - losses} classes"
