"""Cote d'accessibilite par type de service, reprise de GMQ210.

Chaque lieu residentiel recoit une cote par type de service selon la
distance de marche vers le service le plus proche de ce type. Les paliers
viennent de config.yaml et ne sont jamais codes en dur ici.
"""

from __future__ import annotations

import math

import pandas as pd


def score_from_distance(distance_m, thresholds):
    """Attribue la cote correspondant au premier palier qui contient la distance.

    Une distance absente ou infinie recoit la cote du dernier palier, la plus
    basse, car le service est alors hors de portee de marche.
    """
    lowest_score = thresholds[-1][1]
    if distance_m is None:
        return lowest_score
    if isinstance(distance_m, float) and (
        math.isnan(distance_m) or math.isinf(distance_m)
    ):
        return lowest_score
    for max_distance, score in thresholds:
        if distance_m <= max_distance:
            return score
    return lowest_score


def accessibility_table(distances_by_type, thresholds):
    """Construit le tableau des cotes par lieu et par type de service.

    distances_by_type associe chaque type de service a un dictionnaire
    lieu vers distance de marche en metres. Les lieux absents d'un type
    recoivent la cote la plus basse pour ce type.
    """
    place_ids = set()
    for distances in distances_by_type.values():
        place_ids.update(distances.keys())

    rows = []
    for place_id in sorted(place_ids):
        row = {"place_id": place_id}
        for service_type, distances in distances_by_type.items():
            distance = distances.get(place_id)
            row[f"distance_{service_type}"] = distance
            row[f"cote_{service_type}"] = score_from_distance(distance, thresholds)
        rows.append(row)
    return pd.DataFrame(rows)


def total_score(table, service_types):
    """Ajoute la cote totale, somme des cotes de tous les types de services."""
    table = table.copy()
    score_columns = [f"cote_{service_type}" for service_type in service_types]
    table["cote_totale"] = table[score_columns].sum(axis=1)
    return table
