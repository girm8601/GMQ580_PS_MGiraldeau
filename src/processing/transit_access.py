"""Acces complementaire aux services par le reseau de transport fixe.

Un arret d'autobus ou une gare compte comme point d'acces si le lieu
residentiel peut l'atteindre a pied sous le seuil de la configuration.
Cette dimension complete la marche directe sans modeliser les horaires,
conformement a la decision documentee dans le README.
"""

from __future__ import annotations

import pandas as pd


def is_covered_by_transit(distance_m, max_distance_m):
    """Indique si une distance de marche donne acces au reseau de transport."""
    if distance_m is None:
        return False
    return distance_m <= max_distance_m


def transit_coverage_table(distances_to_stop, max_distance_m):
    """Construit le tableau d'acces au transport par lieu residentiel.

    distances_to_stop associe chaque lieu a sa distance de marche vers le
    point d'acces le plus proche, arret d'autobus ou gare confondus.
    """
    rows = []
    for place_id, distance in distances_to_stop.items():
        rows.append(
            {
                "place_id": place_id,
                "distance_transport": distance,
                "acces_transport": is_covered_by_transit(distance, max_distance_m),
            }
        )
    return pd.DataFrame(rows)
