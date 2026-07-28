"""Scenarios d'ajout de services et notation des terrains a developper.

Ce module a deux usages. L'ajout de services, pour les aines et pour le reste de la
population, applique le noyau de couverture maximale (spopt) et sert a la validation, le
gain reste trop faible pour etre la solution, et les types comme les sites retenus different
d'un groupe a l'autre. La notation des terrains a developper donne a chaque terrain sa cote
d'accessibilite ainee, a la marche et au transport, pour le levier. L'agregation en secteurs
se fait dans sectors.py.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from src.io import latitude_longitude
from src.processing.accessibility import residence_scores
from src.processing.candidate_sites import build_candidate_sites
from src.processing.graph import nearest_graph_nodes
from src.processing.optimization import distance_matrix, solve_mclp


def _initial_coverage(distances_by_type, point_ids, service_types, threshold):
    """Marque, par type de service, les points deja couverts sous le seuil."""
    return {
        t: np.array(
            [
                distances_by_type[t].get(pid) is not None
                and distances_by_type[t].get(pid) <= threshold
                for pid in point_ids
            ]
        )
        for t in service_types
    }


def _best_addition(service_types, weights, covered, matrix_work, threshold, importance):
    """Retient le type et le site qui rapportent le plus a l'etape courante.

    Pour chaque type, la couverture maximale place un site sur la demande encore non
    couverte, et le gain est pondere par l'importance du service. Retourne le couple (type,
    indice du site) ou None si aucun ajout n'apporte de gain.
    """
    best = None
    for service_type in service_types:
        uncovered = weights * (~covered[service_type])
        if uncovered.sum() <= 0:
            continue
        sites_idx, gained = solve_mclp(matrix_work, uncovered, threshold, 1)
        if not sites_idx or gained <= 0:
            continue
        score = importance.get(service_type, 1.0) * gained
        if best is None or score > best[0]:
            best = (score, service_type, sites_idx[0])
    if best is None:
        return None
    return best[1], best[2]


def _gain_row(
    n_services, group, threshold, added_type, site_id, latitude, longitude, rate
):
    """Une ligne du tableau de gain, part de demande du groupe couverte en pourcentage."""
    return {
        "n_services": n_services,
        "group": group,
        "threshold_m": threshold,
        "added_type": added_type,
        "site_id": site_id,
        "latitude": latitude,
        "longitude": longitude,
        "covered_percent": round(100.0 * rate, 1),
    }


def build_service_assortment(
    demand,
    distances_by_type,
    candidates,
    matrix,
    importance,
    weight_column,
    threshold,
    group,
    n_max,
    config,
    logger,
):
    """Construit l'assortiment de services ajoutes pour un groupe, etape par etape.

    A chaque etape, le meilleur type et le meilleur site sont retenus sur la demande du
    groupe encore non couverte, ponderes par l'importance du service. Un site choisi ferme
    ses environs immediats pour que chaque ajout desserve un secteur different, et
    l'assortiment s'arrete a n_max ajouts. Retourne les lignes de gain du groupe.
    """
    service_types = list(config["essential_services"].keys())
    spacing = float(config["optimization"]["site_spacing_m"])
    precision = config["export"]["coordinate_precision"]
    latitudes, longitudes = latitude_longitude(
        candidates.geometry, config["geographic_crs"], precision
    )
    out_of_reach = float(config["optimization"]["matrix_cutoff_m"]) * float(
        config["optimization"]["out_of_reach_multiplier"]
    )

    point_ids = list(demand["residence_id"])
    weights = demand[weight_column].to_numpy(dtype=float)
    total_weight = float(weights.sum())
    total_importance = sum(importance.get(t, 1.0) for t in service_types)

    covered = _initial_coverage(distances_by_type, point_ids, service_types, threshold)

    def weighted_rate():
        weighted_covered = sum(
            importance.get(t, 1.0) * float(weights[covered[t]].sum())
            for t in service_types
        )
        if total_weight == 0.0 or total_importance == 0.0:
            return 0.0
        return weighted_covered / (total_importance * total_weight)

    matrix_work = matrix.copy()
    gain_rows = [_gain_row(0, group, threshold, "", "", "", "", weighted_rate())]
    for step in range(1, n_max + 1):
        best = _best_addition(
            service_types, weights, covered, matrix_work, threshold, importance
        )
        if best is None:
            logger.info(
                "Plus aucun ajout utile pour %s, arret a l'etape %d", group, step
            )
            break
        best_type, site_index = best
        covered[best_type] = covered[best_type] | (matrix[:, site_index] <= threshold)

        nearby = (
            candidates.geometry.distance(candidates.geometry.iloc[site_index])
            <= spacing
        )
        matrix_work[:, nearby.to_numpy()] = out_of_reach

        site_id = int(candidates.iloc[site_index]["site_id"])
        gain_rows.append(
            _gain_row(
                step,
                group,
                threshold,
                best_type,
                site_id,
                latitudes.iloc[site_index],
                longitudes.iloc[site_index],
                weighted_rate(),
            )
        )
        logger.info(
            "Assortiment %s, etape %d, ajout %s au site %d",
            group,
            step,
            best_type,
            site_id,
        )
    return gain_rows


def filter_candidates_near_road(candidates, graph, config, logger):
    """Ecarte les sites candidats trop loin du reseau pietonnier."""
    import osmnx as ox

    nodes_gdf = ox.graph_to_gdfs(graph, edges=False)
    candidates = candidates.copy()
    candidates["node"] = nearest_graph_nodes(graph, candidates)
    node_geometry = candidates["node"].map(nodes_gdf.geometry)
    distances = candidates.geometry.distance(
        gpd.GeoSeries(node_geometry.values, crs=candidates.crs)
    )
    max_distance = config["optimization"]["site_road_max_distance_m"]
    kept = candidates[distances <= max_distance].copy()
    if logger is not None:
        logger.info(
            "Sites candidats pres du reseau, %d sur %d retenus",
            len(kept),
            len(candidates),
        )
    return kept.reset_index(drop=True)


def _prepare_candidates(landuse_gdf, source, graph, study_zone, config, logger):
    """Points candidats d'un usage du sol, filtres pres du reseau et regroupes par noeud."""
    candidates = build_candidate_sites(landuse_gdf, study_zone, source, logger)
    candidates = filter_candidates_near_road(candidates, graph, config, logger)
    candidates = candidates.drop_duplicates(subset=["node"]).reset_index(drop=True)
    candidates["site_id"] = candidates.index
    return candidates


