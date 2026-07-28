"""Cote d'accessibilite sur 100 par residence, reprise de GMQ210.

Chaque residence recoit une cote de proximite par type de service selon la
distance de marche vers le service le plus proche de ce type. Le palier de
distance donne une fraction de points, definie dans config.yaml, et cette
fraction est ponderee par l'importance du service pour le groupe choisi,
aines ou reste de la population. Etre proche d'un service important pese lourd,
etre loin d'un service moins important pese peu. La somme ponderee est ramenee
sur 100, puis une cote qualitative globale est attribuee selon des paliers de
pourcentage. Les paliers et fractions viennent tous de config.yaml.
"""

from __future__ import annotations

import math

import geopandas as gpd
import pandas as pd

from src.processing.graph import distances_from_sources, nearest_graph_nodes


def _is_out_of_reach(distance_m):
    """Indique qu'une distance est absente ou infinie, donc hors de portee."""
    if distance_m is None:
        return True
    if isinstance(distance_m, float) and (
        math.isnan(distance_m) or math.isinf(distance_m)
    ):
        return True
    return False


def band_label(distance_m, bands):
    """Libelle du palier de distance qui contient la distance de marche.

    Une distance absente ou infinie recoit le dernier palier, le moins bon.
    """
    if _is_out_of_reach(distance_m):
        return bands[-1][1]
    for max_distance, label in bands:
        if distance_m <= max_distance:
            return label
    return bands[-1][1]


def overall_quality_label(ratio, overall_ratios):
    """Libelle qualitatif global selon le ratio du pourcentage obtenu."""
    for min_ratio, label in overall_ratios:
        if ratio >= min_ratio:
            return label
    return overall_ratios[-1][1]


def residence_scores(
    distances_by_type, importance, bands, band_fractions, overall_ratios
):
    """Cote sur 100 et cote qualitative par residence pour une population donnee.

    distances_by_type associe chaque type de service a un dictionnaire residence
    vers distance de marche minimale en metres, meme au dela des seuils. importance
    donne le poids de chaque type. bands et band_fractions traduisent la distance en
    fraction de points. Retourne un tableau avec une ligne par residence, sa cote sur
    100, sa cote qualitative et sa distance en kilometres vers chaque type de service.
    """
    service_types = list(distances_by_type.keys())
    best_fraction = max(band_fractions.values())
    max_possible = sum(importance.get(t, 1.0) * best_fraction for t in service_types)

    residence_ids = set()
    for distances in distances_by_type.values():
        residence_ids.update(distances.keys())

    rows = []
    for residence_id in sorted(residence_ids):
        weighted = 0.0
        row = {"residence_id": residence_id}
        for service_type in service_types:
            distance = distances_by_type[service_type].get(residence_id)
            label = band_label(distance, bands)
            weight = importance.get(service_type, 1.0)
            weighted += weight * band_fractions[label]
            row[f"distance_{service_type}_km"] = (
                None if _is_out_of_reach(distance) else round(distance / 1000.0, 2)
            )
        percent = round(100.0 * weighted / max_possible, 1) if max_possible > 0 else 0.0
        row["score_percent"] = percent
        row["quality_label"] = overall_quality_label(percent / 100.0, overall_ratios)
        rows.append(row)
    return pd.DataFrame(rows)


def compute_distances(layers, residences, config, logger):
    """Distances de marche minimales par type de service et vers le transport.

    Les distances sont calculees sans borne pour donner la vraie distance minimale
    vers chaque service, meme au dela des seuils, ce qui evite les valeurs manquantes
    dans les infobulles. Retourne aussi la meilleure marche d'un arret vers chaque type
    de service et la marche de chaque noeud vers l'arret le plus proche, reutilisee pour
    l'acces au transport des residences, des services et des sites candidats.
    """
    graph = layers["graph"]
    residences = residences.copy()
    residences["node"] = nearest_graph_nodes(graph, residences)

    services = layers["services"].copy()
    services["node"] = nearest_graph_nodes(graph, services)

    access_points = pd.concat(
        [layers["stops"].geometry, layers["stations"].geometry], ignore_index=True
    )
    access_gdf = gpd.GeoDataFrame(geometry=access_points, crs=services.crs)
    access_nodes = list(nearest_graph_nodes(graph, access_gdf))

    distances_by_type = {}
    stop_to_service = {}
    for service_type in config["essential_services"]:
        type_nodes = services.loc[services["service_type"] == service_type, "node"]
        reached = distances_from_sources(graph, list(type_nodes), cutoff=None)
        distances_by_type[service_type] = {
            row.residence_id: reached.get(row.node) for row in residences.itertuples()
        }
        stop_distances = [
            reached.get(node) for node in access_nodes if reached.get(node) is not None
        ]
        stop_to_service[service_type] = min(stop_distances) if stop_distances else None
        logger.info(
            "Distances calculees, %s, %d service(s)", service_type, len(type_nodes)
        )

    transit_reached = distances_from_sources(graph, access_nodes, cutoff=None)
    home_to_stop = {
        row.residence_id: transit_reached.get(row.node)
        for row in residences.itertuples()
    }
    return (
        residences,
        services,
        distances_by_type,
        home_to_stop,
        stop_to_service,
        transit_reached,
    )


def scored_residences(residences, distances_by_type, importance, bands, config):
    """Fusionne les cotes par residence avec la geometrie pour la carte."""
    scores = residence_scores(
        distances_by_type,
        importance,
        bands,
        config["band_fractions"],
        config["overall_quality_ratios"],
    )
    columns = ["residence_id", "geometry", "address"]
    merged = residences[columns].merge(scores, on="residence_id", how="left")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=residences.crs)
