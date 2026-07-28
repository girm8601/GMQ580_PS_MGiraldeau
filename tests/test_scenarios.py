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
    _service_transit_matrix,
    build_service_assortment,
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


def test_service_transit_matrix_uses_shorter_path():
    """Le transport raccourcit la distance quand les deux marches sont courtes."""
    walk = np.array([[1000.0, 1000.0]])
    candidate_to_stop = [100.0, None]
    service_to_stop = [200.0]
    transit = _service_transit_matrix(walk, candidate_to_stop, service_to_stop, 800.0)
    # Candidat 0, les deux marches sont courtes, 100 plus 200 bat la marche directe.
    assert transit[0, 0] == 300.0
    # Candidat 1, aucun arret a portee, on garde la marche directe.
    assert transit[0, 1] == 1000.0


def test_assortment_raises_coverage_step_by_step():
    """Chaque ajout doit augmenter la part de demande ainee couverte."""
    pytest.importorskip("spopt")
    residences = pd.DataFrame({"residence_id": [0, 1], "seniors_weight": [1.0, 1.0]})
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
        residences,
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
    percents = [row["covered_percent"] for row in gain_rows]
    assert percents == [0.0, 25.0, 50.0]
    assert len(gain_rows) == 3
