# Objectif, verifier l'indicateur de couverture des residents vulnerables sur
# des donnees synthetiques aux resultats connus.

import pandas as pd

from src.processing.coverage import (
    coverage_rate,
    covered_weight,
    residences_covered,
)


def test_residences_covered_at_threshold():
    """Le seuil doit etre respecte strictement et l'absence geree."""
    covered = residences_covered({"a": 300, "b": 801, "c": None}, 800)
    assert covered == {"a": True, "b": False, "c": False}


def test_covered_weight():
    """Le poids couvert doit additionner les residences couvertes seulement."""
    residences = pd.DataFrame(
        {
            "residence_id": [0, 1, 2, 3],
            "seniors_weight": [5.0, 5.0, 2.0, 2.0],
            "covered": [True, False, True, True],
        }
    )
    assert covered_weight(residences, "covered", "seniors_weight") == 9.0


def test_coverage_rate():
    """Le taux doit rapporter le poids couvert au poids total."""
    residences = pd.DataFrame(
        {
            "seniors_weight": [5.0, 5.0, 2.0, 2.0],
            "covered": [True, False, True, True],
        }
    )
    assert coverage_rate(residences, "covered", "seniors_weight") == 9.0 / 14.0


def test_coverage_rate_without_demand():
    """Un poids total nul doit donner zero plutot qu'une division par zero."""
    residences = pd.DataFrame({"seniors_weight": [0.0], "covered": [False]})
    assert coverage_rate(residences, "covered", "seniors_weight") == 0.0
