"""Testes do cálculo do DECIFRA Score (§4) — funções puras, offline."""
from __future__ import annotations

from decifra_workers import scoring


def test_combine_overall_renormalizes_missing():
    w = scoring.DEFAULT_WEIGHTS
    o = scoring.combine_overall({"expert": 90, "users": 80, "material": None, "value": None}, w)
    expected = (90 * w["expert"] + 80 * w["users"]) / (w["expert"] + w["users"])
    assert o == round(expected, 1)


def test_combine_overall_all_present_equal_weights():
    w = {"expert": 0.25, "users": 0.25, "material": 0.25, "value": 0.25}
    assert scoring.combine_overall({"expert": 100, "users": 80, "material": 60, "value": 40}, w) == 70.0


def test_combine_overall_none_when_empty():
    subs = {"expert": None, "users": None, "material": None, "value": None}
    assert scoring.combine_overall(subs, scoring.DEFAULT_WEIGHTS) is None


def test_confidence_increases_with_sources():
    assert 0 < scoring.confidence_from_sources(1, 0.8) < scoring.confidence_from_sources(3, 0.8) <= 1


def test_aggregate_users_converts_and_weights():
    assert scoring.aggregate_users([(4.0, 100), (5.0, 100)]) == 90.0  # (80+100)/2
    assert scoring.aggregate_users([]) is None
    assert scoring.aggregate_users([(None, 10)]) is None


def test_aggregate_expert_weighted():
    assert scoring.aggregate_expert([(90.0, 1.0), (80.0, 1.0)]) == 85.0
    assert scoring.aggregate_expert([]) is None


def test_material_none_without_inputs():
    assert scoring.material_score(None, None, False, 0, 0) is None


def test_material_with_inputs_in_range():
    m = scoring.material_score(5, 2000, True, 300, 0)
    assert m is not None and 60 < m <= 100


def test_value_scores_relative_50_100():
    out = scoring.value_scores([("a", 90, 100), ("b", 60, 100)])
    assert out["a"] == 100.0 and out["b"] == 50.0


def test_value_scores_single_is_neutral():
    assert scoring.value_scores([("a", 80, 200)]) == {"a": 75.0}


def test_weights_ssd_material_heavier_than_audio():
    assert scoring.weights_for("ssd")["material"] > scoring.weights_for("auscultadores")["material"]
