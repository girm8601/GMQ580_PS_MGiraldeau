"""Lignes du reseau fixe, un trajet sans transfert.

Un deplacement par le transport se fait en trois temps. La marche de la residence vers
un arret, le trajet a bord, puis la marche de l'arret d'arrivee vers le service. Les
deux arrets appartiennent a la meme ligne, le projet ne modelise aucun transfert car les
correspondances possibles ne sont pas connues. La distance retenue est la somme des deux
marches, le trajet a bord ne compte pas puisque le seuil porte sur la marche.

Ce module rattache les arrets de chaque ligne au graphe pietonnier, puis mesure en une
seule passe de Dijkstra par ligne la marche de chaque noeud du graphe vers l'arret le
plus proche de cette ligne. La meme passe sert ensuite aux residences, aux services et
aux terrains candidats. La ligne de train exo est traitee comme une ligne de plus, ses
deux gares relient les deux rives.
"""

from __future__ import annotations

from src.processing.graph import distances_from_sources, nearest_graph_nodes


def route_stop_nodes(route_stops, stops_gdf, stop_id_field):
    """Noeuds du graphe desservis par chaque ligne.

    route_stops associe chaque ligne a ses identifiants d'arrets. stops_gdf porte les
    arrets conserves dans la zone d'etude avec leur colonne node. Une ligne dont aucun
    arret n'est conserve est absente du resultat.
    """
    node_by_stop = dict(zip(stops_gdf[stop_id_field], stops_gdf["node"]))
    nodes_by_route = {}
    for route_id, stop_ids in route_stops.items():
        nodes = [node_by_stop[s] for s in stop_ids if s in node_by_stop]
        if nodes:
            nodes_by_route[route_id] = list(dict.fromkeys(nodes))
    return nodes_by_route


def walk_to_each_route(graph, nodes_by_route, max_total_walk_m):
    """Marche de chaque noeud du graphe vers l'arret le plus proche de chaque ligne.

    La recherche est bornee a la marche totale maximale. Une marche plus longue que ce
    total ne peut de toute facon pas faire partie d'un deplacement acceptable, puisque
    l'autre marche du trajet est au mieux nulle.
    """
    return {
        route_id: distances_from_sources(graph, nodes, cutoff=max_total_walk_m)
        for route_id, nodes in nodes_by_route.items()
    }


def route_to_service_walk(route_walk, nodes_by_type):
    """Marche de chaque ligne vers le service le plus proche de chaque type.

    Pour une ligne et un type de service, c'est la plus courte marche entre un arret de
    la ligne et un service de ce type. Un type hors de portee de la ligne recoit None.
    """
    walk_by_route = {}
    for route_id, reached in route_walk.items():
        walk_by_route[route_id] = {}
        for service_type, nodes in nodes_by_type.items():
            reachable = [reached[node] for node in nodes if node in reached]
            walk_by_route[route_id][service_type] = (
                min(reachable) if reachable else None
            )
    return walk_by_route


def prepare_route_access(layers, nodes_by_type, config, logger):
    """Prepare l'acces par le transport, une passe de marche par ligne du reseau fixe.

    Retourne la marche de chaque noeud vers chaque ligne et la marche de chaque ligne
    vers chaque type de service. Les deux servent ensuite a la marche totale d'un
    deplacement sans transfert, pour les residences comme pour les terrains candidats.
    """
    graph = layers["graph"]
    transit = config["transit"]
    stop_id_field = transit["gtfs_fields"]["stop_id"]

    stops = layers["stops"].copy()
    stops["node"] = nearest_graph_nodes(graph, stops)
    nodes_by_route = route_stop_nodes(layers["route_stops"], stops, stop_id_field)

    # Le train est une ligne de plus, ses deux gares joignent les deux rives.
    stations = layers["stations"]
    if stations is not None and len(stations) > 0:
        station_nodes = list(dict.fromkeys(nearest_graph_nodes(graph, stations)))
        nodes_by_route[transit["context_train_line"]] = station_nodes

    max_total = max(
        transit["max_total_walk_seniors_m"], transit["max_total_walk_rest_m"]
    )
    route_walk = walk_to_each_route(graph, nodes_by_route, max_total)
    walk_by_route = route_to_service_walk(route_walk, nodes_by_type)
    logger.info(
        "Lignes du reseau fixe preparees, %d ligne(s) desservant la zone",
        len(nodes_by_route),
    )
    return route_walk, walk_by_route
