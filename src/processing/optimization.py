"""Optimisation par couverture maximale avec spopt, scenarios S1.

Pour chaque nombre de services de n_services_min a n_services_max, le modele
choisit les sites candidats qui couvrent la plus grande demande encore non
couverte sous le seuil de marche. La demande est ponderee par les aines, puis
par la population totale pour l'analyse de sensibilite d'equite.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.processing.graph import distances_from_sources


def distance_matrix(graph, candidate_nodes, demand_nodes, threshold_m):
    """Matrice des distances de marche entre demande et candidats.

    Un passage de Dijkstra par candidat, borne au seuil, remplit une colonne.
    Les paires hors de portee recoivent une valeur superieure au seuil pour
    que le modele les considere non couvertes.
    """
    out_of_reach = float(threshold_m) * 10.0
    matrix = np.full((len(demand_nodes), len(candidate_nodes)), out_of_reach)
    demand_index = {node: i for i, node in enumerate(demand_nodes)}
    for j, candidate_node in enumerate(candidate_nodes):
        reached = distances_from_sources(graph, [candidate_node], cutoff=threshold_m)
        for node, distance in reached.items():
            i = demand_index.get(node)
            if i is not None and distance < matrix[i, j]:
                matrix[i, j] = distance
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


def gain_curve(cost_matrix, weights, threshold_m, n_min, n_max, solver=None):
    """Courbe de gain, demande couverte selon le nombre de services ajoutes."""
    rows = []
    for n_facilities in range(n_min, n_max + 1):
        selected, covered_demand = solve_mclp(
            cost_matrix, weights, threshold_m, n_facilities, solver=solver
        )
        rows.append(
            {
                "n_services": n_facilities,
                "demande_couverte": covered_demand,
                "sites_choisis": selected,
            }
        )
    return pd.DataFrame(rows)
