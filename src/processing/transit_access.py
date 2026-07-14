"""Acces complementaire aux services par le reseau de transport fixe.

Un service peut etre atteint par le transport en marchant de la residence vers un
arret, en prenant l'autobus, puis en marchant de l'arret d'arrivee vers le service.
Les deux marches doivent rester courtes, sous le seuil de la configuration. La
distance retenue est la plus courte entre la marche directe et cet acces par le
transport. Le reseau fixe local est traite comme un tout connecte, sans horaires,
conformement a la decision documentee dans le README. Cette dimension sert seulement
a la carte S0 de verification.
"""

from __future__ import annotations


def has_transit_access(distance_m, max_distance_m):
    """Indique si une distance de marche donne acces a un arret du reseau."""
    if distance_m is None:
        return False
    return distance_m <= max_distance_m


def effective_transit_distance(
    walk_distance_m, home_to_stop_m, stop_to_service_m, max_stop_distance_m
):
    """Distance effective vers un service en tenant compte du transport.

    home_to_stop_m est la marche de la residence vers l'arret le plus proche.
    stop_to_service_m est la marche du meilleur arret vers le service. Les deux
    marches doivent rester sous le seuil pour que le transport soit utilise. Sinon,
    ou si le transport n'aide pas, la marche directe est conservee.
    """
    if not has_transit_access(home_to_stop_m, max_stop_distance_m):
        return walk_distance_m
    if not has_transit_access(stop_to_service_m, max_stop_distance_m):
        return walk_distance_m
    transit_total = home_to_stop_m + stop_to_service_m
    if walk_distance_m is None:
        return transit_total
    return min(walk_distance_m, transit_total)


def transit_distances_by_type(distances_by_type, home_to_stop, stop_to_service, config):
    """Distances effectives par type sur la carte de verification transport.

    Pour chaque residence, un service peut etre atteint en marchant vers un arret,
    en prenant l'autobus, puis en marchant de l'arret vers le service. La distance
    retenue est la plus courte entre cette chaine et la marche directe.
    """
    max_stop = config["transit"]["max_stop_distance_m"]
    effective = {}
    for service_type, distances in distances_by_type.items():
        service_stop = stop_to_service.get(service_type)
        effective[service_type] = {
            rid: effective_transit_distance(
                distances.get(rid), home_to_stop.get(rid), service_stop, max_stop
            )
            for rid in distances
        }
    return effective
