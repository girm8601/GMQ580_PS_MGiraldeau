"""Reseau pietonnier OpenStreetMap, charge depuis le fichier regenerable.

Le telechargement se fait une seule fois par download_data.py qui ecrit un
fichier GraphML dans data_processed. Ici on charge ce fichier et on projette le
graphe vers le CRS cible pour que toutes les mesures soient en metres.
"""

from __future__ import annotations

import os


def load_walk_graph(config, logger=None):
    """Charge le graphe pietonnier et le projette vers le CRS cible."""
    import osmnx as ox

    path = os.path.join(
        config["paths"]["data_processed"],
        config["paths"]["osm_files"]["walk_graph"],
    )
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Graphe pietonnier introuvable, {path}. Lancer d'abord download_data.py"
        )
    graph = ox.load_graphml(path)
    graph = ox.project_graph(graph, to_crs=config["target_crs"])
    if logger is not None:
        logger.info(
            "Graphe pietonnier charge, %d noeuds et %d liens",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )
    return graph
