"""Validation de l'ajout de services essentiels, par la couverture maximale.

La couverture maximale de spopt est appliquee aux terrains commerciaux OpenStreetMap, pour
les aines et pour le reste de la population. Elle repond de deux facons.

L'assortiment etape par etape retient a chaque tour le type et le site qui rapportent le
plus. C'est le scenario realiste et il montre que les besoins des deux groupes different.
La borne superieure place au contraire les cinq services d'un seul coup, par type, ce qui
donne le vrai optimum et non un choix glouton.

Les deux montrent que le gain reste trop faible pour etre la solution, et la borne le
prouve meme pour la meilleure implantation possible. La notation des terrains a developper
est dans site_scoring.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.io import latitude_longitude
from src.processing.candidate_sites import prepare_candidates
from src.processing.optimization import distance_matrix, solve_mclp


def demand_by_node(residences, distances_by_type, weight_columns, offset_step_m):
    """Regroupe la demande des residences par noeud et par classe d'ecart d'accrochage.

    Deux residences accrochees au meme noeud avec le meme ecart ont exactement les memes
    distances vers tout site candidat. Les additionner en un seul point de demande ne change
    alors aucun resultat de la couverture maximale. Le noeud seul ne suffit pas, l'ecart varie
    d'une residence a l'autre sur un meme noeud, parfois de plus d'un kilometre. Les ecarts
    sont donc regroupes par classe de offset_step_m metres, ce qui borne l'imprecision a cette
    largeur et divise par trois le nombre de lignes du modele.

    Retourne le tableau de demande, une ligne par groupe avec son noeud et son ecart moyen, et
    les distances de ce groupe vers chaque type de service.
    """
    residences = residences.copy()
    residences["offset_class"] = (residences["snap_m"] // offset_step_m).astype(int)
    grouped = residences.groupby(["node", "offset_class"], sort=True)
    table = grouped[list(weight_columns)].sum().reset_index()
    table["snap_m"] = grouped["snap_m"].mean().to_numpy()
    table["point_id"] = list(zip(table["node"], table["offset_class"]))
    representative = grouped["residence_id"].first()
    group_distances = {
        service_type: {
            point_id: distances.get(representative.loc[key])
            for point_id, key in zip(table["point_id"], representative.index)
        }
        for service_type, distances in distances_by_type.items()
    }
    return table, group_distances


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
    candidates = prepare_candidates(
        commercial, "commercial", graph, layers["study_zone"], config, logger
    )
    if len(candidates) == 0:
        logger.warning(
            "Aucun site commercial pres du reseau, validation d'ajout sautee"
        )
        return None

    demand, node_distances = demand_by_node(
        residences,
        distances_by_type,
        ("seniors_weight", "rest_weight"),
        config["optimization"]["demand_offset_step_m"],
    )
    logger.info(
        "Demande agregee par noeud et par classe d'ecart, %d point(s) pour %d residence(s)",
        len(demand),
        len(residences),
    )
    matrix = distance_matrix(
        graph,
        list(zip(candidates["node"], candidates["snap_m"])),
        list(zip(demand["node"], demand["snap_m"])),
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
