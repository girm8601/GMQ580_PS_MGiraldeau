"""Notation des terrains a developper par accessibilite ainee.

Chaque terrain a developper recoit la cote sur 100 qu'un aine y obtiendrait, a la marche
puis avec le transport. Le calcul reprend exactement celui d'une residence, memes paliers
de distance, memes poids d'importance et meme regle de trajet sans transfert, pour que les
deux cotes soient comparables.

Les cotes servent ensuite au levier, l'agregation en secteurs se fait dans sectors.py. La
validation d'ajout de services est dans service_addition.py.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np

from src.processing.accessibility import residence_scores
from src.processing.candidate_sites import prepare_candidates
from src.processing.optimization import distance_matrix
from src.processing.transit_access import transit_distances_by_type


def candidate_type_distances(matrix, service_types, site_ids, config, out_of_reach):
    """Marche de chaque site candidat vers le service le plus proche de chaque type.

    matrix est la matrice service par candidat des distances de marche. service_types donne
    le type de chaque ligne de la matrice. Les types viennent de la configuration et non
    des services observes, pour que le maximum possible de la cote soit le meme que celui
    des residences. Un type absent de la zone donne une distance absente partout.
    """
    types_array = np.asarray(service_types)
    distances_by_type = {}
    for service_type in config["essential_services"]:
        rows = np.where(types_array == service_type)[0]
        if len(rows) == 0:
            distances_by_type[service_type] = {site_id: None for site_id in site_ids}
            continue
        col_min = matrix[rows, :].min(axis=0)
        distances_by_type[service_type] = {
            site_ids[j]: (None if col_min[j] >= out_of_reach else float(col_min[j]))
            for j in range(len(site_ids))
        }
    return distances_by_type


def _score_sites(candidates, distances_by_type, config):
    """Attribue a chaque site candidat sa cote sur 100 et sa cote qualitative ainee.

    distances_by_type donne la distance du site vers chaque type de service dans le mode
    choisi. Retourne les points candidats avec leur cote, prets pour l'agregation en
    secteurs.
    """
    scores = residence_scores(
        distances_by_type,
        config["importance_seniors"],
        config["quality_bands"]["seniors"],
        config["band_fractions"],
        config["overall_quality_ratios"],
    ).rename(columns={"residence_id": "site_id"})
    merged = candidates[["site_id", "geometry"]].merge(
        scores[["site_id", "score_percent", "quality_label"]], on="site_id", how="left"
    )
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=candidates.crs)


def score_development_sites(layers, services, route_access, config, logger):
    """Note les terrains a developper par accessibilite ainee, a la marche et au transport.

    Construit les points candidats a developper, calcule leur distance par type de service
    a la marche puis avec le transport, et leur cote sur 100 a chaque mode. Le transport
    suit exactement la meme regle que pour les residences, un trajet sans transfert dont la
    marche totale respecte le seuil des aines. Retourne un dictionnaire des deux couches de
    points notes, ou None si aucun terrain n'est disponible.
    """
    development = layers.get("development")
    if development is None or len(development) == 0:
        logger.warning("Terrains a developper absents, secteurs de logement sautes")
        return None

    graph = layers["graph"]
    candidates = prepare_candidates(
        development, "development", graph, layers["study_zone"], config, logger
    )
    if len(candidates) == 0:
        logger.warning("Aucun terrain a developper pres du reseau, secteurs sautes")
        return None

    cutoff = float(config["optimization"]["matrix_cutoff_m"])
    multiplier = config["optimization"]["out_of_reach_multiplier"]
    out_of_reach = cutoff * float(multiplier)
    walk_matrix = distance_matrix(
        graph,
        list(zip(candidates["node"], candidates["snap_m"])),
        list(zip(services["node"], services["snap_m"])),
        cutoff,
        multiplier,
    )
    site_ids = list(candidates["site_id"])
    walk_distances = candidate_type_distances(
        walk_matrix, list(services["service_type"]), site_ids, config, out_of_reach
    )
    route_walk, walk_by_route = route_access
    transit_distances = transit_distances_by_type(
        walk_distances,
        dict(zip(site_ids, zip(candidates["node"], candidates["snap_m"]))),
        route_walk,
        walk_by_route,
        float(config["transit"]["max_total_walk_seniors_m"]),
    )

    scored = {
        "walk": _score_sites(candidates, walk_distances, config),
        "transit": _score_sites(candidates, transit_distances, config),
    }
    logger.info("Terrains a developper notes, %d", len(candidates))
    return scored
