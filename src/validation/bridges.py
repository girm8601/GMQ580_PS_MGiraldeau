"""Franchissabilite pietonne des ponts sur le Richelieu.

La riviere separe la rive ouest (Beloeil, McMasterville) de la rive est
(Mont-Saint-Hilaire, Otterburn Park). Un lien du graphe pietonnier qui relie un
noeud de chaque rive traverse forcement la riviere. Ce module identifie ces
liens, produit un rapport verifiable et permet de les retirer pour chiffrer
l'effet de barriere, qui reste faible.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from src.processing.graph import distances_from_snapped_sources, smallest_offset_by_node
from src.results.metrics import barrier_effect_table


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


def _covered_weight(graph, snapped, threshold, snapped_residences, weight_by_residence):
    """Poids de demande couvert par un type de service sous le seuil, sur un graphe donne.

    snapped donne les couples noeud et ecart des services du type, snapped_residences ceux
    des residences. Les deux ecarts comptent dans la distance, comme partout ailleurs.
    """
    reached = distances_from_snapped_sources(
        graph,
        smallest_offset_by_node(
            [node for node, _ in snapped], [snap for _, snap in snapped]
        ),
        cutoff=threshold,
    )
    covered = 0.0
    for residence_id, (node, snap_m) in snapped_residences.items():
        distance = reached.get(node)
        if distance is not None and distance + snap_m <= threshold:
            covered += weight_by_residence[residence_id]
    return covered


def river_polygon(water_gdf, municipalities_gdf, west_names, east_names, name_field):
    """Le plan d'eau qui separe les deux rives, la riviere Richelieu.

    La couche d'eau porte aussi un lac et une vingtaine d'etangs. Seul le polygone qui
    touche a la fois une municipalite de l'ouest et une de l'est fait barriere entre les
    deux rives, c'est la definition meme de l'effet mesure ici. Retourne None si aucun
    polygone ne separe les deux rives.
    """
    if water_gdf is None or len(water_gdf) == 0:
        return None
    west = municipalities_gdf[
        municipalities_gdf[name_field].isin(west_names)
    ].union_all()
    east = municipalities_gdf[
        municipalities_gdf[name_field].isin(east_names)
    ].union_all()
    separating = water_gdf[
        water_gdf.geometry.intersects(west) & water_gdf.geometry.intersects(east)
    ]
    return separating.union_all() if len(separating) > 0 else None


def unclassified_edges(edge_keys, banks):
    """Parmi des liens donnes, ceux dont au moins une extremite n'a pas de rive connue."""
    return [
        (u, v, key)
        for u, v, key in edge_keys
        if banks.get(u) is None or banks.get(v) is None
    ]


def river_edges_without_bank(graph, river, banks):
    """Liens qui coupent la riviere sans rive connue aux deux bouts, les ponts suspects.

    Trois cas coupent la riviere. Un lien entre deux rives opposees est un pont, il est deja
    detecte. Un lien dont les deux bouts sont sur la meme rive est un sentier de berge qui
    coupe une anse, c'est normal et la zone en compte six. Reste le cas ou une extremite
    n'appartient a aucune municipalite connue. Un noeud pose au milieu d'un pont produirait
    exactement ce cas, et le pont echapperait alors a la detection par les rives. Retourne
    None si la riviere ou les geometries de liens sont absentes.
    """
    import osmnx as ox

    if river is None:
        return None
    edges = ox.graph_to_gdfs(graph, nodes=False)
    if "geometry" not in edges.columns:
        return None
    crossing = edges[edges.geometry.crosses(river)]
    return unclassified_edges(list(crossing.index), banks)


def _check_bridge_detection(graph, river, banks, crossings, logger):
    """Verifie qu'aucun lien franchissant la riviere n'a echappe a la detection."""
    suspects = river_edges_without_bank(graph, river, banks)
    if suspects is None:
        logger.warning(
            "Riviere introuvable dans la couche d'eau, la detection des ponts n'a pas pu "
            "etre recoupee"
        )
        return
    if suspects:
        logger.warning(
            "Detection des ponts a verifier, %d lien(s) coupent la riviere sans rive "
            "connue aux deux bouts",
            len(suspects),
        )
        return
    logger.info(
        "Detection des ponts recoupee, %d lien(s) de pont et aucun lien de riviere sans "
        "rive connue",
        len(crossings),
    )


def barrier_analysis(layers, residences, snapped_by_type, config, logger):
    """Chiffre l'effet de barriere par groupe et par service en coupant les liens du pont.

    Pour chaque groupe a son seuil, aines a 800 m et reste a 1000 m, on compte la demande
    couverte par type de service avec les ponts puis sans les ponts. L'ecart est l'effet de
    barriere, qui reste faible. snapped_by_type donne les couples noeud et ecart des services
    de chaque type. Retourne le tableau d'effet et le tableau verifiable des liens
    traversants, que l'appelant exporte comme les autres tableaux.
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
    logger.info(
        "Liens traversant la riviere, %d, franchissabilite confirmee", len(crossings)
    )
    river = river_polygon(
        layers.get("water"),
        layers["municipalities"],
        config["study_area"]["west_bank"],
        config["study_area"]["east_bank"],
        config["study_area"]["municipality_name_field"],
    )
    _check_bridge_detection(graph, river, banks, crossings, logger)

    cut_graph = remove_crossing_edges(graph, crossings)
    snapped_residences = dict(
        zip(residences["residence_id"], zip(residences["node"], residences["snap_m"]))
    )
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
            snapped = snapped_by_type[service_type]
            covered_with = _covered_weight(
                graph, snapped, threshold, snapped_residences, weight_by_residence
            )
            covered_without = _covered_weight(
                cut_graph, snapped, threshold, snapped_residences, weight_by_residence
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
    return barrier_effect_table(rows), report
