"""Optimisation par couverture maximale avec spopt.

Le modele choisit les sites candidats qui couvrent la plus grande demande sous le seuil de
marche (Church and ReVelle, 1974). Il sert deux fois dans la validation d'ajout de
services. Une fois par etape de l'assortiment, ou il place un seul service sur la demande
encore non couverte. Une fois pour la borne superieure du gain, ou il place les cinq
services d'un coup et donne donc le vrai optimum et non un choix glouton. Les deux
scenarios eux memes sont construits dans service_addition.py.

La demande est agregee avant d'entrer ici, par noeud du graphe et par classe d'ecart
d'accrochage. Le modele reste exactement le meme, il compte simplement bien moins de lignes,
ce qui le rend rapide.

Chaque point porte son ecart d'accrochage au reseau. Une distance de la matrice est donc
l'ecart du candidat, plus le trajet sur le reseau, plus l'ecart du point de demande.
"""

from __future__ import annotations

import numpy as np

from src.processing.graph import distances_from_snapped_sources


def distance_matrix(graph, candidates, demand, threshold_m, out_of_reach_multiplier):
    """Matrice des distances de marche entre demande et candidats.

    candidates et demand sont des listes de couples noeud et ecart d'accrochage. Un passage
    de Dijkstra par candidat, borne au seuil et parti d'un noeud virtuel qui porte l'ecart du
    candidat, remplit une colonne. L'ecart du point de demande s'ajoute ensuite. Les paires
    hors de portee recoivent une valeur superieure au seuil pour que le modele les considere
    non couvertes. Le multiplicateur vient de la configuration, aucune valeur par defaut ne le
    duplique ici.
    """
    out_of_reach = float(threshold_m) * out_of_reach_multiplier
    matrix = np.full((len(demand), len(candidates)), out_of_reach)
    demand_index = {}
    for i, (node, snap_m) in enumerate(demand):
        demand_index.setdefault(node, []).append((i, snap_m))
    for j, (candidate_node, candidate_snap) in enumerate(candidates):
        reached = distances_from_snapped_sources(
            graph, {candidate_node: candidate_snap}, cutoff=threshold_m
        )
        for node, distance in reached.items():
            for i, demand_snap in demand_index.get(node, ()):
                total = distance + demand_snap
                if total <= threshold_m:
                    matrix[i, j] = min(matrix[i, j], total)
    return matrix


def solve_mclp(cost_matrix, weights, threshold_m, n_facilities, solver=None):
    """Resout la couverture maximale avec spopt et retourne les sites choisis.

    Retourne les indices des sites retenus et la demande couverte. La demande deja couverte
    au depart doit etre retiree des poids par l'appelant, le modele travaille alors sur ce
    qu'il reste a gagner.
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
