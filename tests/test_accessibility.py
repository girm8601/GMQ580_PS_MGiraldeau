# Objectif, verifier la cote sur 100 par residence et l'acces au transport sur
# des donnees synthetiques aux reponses connues.

from src.processing.accessibility import (
    band_label,
    overall_quality_label,
    residence_scores,
)
from src.processing.transit_access import (
    effective_transit_distance,
    has_transit_access,
)

# Paliers repris de config.yaml pour les aines, distance max en metres et libelle.
BANDS = [
    [200, "Excellent"],
    [400, "Tres bien"],
    [600, "Bien"],
    [800, "Acceptable"],
    [999999, "Insuffisant"],
]
FRACTIONS = {
    "Excellent": 1.0,
    "Tres bien": 0.75,
    "Bien": 0.5,
    "Acceptable": 0.3,
    "Insuffisant": 0.0,
}
OVERALL = [
    [0.80, "Excellent"],
    [0.70, "Tres bien"],
    [0.50, "Bien"],
    [0.30, "Acceptable"],
    [0.00, "Insuffisant"],
]


def test_band_label_at_thresholds():
    """Chaque palier de distance doit donner le bon libelle."""
    assert band_label(150, BANDS) == "Excellent"
    assert band_label(300, BANDS) == "Tres bien"
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


def test_transit_access():
    """L'acces au transport doit respecter strictement le seuil."""
    assert has_transit_access(400, 500) is True
    assert has_transit_access(500, 500) is True
    assert has_transit_access(501, 500) is False
    assert has_transit_access(None, 500) is False


def test_effective_transit_distance():
    """La distance effective additionne les deux marches quand elles sont courtes."""
    # marche directe 1500 m, mais 300 m vers l'arret et 200 m de l'arret au service.
    assert effective_transit_distance(1500, 300, 200, 500) == 500
    # si la marche vers l'arret depasse le seuil, on garde la marche directe.
    assert effective_transit_distance(1500, 700, 200, 500) == 1500
    # si le service est deja proche a pied, on garde la marche directe.
    assert effective_transit_distance(250, 300, 200, 500) == 250
