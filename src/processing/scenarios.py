"""Scenarios d'ajout de services et notation des terrains a developper.

Ce module a deux usages.

L'ajout de services applique le noyau de couverture maximale (spopt) aux terrains
commerciaux, pour les aines et pour le reste de la population. Il repond de deux facons.
L'assortiment etape par etape retient a chaque tour le type et le site qui rapportent le
plus, c'est le scenario realiste et il montre que les besoins des deux groupes different.
La borne superieure place au contraire les cinq services d'un coup, ce qui donne le vrai
optimum et non un choix glouton. Les deux montrent que le gain reste trop faible pour etre
la solution, la borne le prouve meme pour la meilleure implantation possible.

La notation des terrains a developper donne a chaque terrain sa cote d'accessibilite ainee,
a la marche et au transport, pour le levier. L'agregation en secteurs se fait dans
sectors.py.
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
from src.processing.transit_access import transit_distances_by_type


def demand_by_node(residences, distances_by_type, weight_columns):
    """Regroupe la demande des residences par noeud du graphe pietonnier.

    Toutes les residences accrochees au meme noeud ont exactement la meme distance vers tout
    site candidat. Les additionner en un seul point de demande ne change donc aucun resultat
    de la couverture maximale, c'est une agregation exacte et non une approximation. Elle
    fait passer le modele de dix sept mille lignes a environ trois mille, ce qui fait
    tomber le temps du solveur de trente minutes a quelques minutes. Retourne le tableau de
    demande par noeud et les distances de ce noeud vers chaque type de service.
    """
    grouped = residences.groupby("node", sort=True)
    table = grouped[list(weight_columns)].sum().reset_index()
    table = table.rename(columns={"node": "point_id"})
    representative = grouped["residence_id"].first()
    node_distances = {
        service_type: {
            node: distances.get(representative[node]) for node in table["point_id"]
        }
        for service_type, distances in distances_by_type.items()
    }
    return table, node_distances


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
        "weighted_covered_percent": round(100.0 * rate, 1),
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

    point_ids = list(demand["point_id"])
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


def _bound_row(group, service_type, n_added, threshold, site_ids, before, after, total):
    """Une ligne de la borne superieure, en part de la demande du groupe."""

    def part(value):
        return round(100.0 * value / total, 1) if total else 0.0

    return {
        "group": group,
        "service_type": service_type,
        "n_added": n_added,
        "threshold_m": threshold,
        "site_ids": " ".join(str(site_id) for site_id in sorted(site_ids)),
        "covered_before_percent": part(before),
        "covered_after_percent": part(after),
        "gain_percent": part(after - before),
    }


def optimal_addition_bound(
    demand,
    distances_by_type,
    candidates,
    matrix,
    weight_column,
    threshold,
    group,
    n_max,
    config,
    logger,
):
    """Meilleure implantation possible de n services d'un meme type, par la couverture maximale.

    L'assortiment etape par etape est un choix glouton, il retient le meilleur ajout a chaque
    tour sans revenir sur les precedents. La couverture maximale place au contraire les n
    services d'un seul coup et donne donc le vrai optimum. Le resultat est une borne
    superieure du gain, personne ne peut faire mieux avec n services de ce type sur ces
    terrains. Aucune distance minimale entre sites n'est imposee ici, la borne est ainsi la
    plus genereuse possible. Retourne une ligne par type de service.
    """
    point_ids = list(demand["point_id"])
    weights = demand[weight_column].to_numpy(dtype=float)
    total = float(weights.sum())
    rows = []
    for service_type in config["essential_services"]:
        covered = _initial_coverage(
            distances_by_type, point_ids, [service_type], threshold
        )[service_type]
        before = float(weights[covered].sum())
        remaining = weights * (~covered)
        if remaining.sum() <= 0:
            rows.append(
                _bound_row(
                    group, service_type, n_max, threshold, [], before, before, total
                )
            )
            continue
        selected, gained = solve_mclp(matrix, remaining, threshold, n_max)
        site_ids = [int(candidates.iloc[index]["site_id"]) for index in selected]
        rows.append(
            _bound_row(
                group,
                service_type,
                n_max,
                threshold,
                site_ids,
                before,
                before + gained,
                total,
            )
        )
        logger.info(
            "Borne d'ajout %s, %s, la meilleure implantation de %d services gagne %s point(s)",
            group,
            service_type,
            n_max,
            rows[-1]["gain_percent"],
        )
    return rows


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

    La couverture maximale est appliquee aux terrains commerciaux OpenStreetMap de deux
    facons. L'assortiment ajoute de 1 a n_service_check services, un a la fois, et les types
    comme les sites retenus different d'un groupe a l'autre. La borne superieure place les
    n_service_check services d'un seul coup, par type, et donne le vrai optimum. Retourne le
    tableau de gain et le tableau de borne, ou None si aucun terrain n'est disponible.
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

    demand, node_distances = demand_by_node(
        residences, distances_by_type, ("seniors_weight", "rest_weight")
    )
    logger.info(
        "Demande agregee par noeud du graphe, %d point(s) pour %d residence(s)",
        len(demand),
        len(residences),
    )
    matrix = distance_matrix(
        graph,
        list(candidates["node"]),
        list(demand["point_id"]),
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
    gain_rows = []
    bound_rows = []
    for importance, weight_column, threshold, group in groups:
        gain_rows.extend(
            build_service_assortment(
                demand,
                node_distances,
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
        bound_rows.extend(
            optimal_addition_bound(
                demand,
                node_distances,
                candidates,
                matrix,
                weight_column,
                threshold,
                group,
                n_max,
                config,
                logger,
            )
        )
    return pd.DataFrame(gain_rows), pd.DataFrame(bound_rows)


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
    site_ids = list(candidates["site_id"])
    walk_distances = candidate_type_distances(
        walk_matrix, list(services["service_type"]), site_ids, config, out_of_reach
    )
    route_walk, walk_by_route = route_access
    transit_distances = transit_distances_by_type(
        walk_distances,
        dict(zip(site_ids, candidates["node"])),
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
