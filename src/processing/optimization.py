"""Optimisation par couverture maximale avec spopt.

Le modele choisit les sites candidats qui couvrent la plus grande demande sous le
seuil de marche. Ce noyau sert au levier de logement, choisir les meilleurs terrains
brownfield pour les aines, et a la validation qui montre que l'ajout de services ne
rapporte pas assez. Les scenarios eux memes sont construits dans scenarios.py.
"""

from __future__ import annotations

import numpy as np

from src.processing.graph import distances_from_sources


def distance_matrix(
    graph, candidate_nodes, demand_nodes, threshold_m, out_of_reach_multiplier
):
    """Matrice des distances de marche entre demande et candidats.

    Un passage de Dijkstra par candidat, borne au seuil, remplit une colonne. Les
    paires hors de portee recoivent une valeur superieure au seuil pour que le
    modele les considere non couvertes. Le multiplicateur vient de la configuration,
    aucune valeur par defaut ne le duplique ici.
    """
    out_of_reach = float(threshold_m) * out_of_reach_multiplier
    matrix = np.full((len(demand_nodes), len(candidate_nodes)), out_of_reach)
    demand_index = {}
    for i, node in enumerate(demand_nodes):
        demand_index.setdefault(node, []).append(i)
    for j, candidate_node in enumerate(candidate_nodes):
        reached = distances_from_sources(graph, [candidate_node], cutoff=threshold_m)
        for node, distance in reached.items():
            for i in demand_index.get(node, ()):
                matrix[i, j] = min(matrix[i, j], distance)
    return matrix


def solve_mclp(cost_matrix, weights, threshold_m, n_facilities, solver=None):
    """Resout la couverture maximale et retourne les sites choisis.

    Retourne les indices des sites retenus et la demande couverte. La demande
    deja couverte au depart doit etre retiree des poids par l'appelant.
    """
    import pulp
    from spopt.locate import MCLP

    if solver is None:
        solver = pulp.PULP_CBC_CMD(msg=False)

    model = MCLP.from_cost_matrix(
        cost_matrix,
        np.asarray(weights, dtype=float),
        threshold_m,
        p_facilities=n_facilities,
    )
    model = model.solve(solver)

    selected = [
        j for j in range(cost_matrix.shape[1]) if model.fac_vars[j].value() > 0.5
    ]
    covered_mask = np.zeros(cost_matrix.shape[0], dtype=bool)
    for j in selected:
        covered_mask |= cost_matrix[:, j] <= threshold_m
    covered_demand = float(np.asarray(weights, dtype=float)[covered_mask].sum())
    return selected, covered_demand
