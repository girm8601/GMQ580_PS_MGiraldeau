"""Scenarios S1, construction de l'assortiment de services et cartes optimisees.

Ce module regroupe la logique des scenarios S1. Il choisit les sites candidats,
construit un assortiment de services a ajouter pour chaque ponderation, recalcule la
cote des residences apres chaque ajout et produit les cartes aux paliers demandes.
Le point d'entree du projet, main.py, ne fait qu'appeler optimization_s1.
"""

from __future__ import annotations

import os

import geopandas as gpd
import numpy as np
import pandas as pd

from src.processing.accessibility import scored_residences
from src.processing.candidate_sites import build_candidate_sites
from src.processing.graph import distances_from_sources, nearest_graph_nodes
from src.processing.optimization import distance_matrix, solve_mclp
from src.visualization.maps import ordered_service_types, s1_map


def build_service_assortment(
    residences,
    distances_by_type,
    candidates,
    matrix,
    weighting,
    importance,
    weight_column,
    threshold,
    config,
    logger,
):
    """Construit l'assortiment S1 mixte pour une ponderation donnee.

    A chaque etape, chaque type est optimise separement sur la demande encore non
    couverte, et l'ajout retenu est celui qui rapporte le plus une fois pondere par
    l'importance du service. Retourne les lignes de gain et la liste ordonnee des
    sites choisis avec leur type.
    """
    service_types = list(config["essential_services"].keys())
    spacing = float(config["optimization"]["site_spacing_m"])
    n_max = config["optimization"]["n_services_max"]
    multiplier = config["optimization"]["out_of_reach_multiplier"]
    out_of_reach = float(config["optimization"]["matrix_cutoff_m"]) * multiplier

    residence_ids = list(residences["residence_id"])
    weights = residences[weight_column].to_numpy(dtype=float)
    total_weight = float(weights.sum())
    total_importance = sum(importance.get(t, 1.0) for t in service_types)

    covered = {
        t: np.array(
            [
                distances_by_type[t].get(rid) is not None
                and distances_by_type[t].get(rid) <= threshold
                for rid in residence_ids
            ]
        )
        for t in service_types
    }

    def weighted_rate():
        weighted_covered = sum(
            importance.get(t, 1.0) * float(weights[covered[t]].sum())
            for t in service_types
        )
        if total_weight == 0.0 or total_importance == 0.0:
            return 0.0
        return weighted_covered / (total_importance * total_weight)

    matrix_work = matrix.copy()
    gain_rows = [
        {
            "n_services": 0,
            "weighting": weighting,
            "added_type": "",
            "site_id": "",
            "covered_percent": round(100.0 * weighted_rate(), 1),
        }
    ]
    selected = []
    for step in range(1, n_max + 1):
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
            logger.info("Plus aucun ajout utile, arret a l'etape %d", step)
            break
        _score, best_type, site_index = best
        newly = matrix[:, site_index] <= threshold
        covered[best_type] = covered[best_type] | newly

        nearby = (
            candidates.geometry.distance(candidates.geometry.iloc[site_index])
            <= spacing
        )
        matrix_work[:, nearby.to_numpy()] = out_of_reach

        selected.append(
            {"step": step, "service_type": best_type, "site_index": site_index}
        )
        gain_rows.append(
            {
                "n_services": step,
                "weighting": weighting,
                "added_type": best_type,
                "site_id": int(candidates.iloc[site_index]["site_id"]),
                "covered_percent": round(100.0 * weighted_rate(), 1),
            }
        )
        logger.info(
            "Assortiment %s, etape %d, ajout %s au site %d",
            weighting,
            step,
            best_type,
            int(candidates.iloc[site_index]["site_id"]),
        )
    return gain_rows, selected


