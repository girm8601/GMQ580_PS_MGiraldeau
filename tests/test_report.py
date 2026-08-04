# Objectif, verifier la mise en forme du rapport PDF, ecriture des nombres a la
# francaise et conclusion du diagnostic completee par la comparaison a seuil commun.

import pandas as pd

from src.results.report import CONCLUSION, _french_number, diagnostic_conclusion

CONFIG = {
    "optimization": {"coverage_threshold_seniors_m": 800},
    "report": {"decimal_separator": ","},
}


def test_decimal_separator_is_a_comma():
    """Le guide de redaction du departement exige la virgule comme signe decimal."""
    assert _french_number(16.6, ",") == "16,6"
    assert _french_number(-73.224437, ",") == "-73,224437"


def test_whole_numbers_lose_their_empty_decimal():
    """Un compte de personnes ne doit pas s'afficher avec un zero apres la virgule."""
    assert _french_number(45343.0, ",") == "45343"
    assert _french_number(0.0, ",") == "0"


def test_missing_value_stays_empty():
    """Une valeur absente laisse la case vide plutot que d'ecrire nan."""
    assert _french_number(float("nan"), ",") == ""


def _summary(seniors, rest, threshold=800):
    """Sommaire synthetique de couverture a la marche, un seuil et deux groupes."""
    rows = []
    for population, values in (("seniors", seniors), ("rest", rest)):
        for service_type, percent in values.items():
            rows.append(
                {
                    "population": population,
                    "mode": "marche",
                    "service_type": service_type,
                    "threshold_m": threshold,
                    "covered_percent": percent,
                }
            )
    return pd.DataFrame(rows)


def test_conclusion_names_the_location_advantage():
    """Des aines devant a seuil commun doivent etre nommes dans la conclusion."""
    summary = _summary(
        {"pharmacy": 23.2, "bank": 16.6}, {"pharmacy": 16.4, "bank": 11.6}
    )
    text = diagnostic_conclusion(CONFIG, {"coverage": summary})
    assert text.startswith(CONCLUSION["diagnostic"])
    assert "mieux situés" in text
    assert "2 des 2" in text
    assert "5,9" in text


def test_conclusion_stays_neutral_without_the_advantage():
    """Sans avantage de localisation, la conclusion de base est laissee telle quelle."""
    summary = _summary(
        {"pharmacy": 10.0, "bank": 8.0}, {"pharmacy": 16.4, "bank": 11.6}
    )
    assert (
        diagnostic_conclusion(CONFIG, {"coverage": summary}) == CONCLUSION["diagnostic"]
    )


def test_conclusion_survives_a_missing_summary():
    """Un sommaire absent ne doit pas casser le rapport, la conclusion reste celle de base."""
    assert diagnostic_conclusion(CONFIG, {}) == CONCLUSION["diagnostic"]
