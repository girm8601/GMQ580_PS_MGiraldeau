"""Indicateur de couverture des residents vulnerables par aire de diffusion.

Une residence est couverte pour un type de service si elle atteint a pied un
service de ce type sous le seuil. La part des residences couvertes de chaque
aire de diffusion s'applique ensuite au compte d'aines de l'aire, puisque le
recensement ne localise pas les personnes a l'adresse.
"""

from __future__ import annotations


def residences_covered(distances, threshold_m):
    """Indique pour chaque lieu si la distance de marche respecte le seuil."""
    covered = {}
    for place_id, distance in distances.items():
        covered[place_id] = distance is not None and distance <= threshold_m
    return covered


def coverage_by_area(residences_df, area_field, covered_field, demand_df, weight_field):
    """Calcule la couverture ponderee par aire de diffusion.

    residences_df relie chaque residence a son aire de diffusion avec un
    indicateur de couverture. demand_df fournit le poids de demande par aire.
    Retourne un tableau par aire avec la part couverte et la demande couverte.
    """
    share = (
        residences_df.groupby(area_field)[covered_field]
        .mean()
        .rename("part_couverte")
        .reset_index()
    )
    merged = demand_df.merge(share, on=area_field, how="left")
    merged["part_couverte"] = merged["part_couverte"].fillna(0.0)
    merged["demande_couverte"] = merged["part_couverte"] * merged[weight_field]
    return merged


def total_coverage_rate(coverage_df, weight_field):
    """Taux global de couverture, demande couverte sur demande totale."""
    total_weight = float(coverage_df[weight_field].sum())
    if total_weight == 0.0:
        return 0.0
    return float(coverage_df["demande_couverte"].sum()) / total_weight
