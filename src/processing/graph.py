"""Graphe pietonnier et distances de marche par plus court chemin.

Les distances sont mesurees sur le reseau avec l'algorithme de Dijkstra et
le poids length en metres, jamais a vol d'oiseau. Le calcul multi sources
donne en un seul passage la distance de chaque noeud du graphe au service
le plus proche, ce qui reste rapide meme avec des milliers de residences.
"""

from __future__ import annotations

import networkx as nx


def distances_from_sources(graph, source_nodes, cutoff=None, weight="length"):
    """Distance de marche de chaque noeud du graphe vers la source la plus proche.

    Retourne un dictionnaire noeud vers distance en metres. Les noeuds hors
    de portee du cutoff sont absents du dictionnaire. Une liste de sources
    vide retourne un dictionnaire vide plutot qu'une erreur.
    """
    valid_sources = [node for node in source_nodes if graph.has_node(node)]
    if not valid_sources:
        return {}
    return nx.multi_source_dijkstra_path_length(
        graph, valid_sources, cutoff=cutoff, weight=weight
    )


def nearest_graph_nodes(graph, points_gdf):
    """Associe chaque point au noeud du graphe le plus proche (graphe projete).

    L'import d'OSMnx se fait ici pour que les tests des fonctions pures
    n'exigent pas cette dependance.
    """
    import osmnx as ox

    return ox.distance.nearest_nodes(
        graph, points_gdf.geometry.x.values, points_gdf.geometry.y.values
    )
