# Objectif, verifier l'initialisation de la couverture, l'assortiment d'ajout de services
# et la matrice de distances transport des candidats, sur des donnees synthetiques aux
# reponses connues.

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from src.processing.scenarios import (
    _initial_coverage,
    build_service_assortment,
    candidate_type_distances,
    demand_by_node,
    optimal_addition_bound,
)

CONFIG = {
    "geographic_crs": "EPSG:4326",
    "essential_services": {"epicerie": {}, "pharmacie": {}},
    "importance_seniors": {"epicerie": 1.0, "pharmacie": 1.0},
    "optimization": {
        "coverage_threshold_seniors_m": 800.0,
        "site_spacing_m": 300.0,
        "matrix_cutoff_m": 1000.0,
        "out_of_reach_multiplier": 10.0,
    },
    "export": {"coordinate_precision": 6},
}


class _SilentLogger:
    """Journal muet, les tests ne verifient pas la journalisation."""

    def info(self, *args, **kwargs):
        pass


def test_initial_coverage_marks_within_threshold():
    """Un point compte comme couvert seulement s'il est sous le seuil."""
    covered = _initial_coverage({"a": {0: 100, 1: 900, 2: None}}, [0, 1, 2], ["a"], 800)
    assert list(covered["a"]) == [True, False, False]


def test_candidate_distances_cover_every_configured_type():
    """Un type sans service dans la zone doit rester present, avec une distance absente.

    Le maximum possible de la cote doit rester le meme pour un site candidat et pour une
    residence, sinon les deux cotes ne seraient plus comparables.
    """
    # Deux lignes de services, les deux de type epicerie, aucune pharmacie dans la zone.
    matrix = np.array([[300.0, 10000.0], [700.0, 10000.0]])
    distances = candidate_type_distances(
        matrix, ["epicerie", "epicerie"], [0, 1], CONFIG, 10000.0
    )
    assert sorted(distances) == ["epicerie", "pharmacie"]
    # Le site 0 garde la plus courte des deux lignes, le site 1 est hors de portee.
    assert distances["epicerie"] == {0: 300.0, 1: None}
    assert distances["pharmacie"] == {0: None, 1: None}


def test_assortment_raises_coverage_step_by_step():
    """Chaque ajout doit augmenter la part de demande ainee couverte."""
    pytest.importorskip("spopt")
    demand = pd.DataFrame({"point_id": [0, 1], "seniors_weight": [1.0, 1.0]})
    distances = {
        "epicerie": {0: 9999.0, 1: 9999.0},
        "pharmacie": {0: 9999.0, 1: 9999.0},
    }
    # Deux terrains eloignes, chacun couvre une seule residence a moins de 800 m.
    candidates = gpd.GeoDataFrame(
        {"site_id": [0, 1]},
        geometry=[Point(0, 0), Point(100000, 100000)],
        crs="EPSG:2950",
    )
    matrix = np.array([[100.0, 10000.0], [10000.0, 100.0]])
    gain_rows = build_service_assortment(
        demand,
        distances,
        candidates,
        matrix,
        CONFIG["importance_seniors"],
        "seniors_weight",
        CONFIG["optimization"]["coverage_threshold_seniors_m"],
        "seniors",
        2,
        CONFIG,
        _SilentLogger(),
    )
    percents = [row["weighted_covered_percent"] for row in gain_rows]
    assert percents == [0.0, 25.0, 50.0]
    assert len(gain_rows) == 3


def test_demand_by_node_is_an_exact_aggregation():
    """Regrouper la demande par noeud doit conserver le poids total et les distances.

    Deux residences accrochees au meme noeud ont la meme distance vers tout candidat. Les
    additionner ne change donc aucun resultat de la couverture maximale, c'est ce qui
    autorise l'agregation.
    """
    residences = pd.DataFrame(
        {
            "residence_id": [0, 1, 2],
            "node": ["n1", "n1", "n2"],
            "seniors_weight": [3.0, 4.0, 5.0],
            "rest_weight": [1.0, 1.0, 2.0],
        }
    )
    distances = {"epicerie": {0: 250.0, 1: 250.0, 2: 900.0}}
    table, node_distances = demand_by_node(
        residences, distances, ("seniors_weight", "rest_weight")
    )
    assert list(table["point_id"]) == ["n1", "n2"]
    assert list(table["seniors_weight"]) == [7.0, 5.0]
    assert table["seniors_weight"].sum() == residences["seniors_weight"].sum()
    assert node_distances["epicerie"] == {"n1": 250.0, "n2": 900.0}


def test_optimal_bound_reports_the_best_possible_placement():
    """La borne place les services d'un coup et ne descend jamais sous l'etat actuel.

    Le noeud n1 est deja couvert, les noeuds n2 et n3 ne le sont pas et un site les atteint
    chacun. Avec deux services, l'optimum couvre donc toute la demande.
    """
    pytest.importorskip("spopt")
    demand = pd.DataFrame(
        {"point_id": ["n1", "n2", "n3"], "seniors_weight": [10.0, 5.0, 5.0]}
    )
    distances = {"epicerie": {"n1": 300.0, "n2": 2000.0, "n3": 2000.0}}
    candidates = gpd.GeoDataFrame(
        {"site_id": [0, 1]},
        geometry=[Point(0, 0), Point(100000, 100000)],
        crs="EPSG:2950",
    )
    matrix = np.array([[10000.0, 10000.0], [100.0, 10000.0], [10000.0, 100.0]])
    config = dict(CONFIG, essential_services={"epicerie": {}})
    rows = optimal_addition_bound(
        demand,
        distances,
        candidates,
        matrix,
        "seniors_weight",
        800.0,
        "seniors",
        2,
        config,
        _SilentLogger(),
    )
    row = rows[0]
    assert row["n_added"] == 2
    assert row["covered_before_percent"] == 50.0
    assert row["covered_after_percent"] == 100.0
    assert row["gain_percent"] == 50.0
    assert row["site_ids"] == "0 1"