def service_addition_check(layers, residences, distances_by_type, config, logger):
    """Ajout de services essentiels, pour les aines et pour le reste de la population.

    On applique la couverture maximale aux terrains commerciaux OpenStreetMap, en ajoutant
    de 1 a n_service_check services. Les types et les sites retenus different d'un groupe a
    l'autre, ce qui montre des besoins distincts (diagnostic), et le gain reste trop faible
    pour etre la solution (validation). Retourne le tableau de gain des deux groupes, ou
    None si aucun terrain commercial n'est disponible.
    """
    commercial = layers.get("commercial")
    if commercial is None or len(commercial) == 0:
        logger.warning(
            "Terrains commerciaux absents, validation d'ajout de services sautee"
        )
        return None

    graph = layers["graph"]
    n_max = config["optimization"]["n_service_check"]
    candidates = _prepare_candidates(
        commercial, "commercial", graph, layers["study_zone"], config, logger
    )
    if len(candidates) == 0:
        logger.warning(
            "Aucun site commercial pres du reseau, validation d'ajout sautee"
        )
        return None

    matrix = distance_matrix(
        graph,
        list(candidates["node"]),
        list(residences["node"]),
        float(config["optimization"]["matrix_cutoff_m"]),
        config["optimization"]["out_of_reach_multiplier"],
    )
    groups = [
        (
            config["importance_seniors"],
            "seniors_weight",
            float(config["optimization"]["coverage_threshold_seniors_m"]),
            "seniors",
        ),
        (
            config["importance_rest"],
            "rest_weight",
            float(config["optimization"]["coverage_threshold_rest_m"]),
            "rest",
        ),
    ]
    rows = []
    for importance, weight_column, threshold, group in groups:
        rows.extend(
            build_service_assortment(
                residences,
                distances_by_type,
                candidates,
                matrix,
                importance,
                weight_column,
                threshold,
                group,
                n_max,
                config,
                logger,
            )
        )
    return pd.DataFrame(rows)


