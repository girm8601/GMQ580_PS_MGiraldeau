"""Indicateur de couverture des residents vulnerables.

Une residence est couverte pour un type de service si elle atteint a pied un
service de ce type sous le seuil. Comme le compte d'aines est reparti sur les
residences, la demande couverte se calcule directement au niveau de la residence,
en additionnant le poids d'aines des residences couvertes.
"""

from __future__ import annotations

import pandas as pd


def residences_covered(distances, threshold_m):
    """Indique pour chaque residence si la distance de marche respecte le seuil."""
    covered = {}
    for residence_id, distance in distances.items():
        covered[residence_id] = distance is not None and distance <= threshold_m
    return covered


def covered_weight(residences_df, covered_field, weight_field):
    """Somme du poids de demande des residences couvertes."""
    covered = residences_df[residences_df[covered_field]]
    return float(covered[weight_field].sum())


def coverage_rate(residences_df, covered_field, weight_field):
    """Taux de couverture, poids couvert sur poids total."""
    total_weight = float(residences_df[weight_field].sum())
    if total_weight == 0.0:
        return 0.0
    return covered_weight(residences_df, covered_field, weight_field) / total_weight


def coverage_summary(
    residences, distances_by_type, transit_seniors, transit_rest, config
):
    """Part couverte par type, par groupe et par mode, aux seuils de couverture.

    Le groupe seniors utilise le poids d'aines et une marche totale de 800 m par le
    transport, le groupe rest est le reste de la population, poids du reste et marche
    totale de 1000 m. Chaque part passe par les memes trois fonctions elementaires que
    les tests couvrent, residences couvertes, poids couvert puis taux.

    Chaque groupe est aussi mesure au seuil de l'autre. La comparaison d'equite du projet
    garde chaque groupe a sa propre distance tolerable, c'est son objet meme, mais elle ne
    permet pas de savoir si un ecart vient de la tolerance ou de la localisation. Les parts
    a seuil commun repondent a cette seconde question et rendent la lecture verifiable.
    """
    thr_seniors = config["optimization"]["coverage_threshold_seniors_m"]
    thr_rest = config["optimization"]["coverage_threshold_rest_m"]
    ref_seniors = config["optimization"]["coverage_reference_seniors_m"]
    ref_rest = config["optimization"]["coverage_reference_rest_m"]
    seniors_thresholds = sorted({ref_seniors, thr_seniors, thr_rest})
    rest_thresholds = sorted({ref_rest, thr_rest, thr_seniors})
    plans = [
        (
            "seniors",
            "seniors_weight",
            "marche",
            distances_by_type,
            seniors_thresholds,
        ),
        (
            "seniors",
            "seniors_weight",
            "marche_transport",
            transit_seniors,
            seniors_thresholds,
        ),
        (
            "rest",
            "rest_weight",
            "marche",
            distances_by_type,
            rest_thresholds,
        ),
        (
            "rest",
            "rest_weight",
            "marche_transport",
            transit_rest,
            rest_thresholds,
        ),
    ]
    working = residences.copy()
    rows = []
    for population, weight_field, mode, distances_all, thresholds in plans:
        for service_type, distances in distances_all.items():
            for threshold in thresholds:
                covered = residences_covered(distances, threshold)
                working["covered"] = (
                    working["residence_id"].map(covered).fillna(False).astype(bool)
                )
                rate = coverage_rate(working, "covered", weight_field)
                rows.append(
                    {
                        "population": population,
                        "mode": mode,
                        "service_type": service_type,
                        "threshold_m": threshold,
                        "covered_percent": round(100.0 * rate, 1),
                    }
                )
    return pd.DataFrame(rows)
