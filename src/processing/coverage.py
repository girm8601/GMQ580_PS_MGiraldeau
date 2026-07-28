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

    Le groupe seniors utilise le poids d'aines et le transport a 800 m, le groupe rest est
    le reste de la population, poids du reste et transport a 1000 m.
    """
    thr_seniors = config["optimization"]["coverage_threshold_seniors_m"]
    thr_rest = config["optimization"]["coverage_threshold_rest_m"]
    ref_seniors = config["optimization"]["coverage_reference_seniors_m"]
    ref_rest = config["optimization"]["coverage_reference_rest_m"]
    plans = [
        (
            "seniors",
            "seniors_weight",
            "marche",
            distances_by_type,
            [ref_seniors, thr_seniors],
        ),
        (
            "seniors",
            "seniors_weight",
            "marche_transport",
            transit_seniors,
            [ref_seniors, thr_seniors],
        ),
        (
            "rest",
            "rest_weight",
            "marche",
            distances_by_type,
            [ref_rest, thr_rest],
        ),
        (
            "rest",
            "rest_weight",
            "marche_transport",
            transit_rest,
            [ref_rest, thr_rest],
        ),
    ]
    rows = []
    for population, weight_field, mode, distances_all, thresholds in plans:
        total = float(residences[weight_field].sum())
        for service_type, distances in distances_all.items():
            for threshold in thresholds:
                covered = sum(
                    getattr(row, weight_field)
                    for row in residences.itertuples()
                    if distances.get(row.residence_id) is not None
                    and distances.get(row.residence_id) <= threshold
                )
                percent = 100.0 * covered / total if total else 0.0
                rows.append(
                    {
                        "population": population,
                        "mode": mode,
                        "service_type": service_type,
                        "threshold_m": threshold,
                        "covered_percent": round(percent, 1),
                    }
                )
    return pd.DataFrame(rows)
