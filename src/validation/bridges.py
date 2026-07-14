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


def barrier_analysis(layers, residences, services, config, logger):
    """Chiffre l'effet de barriere en coupant les liens qui traversent la riviere."""
    import osmnx as ox

    graph = layers["graph"]
    threshold = config["optimization"]["coverage_threshold_seniors_m"]

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
        os.path.join(config["paths"]["outputs_tables"], "ponts_traversants.csv"),
        logger,
    )
    logger.info(
        "Liens traversant la riviere, %d, franchissabilite confirmee", len(crossings)
    )

    cut_graph = remove_crossing_edges(graph, crossings)
    node_by_residence = dict(zip(residences["residence_id"], residences["node"]))
    seniors_by_residence = dict(
        zip(residences["residence_id"], residences["seniors_weight"])
    )
    with_bridges = {}
    without_bridges = {}
    for scenario, active_graph, target in (
        ("avec", graph, with_bridges),
        ("sans", cut_graph, without_bridges),
    ):
        for service_type in config["essential_services"]:
            type_nodes = services.loc[services["service_type"] == service_type, "node"]
            reached = distances_from_sources(
                active_graph, list(type_nodes), cutoff=threshold
            )
            covered_seniors = sum(
                seniors_by_residence[rid]
                for rid, node in node_by_residence.items()
                if reached.get(node) is not None
            )
            target[service_type] = round(float(covered_seniors), 1)
        logger.info("Scenario %s ponts evalue", scenario)
    return barrier_effect_table(with_bridges, without_bridges)
