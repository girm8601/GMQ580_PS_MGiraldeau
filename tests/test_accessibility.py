# Objectif, verifier la cote sur 100 par residence sur des donnees synthetiques aux
# reponses connues. L'acces par le transport est couvert par test_transit.py.

from src.processing.accessibility import (
    band_label,
    overall_quality_label,
    residence_scores,
)

# Paliers repris de config.yaml pour les aines, distance max en metres et libelle.
BANDS = [
    [200, "Excellent"],
    [400, "Très bien"],
    [600, "Bien"],
    [800, "Acceptable"],
    [999999, "Insuffisant"],
]
FRACTIONS = {
    "Excellent": 1.0,
    "Très bien": 0.7,
    "Bien": 0.5,
    "Acceptable": 0.3,
    "Insuffisant": 0.0,
}
OVERALL = [
    [0.80, "Excellent"],
    [0.60, "Très bien"],
    [0.40, "Bien"],
    [0.20, "Acceptable"],
    [0.00, "Insuffisant"],
]


def test_band_label_at_thresholds():
    """Chaque palier de distance doit donner le bon libelle."""
    assert band_label(150, BANDS) == "Excellent"
    assert band_label(300, BANDS) == "Très bien"
    assert band_label(700, BANDS) == "Acceptable"
    assert band_label(1200, BANDS) == "Insuffisant"


def test_out_of_reach_gets_lowest():
    """Un service hors de portee doit donner le dernier palier, jamais une erreur."""
    assert band_label(None, BANDS) == "Insuffisant"
    assert band_label(float("inf"), BANDS) == "Insuffisant"


def test_overall_quality_label():
    """Le libelle global doit suivre le ratio du pourcentage obtenu."""
    assert overall_quality_label(0.90, OVERALL) == "Excellent"
    assert overall_quality_label(0.55, OVERALL) == "Bien"
    assert overall_quality_label(0.10, OVERALL) == "Insuffisant"


def test_residence_scores_dispersion():
    """La cote doit ponderer chaque type par son importance et sa proximite."""
    distances = {
        "pharmacy": {1: 100, 2: 100, 3: 2000},
        "supermarket": {1: 100, 2: 2000, 3: 2000},
    }
    importance = {"pharmacy": 1.0, "supermarket": 0.8}
    table = residence_scores(distances, importance, BANDS, FRACTIONS, OVERALL)
    row1 = table[table["residence_id"] == 1].iloc[0]
    row2 = table[table["residence_id"] == 2].iloc[0]
    row3 = table[table["residence_id"] == 3].iloc[0]
    # residence 1 proche des deux services, cote maximale.
    assert row1["score_percent"] == 100.0
    assert row1["quality_label"] == "Excellent"
    # residence 3 loin des deux services, cote minimale.
    assert row3["score_percent"] == 0.0
    assert row3["quality_label"] == "Insuffisant"
    # residence 2 proche du service important seulement, cote intermediaire.
    assert 0.0 < row2["score_percent"] < 100.0
    # la distance minimale reste affichee meme au dela des seuils.
    assert row3["distance_pharmacy_km"] == 2.0
