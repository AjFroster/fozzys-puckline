"""Metrics, and the calibration gate in particular."""

from __future__ import annotations

import math

import pytest

from fozzys_puckline.metrics import (
    CalibrationBin,
    accuracy,
    brier_score,
    calibration,
    calibration_threshold,
    evaluate,
    log_loss,
    skill_score,
    worst_calibration_z,
)


def test_perfect_prediction_has_no_loss() -> None:
    assert log_loss([1.0, 0.0], [True, False]) == pytest.approx(0.0, abs=1e-12)
    assert brier_score([1.0, 0.0], [True, False]) == pytest.approx(0.0)


def test_coin_flip_loses_ln_two() -> None:
    assert log_loss([0.5, 0.5], [True, False]) == pytest.approx(math.log(2))


def test_confident_and_wrong_is_bounded_not_infinite() -> None:
    """Clipping keeps one catastrophic call from making the metric unreadable."""
    assert log_loss([1.0], [False]) < 40.0


def test_accuracy_uses_a_half_threshold() -> None:
    assert accuracy([0.6, 0.4, 0.51], [True, False, False]) == pytest.approx(2 / 3)


def test_skill_score_signs() -> None:
    assert skill_score(0.5, 1.0) == pytest.approx(0.5)
    assert skill_score(1.5, 1.0) == pytest.approx(-0.5)


# -- calibration ------------------------------------------------------------


def test_calibration_bins_by_predicted_probability() -> None:
    table = calibration([0.05, 0.15, 0.95], [False, True, True], bins=10)
    assert [b.count for b in table] == [1, 1, 1]
    assert table[0].lower == pytest.approx(0.0)
    assert table[-1].upper == pytest.approx(1.0)


def test_probability_of_one_lands_in_the_last_bin() -> None:
    """Guards the classic off-by-one that puts p=1.0 in a bin that does not exist."""
    table = calibration([1.0], [True], bins=10)
    assert len(table) == 1
    assert table[0].lower == pytest.approx(0.9)


def test_z_scales_with_sample_size() -> None:
    """The same gap means very different things at 30 games and at 3000."""
    thin = CalibrationBin(0.5, 0.6, 30, 0.55, 0.45)
    thick = CalibrationBin(0.5, 0.6, 3000, 0.55, 0.45)
    assert thin.z < 2.0 < thick.z


def test_thin_bins_are_ignored_by_the_gate() -> None:
    table = [CalibrationBin(0.7, 0.8, 5, 0.75, 0.20)]
    assert worst_calibration_z(table) == 0.0


def test_threshold_tightens_as_more_bins_are_tested() -> None:
    """Every populated bin is another chance to fail by luck alone."""
    assert calibration_threshold(1) < calibration_threshold(5) < calibration_threshold(10)
    assert calibration_threshold(5) == pytest.approx(2.576, abs=0.01)


def test_no_testable_bins_is_not_a_failure() -> None:
    assert calibration_threshold(0) == float("inf")


# -- evaluate ---------------------------------------------------------------


def test_baseline_is_the_base_rate_in_the_same_window() -> None:
    outcomes = [True] * 60 + [False] * 40
    probs = [0.6] * 100

    result = evaluate(probs, outcomes)

    assert result.baseline_rate == pytest.approx(0.6)
    assert result.log_loss == pytest.approx(result.baseline_log_loss)
    assert result.log_loss_skill == pytest.approx(0.0)


def test_an_informative_model_beats_the_baseline() -> None:
    outcomes = [True] * 50 + [False] * 50
    probs = [0.9] * 50 + [0.1] * 50

    result = evaluate(probs, outcomes)

    assert result.beats_baseline
    assert result.log_loss_skill > 0.5
    assert result.brier_skill > 0.5
