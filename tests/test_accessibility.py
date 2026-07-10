# Objectif, verifier la cote d'accessibilite par type de service et l'acces
# au transport sur des donnees synthetiques aux reponses connues.

from src.processing.accessibility import (
    accessibility_table,
    score_from_distance,
    total_score,
)
from src.processing.transit_access import is_covered_by_transit

# Paliers repris de config.yaml, moins de 1 km cote 4, puis 3, 2 et 1.
THRESHOLDS = [[1000, 4], [2000, 3], [3000, 2], [999999, 1]]


def test_cotes_aux_paliers():
    """Chaque palier de distance doit donner la cote attendue."""
    assert score_from_distance(500, THRESHOLDS) == 4
    assert score_from_distance(1000, THRESHOLDS) == 4
    assert score_from_distance(1500, THRESHOLDS) == 3
    assert score_from_distance(2500, THRESHOLDS) == 2
    assert score_from_distance(5000, THRESHOLDS) == 1


def test_distance_absente_donne_la_cote_la_plus_basse():
    """Un service hors de portee doit donner la cote 1, jamais une erreur."""
    assert score_from_distance(None, THRESHOLDS) == 1
    assert score_from_distance(float("inf"), THRESHOLDS) == 1


def test_tableau_des_cotes():
    """Le tableau doit croiser chaque lieu avec chaque type de service."""
    distances = {
        "epicerie": {"a": 500, "b": 2500},
        "pharmacie": {"a": 1500},
    }
    table = accessibility_table(distances, THRESHOLDS)
    row_a = table[table["place_id"] == "a"].iloc[0]
    row_b = table[table["place_id"] == "b"].iloc[0]
    assert row_a["cote_epicerie"] == 4
    assert row_a["cote_pharmacie"] == 3
    assert row_b["cote_epicerie"] == 2
    assert row_b["cote_pharmacie"] == 1


def test_cote_totale():
    """La cote totale doit etre la somme des cotes par type."""
    distances = {"epicerie": {"a": 500}, "pharmacie": {"a": 1500}}
    table = total_score(
        accessibility_table(distances, THRESHOLDS), ["epicerie", "pharmacie"]
    )
    assert table.iloc[0]["cote_totale"] == 7


def test_acces_transport():
    """L'acces au transport doit respecter strictement le seuil."""
    assert is_covered_by_transit(400, 500) is True
    assert is_covered_by_transit(500, 500) is True
    assert is_covered_by_transit(501, 500) is False
    assert is_covered_by_transit(None, 500) is False
