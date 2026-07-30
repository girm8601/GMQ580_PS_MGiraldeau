"""Distance effective vers un service, marche seule ou marche plus transport.

Un service peut etre atteint a pied directement, ou par le transport en marchant vers un
arret, en prenant l'autobus ou le train sans transfert, puis en marchant de l'arret
d'arrivee vers le service. La marche totale du trajet est la somme des deux marches, et
elle doit rester sous le total acceptable du groupe, 800 metres pour un aine et 1000
metres pour le reste de la population. Le trajet a bord ne compte pas dans ce total.

La distance retenue pour la cote d'une residence est la plus courte des deux, la marche
directe ou la marche totale du trajet. Si le service est plus proche a pied, c'est la
marche seule qui compte. Le meme calcul sert aux terrains candidats du levier.
"""

from __future__ import annotations


def total_walk(home_walk_m, service_walk_m, max_total_walk_m):
    """Marche totale d'un trajet, None si une marche manque ou si le total depasse.

    home_walk_m est la marche vers l'arret de depart, service_walk_m la marche de l'arret
    d'arrivee vers le service. Les deux arrets sont sur la meme ligne.
    """
    if home_walk_m is None or service_walk_m is None:
        return None
    total = home_walk_m + service_walk_m
    return total if total <= max_total_walk_m else None


def best_route_walk(node, route_walk, walk_by_route, service_type, max_total_walk_m):
    """Marche totale la plus courte vers un type de service, toutes lignes confondues.

    Chaque ligne est essayee, la marche du noeud vers cette ligne plus la marche de cette
    ligne vers le service. La meilleure ligne est retenue. Retourne None si aucune ligne
    ne donne un trajet acceptable.
    """
    best = None
    for route_id, reached in route_walk.items():
        candidate = total_walk(
            reached.get(node),
            walk_by_route.get(route_id, {}).get(service_type),
            max_total_walk_m,
        )
        if candidate is not None and (best is None or candidate < best):
            best = candidate
    return best


def effective_distance(walk_distance_m, transit_walk_m):
    """La plus courte entre la marche directe et la marche totale par le transport."""
    if transit_walk_m is None:
        return walk_distance_m
    if walk_distance_m is None:
        return transit_walk_m
    return min(walk_distance_m, transit_walk_m)


def transit_walk_by_node(
    nodes, route_walk, walk_by_route, service_type, max_total_walk_m
):
    """Marche totale la plus courte par le transport, pour chaque noeud demande.

    Le calcul se fait par noeud du graphe et non par point, car plusieurs residences
    partagent le meme noeud d'accrochage. Cela evite de refaire le meme travail.
    """
    return {
        node: best_route_walk(
            node, route_walk, walk_by_route, service_type, max_total_walk_m
        )
        for node in nodes
    }


def transit_distances_by_type(
    distances_by_type, node_by_point, route_walk, walk_by_route, max_total_walk_m
):
    """Distances effectives par type de service en tenant compte du transport.

    distances_by_type donne la marche directe de chaque point vers chaque type de
    service. node_by_point donne le noeud du graphe de chaque point. max_total_walk_m est
    la marche totale acceptable du groupe. Retourne la meme structure que l'entree, avec
    la plus courte des deux distances.
    """
    nodes = list(dict.fromkeys(node_by_point.values()))
    effective = {}
    for service_type, distances in distances_by_type.items():
        by_node = transit_walk_by_node(
            nodes, route_walk, walk_by_route, service_type, max_total_walk_m
        )
        effective[service_type] = {
            point_id: effective_distance(
                distance, by_node.get(node_by_point.get(point_id))
            )
            for point_id, distance in distances.items()
        }
    return effective
