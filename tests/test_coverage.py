# Objectif, verifier l'indicateur de couverture des residents vulnerables sur
# des donnees synthetiques aux resultats connus.

import pandas as pd

from src.processing.coverage import (
    coverage_rate,
    coverage_summary,
    covered_weight,
    residences_covered,
)

SUMMARY_CONFIG = {
    "optimization": {
        "coverage_threshold_seniors_m": 800,
        "coverage_threshold_rest_m": 1000,
        "coverage_reference_seniors_m": 200,
        "coverage_reference_rest_m": 400,
    }
}


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


def test_coverage_summary_by_group_mode_and_threshold():
    """Le sommaire doit croiser les deux groupes, les deux modes et les deux seuils.

    Deux residences de poids egal, la premiere a 150 m du service et la seconde a 900 m.
    Le transport rapproche la seconde a 700 m. Les parts attendues se calculent a la main.
    """
    residences = pd.DataFrame(
        {
            "residence_id": [1, 2],
            "seniors_weight": [10.0, 10.0],
            "rest_weight": [5.0, 5.0],
        }
    )
    walk = {"supermarket": {1: 150.0, 2: 900.0}}
    transit = {"supermarket": {1: 150.0, 2: 700.0}}
    summary = coverage_summary(residences, walk, transit, transit, SUMMARY_CONFIG)

    def part(population, mode, threshold):
        row = summary[
            (summary["population"] == population)
            & (summary["mode"] == mode)
            & (summary["threshold_m"] == threshold)
        ]
        return row.iloc[0]["covered_percent"]

    # A la marche, une seule des deux residences respecte le seuil des aines.
    assert part("seniors", "marche", 800) == 50.0
    # Avec le transport, la seconde passe a 700 m, les deux sont couvertes.
    assert part("seniors", "marche_transport", 800) == 100.0
    # Au palier de reference, seule la premiere residence est vraiment proche.
    assert part("seniors", "marche", 200) == 50.0
    # Le reste de la population tolere 1000 m, les deux sont couvertes des la marche.
    assert part("rest", "marche", 1000) == 100.0
    assert len(summary) == 8
