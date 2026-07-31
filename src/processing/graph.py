"""Graphe pietonnier et distances de marche par plus court chemin.

Les distances sont mesurees sur le reseau avec l'algorithme de Dijkstra et le poids length
en metres, jamais a vol d'oiseau. Le calcul multi sources donne en un seul passage la
distance de chaque noeud du graphe a la source la plus proche, ce qui reste rapide meme
avec des milliers de residences.

Un point n'est jamais exactement sur le reseau, il est accroche au noeud le plus proche et
un ecart subsiste. Cet ecart est la derniere portion de marche, il compte dans toute
distance mesuree. Sans lui, une maison a un kilometre du reseau heriterait de
l'accessibilite du noeud sur lequel elle est accrochee. Il est porte jusqu'au calcul par un
noeud virtuel relie a chaque source par une arete egale a son ecart.
"""

from __future__ import annotations

import networkx as nx

# Nom du noeud ajoute puis retire pour porter les ecarts d'accrochage des sources.
VIRTUAL_SOURCE = "source_virtuelle"


def distances_from_sources(graph, source_nodes, cutoff=None, weight="length"):
    """Distance de marche de chaque noeud du graphe vers la source la plus proche.

    Retourne un dictionnaire noeud vers distance en metres. Les noeuds hors de portee du
    cutoff sont absents du dictionnaire. Une liste de sources vide retourne un dictionnaire
    vide plutot qu'une erreur. Les ecarts d'accrochage ne sont pas comptes ici, voir
    distances_from_snapped_sources.
    """
    valid_sources = [node for node in source_nodes if graph.has_node(node)]
    if not valid_sources:
        return {}
    return nx.multi_source_dijkstra_path_length(
        graph, valid_sources, cutoff=cutoff, weight=weight
    )


def distances_from_snapped_sources(graph, offset_by_node, cutoff=None, weight="length"):
    """Distance de marche de chaque noeud vers la source la plus proche, ecart compris.

    offset_by_node donne l'ecart d'accrochage de chaque noeud source. Un noeud virtuel est
    relie a chaque source par une arete egale a son ecart, un seul Dijkstra depuis ce noeud
    virtuel donne alors le minimum sur les sources de l'ecart plus le trajet sur le reseau.
    Le cutoff porte donc bien sur la distance depuis le point reel. Le noeud virtuel est
    retire avant que le resultat soit rendu, meme si le calcul echoue.
    """
    valid = {
        node: float(offset)
        for node, offset in offset_by_node.items()
        if graph.has_node(node)
    }
    if not valid:
        return {}
    graph.add_node(VIRTUAL_SOURCE)
    for node, offset in valid.items():
        graph.add_edge(VIRTUAL_SOURCE, node, **{weight: offset})
    try:
        reached = nx.single_source_dijkstra_path_length(
            graph, VIRTUAL_SOURCE, cutoff=cutoff, weight=weight
        )
    finally:
        graph.remove_node(VIRTUAL_SOURCE)
    reached.pop(VIRTUAL_SOURCE, None)
    return reached


def smallest_offset_by_node(nodes, offsets):
    """Ecart d'accrochage minimal par noeud, quand plusieurs points partagent un noeud.

    Deux services accroches au meme noeud n'en sont pas a la meme distance. Le plus proche
    decide, c'est lui qu'un pieton atteindra en premier.
    """
    smallest = {}
    for node, offset in zip(nodes, offsets):
        if node not in smallest or offset < smallest[node]:
            smallest[node] = float(offset)
    return smallest


def nearest_graph_nodes(graph, points_gdf):
    """Associe chaque point au noeud du graphe le plus proche (graphe projete).

    L'import d'OSMnx se fait ici pour que les tests des fonctions pures n'exigent pas cette
    dependance.
    """
    import osmnx as ox

    return list(
        ox.distance.nearest_nodes(
            graph, points_gdf.geometry.x.values, points_gdf.geometry.y.values
        )
    )


def snap_points(graph, points_gdf):
    """Accroche chaque point au reseau et mesure l'ecart qui reste.

    Retourne la liste des noeuds accroches et la liste des ecarts en metres, dans l'ordre
    des points. L'ecart est la derniere portion de marche entre le point et le reseau.
    """
    import geopandas as gpd
    import osmnx as ox

    nodes = nearest_graph_nodes(graph, points_gdf)
    node_geometry = ox.graph_to_gdfs(graph, edges=False).geometry
    snapped = gpd.GeoSeries(
        [node_geometry.loc[node] for node in nodes], crs=points_gdf.crs
    )
    points = gpd.GeoSeries(points_gdf.geometry.values, crs=points_gdf.crs)
    offsets = points.distance(snapped, align=False)
    return nodes, [float(offset) for offset in offsets]
