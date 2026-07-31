# Objectif, verifier l'acces par le transport, un trajet sans transfert dont la marche
# totale respecte le seuil du groupe, sur un mini reseau aux reponses connues.

import networkx as nx
import pandas as pd

from src.extraction.transit import fixed_route_stop_ids, stops_by_fixed_route
from src.processing.transit_access import (
    best_route_walk,
    effective_distance,
    total_walk,
    transit_distances_by_type,
)
from src.processing.transit_routes import (
    route_stop_offsets,
    route_to_service_walk,
    walk_to_each_route,
)

GTFS_FIELDS = {
    "route_id": "route_id",
    "route_type": "route_type",
    "trip_id": "trip_id",
    "stop_id": "stop_id",
}


def make_gtfs():
    """Deux lignes fixes et une ligne a la demande, avec leurs arrets."""
    routes = pd.DataFrame(
        {"route_id": ["10", "20", "T99"], "route_type": ["3", "3", "1501"]}
    )
    trips = pd.DataFrame(
        {"trip_id": ["v1", "v2", "v3"], "route_id": ["10", "20", "T99"]}
    )
    stop_times = pd.DataFrame(
        {
            "trip_id": ["v1", "v1", "v2", "v2", "v3"],
            "stop_id": ["a", "b", "b", "c", "z"],
        }
    )
    return routes, trips, stop_times


def test_fixed_routes_only():
    """La ligne a la demande et son arret doivent etre ecartes."""
    route_stops = stops_by_fixed_route(*make_gtfs(), [3], GTFS_FIELDS)
    assert sorted(route_stops) == ["10", "20"]
    assert route_stops["10"] == ["a", "b"]
    assert fixed_route_stop_ids(route_stops) == {"a", "b", "c"}


def test_total_walk_respects_the_group_threshold():
    """La somme des deux marches doit rester sous le total acceptable."""
    assert total_walk(300, 400, 800) == 700
    assert total_walk(500, 400, 800) is None
    assert total_walk(300, None, 800) is None
    assert total_walk(None, 400, 800) is None


def make_route_network():
    """Deux lignes, la ligne proche est mal placee et la ligne loin est bien placee."""
    # Ligne proche, 100 m de la maison mais 900 m du service, total 1000 m.
    # Ligne loin, 400 m de la maison et 200 m du service, total 600 m.
    route_walk = {
        "proche": {"maison": 100.0, "epicerie": 900.0},
        "loin": {"maison": 400.0, "epicerie": 200.0},
    }
    # L'epicerie est pile sur son noeud, son ecart d'accrochage est nul.
    walk_by_route = route_to_service_walk(
        route_walk, {"supermarket": [("epicerie", 0.0)]}
    )
    return route_walk, walk_by_route


def test_best_route_is_the_shortest_total_not_the_nearest_stop():
    """La ligne retenue est celle qui donne la plus courte marche totale."""
    route_walk, walk_by_route = make_route_network()
    assert best_route_walk(
        "maison", 0.0, route_walk, walk_by_route, "supermarket", 800
    ) == (600.0)


def test_no_route_within_the_threshold():
    """Aucun trajet acceptable doit donner None, jamais une valeur approximative."""
    route_walk, walk_by_route = make_route_network()
    assert (
        best_route_walk("maison", 0.0, route_walk, walk_by_route, "supermarket", 500)
        is None
    )


def test_walking_wins_when_the_service_is_closer():
    """Si le service est plus proche a pied, c'est la marche seule qui compte."""
    assert effective_distance(250, 600) == 250
    assert effective_distance(1500, 600) == 600
    assert effective_distance(1500, None) == 1500
    assert effective_distance(None, 600) == 600


def test_distances_by_type_keeps_the_shortest_of_the_two():
    """Chaque point garde la plus courte des deux distances, marche seule ou transport."""
    route_walk, walk_by_route = make_route_network()
    # La residence 1 est loin a pied, le transport l'aide. La residence 2 est deja proche.
    walk_distances = {"supermarket": {1: 2000.0, 2: 150.0}}
    node_and_snap = {1: ("maison", 0.0), 2: ("maison", 0.0)}
    effective = transit_distances_by_type(
        walk_distances, node_and_snap, route_walk, walk_by_route, 800
    )
    assert effective["supermarket"][1] == 600.0
    assert effective["supermarket"][2] == 150.0


def test_the_snap_gap_of_the_starting_point_counts():
    """Un point a 250 m du reseau doit voir ces 250 m s'ajouter a sa marche vers la ligne.

    Sans cet ecart, une maison loin du reseau heriterait de l'accessibilite de son noeud
    d'accrochage. La ligne loin donne un total de 600 m, plus 250 m d'ecart le trajet passe a
    850 m et depasse le seuil de 800 m.
    """
    route_walk, walk_by_route = make_route_network()
    assert (
        best_route_walk("maison", 250.0, route_walk, walk_by_route, "supermarket", 800)
        is None
    )
    assert best_route_walk(
        "maison", 250.0, route_walk, walk_by_route, "supermarket", 900
    ) == (850.0)


def make_walk_graph():
    """Graphe en ligne, la maison est au noeud 1 et deux arrets sont plus loin."""
    graph = nx.Graph()
    graph.add_edge(1, 2, length=100.0)
    graph.add_edge(2, 3, length=200.0)
    graph.add_edge(3, 4, length=1000.0)
    return graph


def test_walk_to_each_route_carries_the_stop_snap_gap():
    """L'ecart d'accrochage de l'arret s'ajoute a la marche vers sa ligne.

    L'arret a est sur le noeud 3, a 300 m du noeud 1, et il est lui meme a 40 m de son noeud.
    La marche de la maison vers cette ligne vaut donc 340 m.
    """
    graph = make_walk_graph()
    stops = pd.DataFrame({"stop_id": ["a", "b"], "node": [3, 4], "snap_m": [40.0, 0.0]})
    offsets = route_stop_offsets({"10": ["a"], "20": ["b"]}, stops, "stop_id")
    assert offsets == {"10": {3: 40.0}, "20": {4: 0.0}}
    route_walk = walk_to_each_route(graph, offsets, 800)
    assert route_walk["10"][1] == 340.0
    assert 1 not in route_walk["20"]


def test_route_without_kept_stop_is_dropped():
    """Une ligne dont aucun arret n'est conserve dans la zone est absente du resultat."""
    stops = pd.DataFrame({"stop_id": ["a"], "node": [3], "snap_m": [0.0]})
    assert route_stop_offsets({"20": ["hors_zone"]}, stops, "stop_id") == {}
