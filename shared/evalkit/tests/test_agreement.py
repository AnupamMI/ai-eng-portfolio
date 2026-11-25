import math

import pytest

from evalkit import confusion, exact_agreement, weighted_kappa

L = [1, 2, 3]


def test_confusion_rows_are_rater_a():
    assert confusion([1, 2, 3, 3], [1, 3, 3, 2], L) == [[1, 0, 0], [0, 0, 1], [0, 1, 1]]


def test_kappa_perfect_chance_and_worst():
    a = [1, 2, 3] * 10
    assert weighted_kappa(a, a, L) == pytest.approx(1.0)
    assert weighted_kappa(a, list(reversed(a)), L) < 0  # systematic reversal
    # independent raters with the same marginals -> ~0
    assert weighted_kappa([1, 1, 3, 3], [1, 3, 1, 3], L) == pytest.approx(0.0)


def test_kappa_matches_hand_computed_value():
    # A=[1,1,2,3], B=[1,2,2,2]; linear weights 0, .5, 1. Observed disagreement:
    # (1,2) once and (3,2) once -> (0.5 + 0.5)/4 = 0.25. Marginals A: 2,1,1; B: 1,3,0.
    # Expected = sum w_ij * rowA_i * colB_j / 16 = (2*3*.5 + 1*1*.5 + 1*1*1 + 1*3*.5) / 16
    #          = (3 + .5 + 1 + 1.5)/16 = 0.375  -> kappa = 1 - 0.25/0.375 = 1/3
    assert weighted_kappa([1, 1, 2, 3], [1, 2, 2, 2], L, weights="linear") == pytest.approx(1 / 3)


def test_kappa_nan_when_no_expected_disagreement_and_agreement_rate():
    assert math.isnan(weighted_kappa([2, 2], [2, 2], L))
    assert exact_agreement([1, 2, 3, 3], [1, 3, 3, 2]) == 0.5
    with pytest.raises(ValueError):
        confusion([1], [1, 2], L)