def _service_transit_matrix(walk_matrix, candidate_to_stop, service_to_stop, max_stop):
    """Matrice service par candidat des distances effectives avec le transport.

    Un candidat atteint un service par le transport en marchant vers un arret, puis de
    l'arret vers le service, si les deux marches restent sous max_stop. La distance retenue
    est la plus courte entre cette chaine et la marche directe. Un arret hors de portee
    garde la marche directe.
    """
    cand = np.array([np.inf if s is None else s for s in candidate_to_stop])
    serv = np.array([np.inf if s is None else s for s in service_to_stop])
    transit_total = serv[:, None] + cand[None, :]
    reachable = (serv[:, None] <= max_stop) & (cand[None, :] <= max_stop)
    return np.where(reachable, np.minimum(walk_matrix, transit_total), walk_matrix)


def _candidate_type_distances(matrix, service_types, site_ids, out_of_reach):
    """Distance de chaque site candidat vers le service le plus proche de chaque type.

    matrix est la matrice service par candidat du mode choisi. Retourne un dictionnaire
    type vers dictionnaire site vers distance, hors de portee devient None.
    """
    types_array = np.asarray(service_types)
    distances_by_type = {}
    for t in dict.fromkeys(service_types):
        rows = np.where(types_array == t)[0]
        col_min = matrix[rows, :].min(axis=0)
        distances_by_type[t] = {
            site_ids[j]: (None if col_min[j] >= out_of_reach else float(col_min[j]))
            for j in range(len(site_ids))
        }
    return distances_by_type


def _score_sites(candidates, services, matrix, out_of_reach, config):
    """Attribue a chaque site candidat sa cote sur 100 et sa cote qualitative ainee.

    matrix est la matrice service par candidat du mode choisi. Retourne les points
    candidats avec leur cote, prets pour l'agregation en secteurs.
    """
    site_ids = list(candidates["site_id"])
    cand_distances = _candidate_type_distances(
        matrix, list(services["service_type"]), site_ids, out_of_reach
    )
    scores = residence_scores(
        cand_distances,
        config["importance_seniors"],
        config["quality_bands"]["seniors"],
        config["band_fractions"],
        config["overall_quality_ratios"],
    ).rename(columns={"residence_id": "site_id"})
    merged = candidates[["site_id", "geometry"]].merge(
        scores[["site_id", "score_percent", "quality_label"]], on="site_id", how="left"
    )
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=candidates.crs)


def score_development_sites(layers, services, transit_reached, config, logger):
    """Note les terrains a developper par accessibilite ainee, a la marche et au transport.

    Construit les points candidats a developper, calcule leur distance par type de service
    a la marche et au transport, puis leur cote sur 100 a chaque mode. Retourne un
    dictionnaire des deux couches de points notes, ou None si aucun terrain n'est
    disponible.
    """
    development = layers.get("development")
    if development is None or len(development) == 0:
        logger.warning("Terrains a developper absents, secteurs de logement sautes")
        return None

    graph = layers["graph"]
    candidates = _prepare_candidates(
        development, "development", graph, layers["study_zone"], config, logger
    )
    if len(candidates) == 0:
        logger.warning("Aucun terrain a developper pres du reseau, secteurs sautes")
        return None

    cutoff = float(config["optimization"]["matrix_cutoff_m"])
    multiplier = config["optimization"]["out_of_reach_multiplier"]
    out_of_reach = cutoff * float(multiplier)
    walk_matrix = distance_matrix(
        graph, list(candidates["node"]), list(services["node"]), cutoff, multiplier
    )
    max_stop = float(config["transit"]["max_stop_distance_seniors_m"])
    candidate_to_stop = [transit_reached.get(node) for node in candidates["node"]]
    service_to_stop = [transit_reached.get(node) for node in services["node"]]
    transit_matrix = _service_transit_matrix(
        walk_matrix, candidate_to_stop, service_to_stop, max_stop
    )

    scored = {
        "walk": _score_sites(candidates, services, walk_matrix, out_of_reach, config),
        "transit": _score_sites(
            candidates, services, transit_matrix, out_of_reach, config
        ),
    }
    logger.info("Terrains a developper notes, %d", len(candidates))
    return scored