def render_s1_maps(
    layers,
    residences,
    distances_by_type,
    candidates,
    selected,
    importance,
    bands,
    map_steps,
    prefix,
    network_edges,
    config,
    logger,
):
    """Produit les cartes S1 aux paliers, residences recolorees et sites ajoutes."""
    graph = layers["graph"]
    icons = config["visualization"]["service_icons"]
    service_types = list(config["essential_services"].keys())
    maps_folder = config["paths"]["outputs_maps"]

    distances_current = {t: dict(distances_by_type[t]) for t in service_types}
    residence_ids = list(residences["residence_id"])
    node_by_position = list(residences["node"])

    site_rows = []
    for item in selected:
        step = item["step"]
        service_type = item["service_type"]
        site = candidates.iloc[item["site_index"]]
        reached = distances_from_sources(graph, [site["node"]], cutoff=None)
        for position, rid in enumerate(residence_ids):
            new_distance = reached.get(node_by_position[position])
            if new_distance is None:
                continue
            current = distances_current[service_type].get(rid)
            if current is None or new_distance < current:
                distances_current[service_type][rid] = new_distance

        site_rows.append(
            {
                "site_id": int(site["site_id"]),
                "service_type": service_type,
                "icon": icons.get(service_type, "fa-circle"),
                "recommendation": f"ajout numero {step}",
                "geometry": site.geometry,
            }
        )

        if step in map_steps:
            scored = scored_residences(
                residences, distances_current, importance, bands, config
            )
            new_sites = gpd.GeoDataFrame(site_rows, crs=candidates.crs)
            s1_map(
                layers["study_zone"],
                layers["municipalities"],
                scored,
                ordered_service_types(service_types, importance),
                network_edges,
                layers["services"],
                new_sites,
                layers["water"],
                config["visualization"],
                os.path.join(maps_folder, f"{prefix}_n{step}.html"),
                logger,
            )
    return gpd.GeoDataFrame(site_rows, crs=candidates.crs)


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
    max_distance = config["land_use"]["road_max_distance_m"]
    kept = candidates[distances <= max_distance].copy()
    if logger is not None:
        logger.info(
            "Sites candidats pres du reseau, %d sur %d retenus",
            len(kept),
            len(candidates),
        )
    return kept.reset_index(drop=True)


def optimization_s1(
    layers, residences, distances_by_type, network_edges, config, logger
):
    """Optimisation S1, assortiments mixtes pour les deux ponderations, cartes et gains."""
    graph = layers["graph"]
    cutoff = float(config["optimization"]["matrix_cutoff_m"])

    candidates = build_candidate_sites(
        layers["land_use"], config, layers["study_zone"], layers["commercial"], logger
    )
    candidates = filter_candidates_near_road(candidates, graph, config, logger)
    candidates = candidates.drop_duplicates(subset=["node"]).reset_index(drop=True)
    candidates["site_id"] = candidates.index
    logger.info("Sites candidats apres regroupement par noeud, %d", len(candidates))

    residence_nodes = list(residences["node"])
    matrix = distance_matrix(
        graph,
        list(candidates["node"]),
        residence_nodes,
        cutoff,
        config["optimization"]["out_of_reach_multiplier"],
    )
    logger.info(
        "Matrice de distances calculee, %d residences par %d sites", *matrix.shape
    )

    map_files = config["paths"]["map_files"]
    plans = {
        "seniors": (
            "seniors_weight",
            config["importance_seniors"],
            config["quality_bands"]["seniors"],
            config["optimization"]["coverage_threshold_seniors_m"],
            config["optimization"]["map_steps_seniors"],
            map_files["s1_prefix_seniors"],
        ),
        "population_total": (
            "population_weight",
            config["importance_population_total"],
            config["quality_bands"]["population_total"],
            config["optimization"]["coverage_threshold_population_m"],
            config["optimization"]["map_steps_population"],
            map_files["s1_prefix_population"],
        ),
    }
    gain_frames = []
    site_frames = []
    for weighting in config["optimization"]["weightings"]:
        weight_column, importance, bands, threshold, map_steps, prefix = plans[
            weighting
        ]
        gain_rows, selected = build_service_assortment(
            residences,
            distances_by_type,
            candidates,
            matrix,
            weighting,
            importance,
            weight_column,
            float(threshold),
            config,
            logger,
        )
        gain_frames.append(pd.DataFrame(gain_rows))
        sites = render_s1_maps(
            layers,
            residences,
            distances_by_type,
            candidates,
            selected,
            importance,
            bands,
            map_steps,
            prefix,
            network_edges,
            config,
            logger,
        )
        if len(sites) > 0:
            sites = sites.copy()
            sites.insert(0, "population", weighting)
            site_frames.append(sites)
    gains = pd.concat(gain_frames, ignore_index=True)
    recommended = None
    if site_frames:
        recommended = gpd.GeoDataFrame(
            pd.concat(site_frames, ignore_index=True), crs=candidates.crs
        )
    return candidates, gains, recommended
