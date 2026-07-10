# Objectif, verifier l'indicateur de couverture des residents vulnerables
# sur des donnees synthetiques aux resultats connus.

import pandas as pd

from src.processing.coverage import (
    coverage_by_area,
    residences_covered,
    total_coverage_rate,
)


def test_residences_couvertes_au_seuil():
    """Le seuil doit etre respecte strictement et l'absence geree."""
    covered = residences_covered({"a": 300, "b": 801, "c": None}, 800)
    assert covered == {"a": True, "b": False, "c": False}


def test_couverture_par_aire():
    """La part couverte de chaque aire doit ponderer sa demande."""
    residences = pd.DataFrame(
        {
            "IDUGD": ["A1", "A1", "A2", "A2"],
            "couvert": [True, False, True, True],
        }
    )
    demand = pd.DataFrame({"IDUGD": ["A1", "A2"], "aines": [200.0, 100.0]})
    coverage = coverage_by_area(residences, "IDUGD", "couvert", demand, "aines")
    row_a1 = coverage[coverage["IDUGD"] == "A1"].iloc[0]
    row_a2 = coverage[coverage["IDUGD"] == "A2"].iloc[0]
    assert row_a1["demande_couverte"] == 100.0
    assert row_a2["demande_couverte"] == 100.0


def test_taux_global():
    """Le taux global doit rapporter la demande couverte a la demande totale."""
    coverage = pd.DataFrame(
        {"aines": [200.0, 100.0], "demande_couverte": [100.0, 100.0]}
    )
    assert total_coverage_rate(coverage, "aines") == 200.0 / 300.0


def test_taux_global_sans_demande():
    """Une demande totale nulle doit donner zero plutot qu'une division par zero."""
    coverage = pd.DataFrame({"aines": [0.0], "demande_couverte": [0.0]})
    assert total_coverage_rate(coverage, "aines") == 0.0
