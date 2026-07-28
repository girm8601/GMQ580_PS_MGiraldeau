"""Franchissabilite pietonne des ponts sur le Richelieu.

La riviere separe la rive ouest (Beloeil, McMasterville) de la rive est
(Mont-Saint-Hilaire, Otterburn Park). Un lien du graphe pietonnier qui relie un
noeud de chaque rive traverse forcement la riviere. Ce module identifie ces
liens, produit un rapport verifiable et permet de les retirer pour chiffrer
l'effet de barriere, qui reste faible.
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd

from src.processing.graph import distances_from_sources
from src.results.metrics import barrier_effect_table, export_table


def classify_banks(nodes_gdf, municipalities_gdf, west_names, east_names, name_field):
    """Associe chaque noeud du graphe a sa rive selon la municipalite qui le contient.

    Retourne un dictionnaire noeud vers rive (west ou east). Les noeuds hors des
    municipalites connues restent absents du dictionnaire.
    """
    bank_by_name = {name: "west" for name in west_names}
    bank_by_name.update({name: "east" for name in east_names})

    joined = gpd.sjoin(
        nodes_gdf,
        municipalities_gdf[[name_field, "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined[~joined.index.duplicated(keep="first")]

    banks = {}
    for node_id, municipality in joined[name_field].items():
        bank = bank_by_name.get(municipality)
        if bank is not None:
            banks[node_id] = bank
    return banks


def find_crossing_edges(graph, banks):
    """Retourne les liens (u, v, cle) dont les extremites sont sur des rives opposees."""
    crossings = []
    for u, v, key in graph.edges(keys=True):
        bank_u = banks.get(u)
        bank_v = banks.get(v)
        if bank_u is not None and bank_v is not None and bank_u != bank_v:
            crossings.append((u, v, key))
    return crossings


def crossing_report(graph, crossings):
    """Construit un tableau verifiable des liens traversants avec leurs attributs OSM."""
    rows = []
    for u, v, key in crossings:
        data = graph.get_edge_data(u, v, key) or {}
        rows.append(
            {
                "west_or_start_node": u,
                "east_or_end_node": v,
                "name": str(data.get("name", "")),
                "highway": str(data.get("highway", "")),
                "bridge": str(data.get("bridge", "")),
                "length_m": round(float(data.get("length", 0.0)), 1),
            }
        )
    return pd.DataFrame(rows)


def remove_crossing_edges(graph, crossings):
    """Retourne une copie du graphe sans les liens traversants (scenario barriere)."""
    cut_graph = graph.copy()
    for u, v, key in crossings:
        if cut_graph.has_edge(u, v, key):
            cut_graph.remove_edge(u, v, key)
    return cut_graph


def _covered_weight(
    graph, type_nodes, threshold, node_by_residence, weight_by_residence
):
    """Poids de demande couvert par un type de service sous le seuil, sur un graphe donne."""
    reached = distances_from_sources(graph, type_nodes, cutoff=threshold)
    return sum(
        weight_by_residence[rid]
        for rid, node in node_by_residence.items()
        if reached.get(node) is not None
    )


def barrier_analysis(layers, residences, services, config, logger):
    """Chiffre l'effet de barriere par groupe et par service en coupant les liens du pont.

    Pour chaque groupe a son seuil, aines a 800 m et reste a 1000 m, on compte la demande
    couverte par type de service avec les ponts puis sans les ponts. L'ecart est l'effet de
    barriere, qui reste faible.
    """
    import osmnx as ox

    graph = layers["graph"]
    nodes_gdf = ox.graph_to_gdfs(graph, edges=False)
    banks = classify_banks(
        nodes_gdf,
        layers["municipalities"],
        config["study_area"]["west_bank"],
        config["study_area"]["east_bank"],
        config["study_area"]["municipality_name_field"],
    )
    crossings = find_crossing_edges(graph, banks)
    report = crossing_report(graph, crossings)
    export_table(
        report,
        os.path.join(
            config["paths"]["outputs_tables"],
            config["paths"]["table_files"]["crossing_bridges"],
        ),
        logger,
    )
    logger.info(
        "Liens traversant la riviere, %d, franchissabilite confirmee", len(crossings)
    )

    cut_graph = remove_crossing_edges(graph, crossings)
    node_by_residence = dict(zip(residences["residence_id"], residences["node"]))
    groups = [
        (
            "seniors",
            "seniors_weight",
            config["optimization"]["coverage_threshold_seniors_m"],
        ),
        ("rest", "rest_weight", config["optimization"]["coverage_threshold_rest_m"]),
    ]
    rows = []
    for group_label, weight_column, threshold in groups:
        weight_by_residence = dict(
            zip(residences["residence_id"], residences[weight_column])
        )
        group_total = round(float(sum(weight_by_residence.values())), 1)
        for service_type in config["essential_services"]:
            type_nodes = list(
                services.loc[services["service_type"] == service_type, "node"]
            )
            covered_with = _covered_weight(
                graph, type_nodes, threshold, node_by_residence, weight_by_residence
            )
            covered_without = _covered_weight(
                cut_graph, type_nodes, threshold, node_by_residence, weight_by_residence
            )
            rows.append(
                {
                    "group": group_label,
                    "service_type": service_type,
                    "threshold_m": threshold,
                    "covered_with_bridges_persons": round(float(covered_with), 1),
                    "covered_without_bridges_persons": round(float(covered_without), 1),
                    "group_total_persons": group_total,
                }
            )
        logger.info("Effet de barriere evalue pour %s", group_label)
    return barrier_effect_table(rows)
