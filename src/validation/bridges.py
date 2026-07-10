"""Franchissabilite pietonne des ponts sur le Richelieu.

La riviere separe la rive ouest (Beloeil, McMasterville) de la rive est
(Mont-Saint-Hilaire, Otterburn Park). Un lien du graphe pietonnier qui relie
un noeud de chaque rive traverse forcement la riviere. Ce module identifie
ces liens, produit un rapport verifiable et permet de les retirer pour
chiffrer l'effet de barriere.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def classify_banks(nodes_gdf, municipalities_gdf, west_names, east_names, name_field):
    """Associe chaque noeud du graphe a sa rive selon la municipalite qui le contient.

    Retourne un dictionnaire noeud vers rive (ouest ou est). Les noeuds hors
    des municipalites connues restent absents du dictionnaire.
    """
    bank_by_name = {name: "ouest" for name in west_names}
    bank_by_name.update({name: "est" for name in east_names})

    joined = gpd.sjoin(
        nodes_gdf,
        municipalities_gdf[[name_field, "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined[~joined.index.duplicated(keep="first")]

    banks = {}
    for node_id, municipality in joined[name_field].items():
        bank = bank_by_name.get(municipality)
        if bank is not None:
            banks[node_id] = bank
    return banks


def find_crossing_edges(graph, banks):
    """Retourne les liens (u, v, cle) dont les extremites sont sur des rives opposees."""
    crossings = []
    for u, v, key in graph.edges(keys=True):
        bank_u = banks.get(u)
        bank_v = banks.get(v)
        if bank_u is not None and bank_v is not None and bank_u != bank_v:
            crossings.append((u, v, key))
    return crossings


def crossing_report(graph, crossings):
    """Construit un tableau verifiable des liens traversants avec leurs attributs OSM."""
    rows = []
    for u, v, key in crossings:
        data = graph.get_edge_data(u, v, key) or {}
        rows.append(
            {
                "noeud_ouest_ou_depart": u,
                "noeud_est_ou_arrivee": v,
                "nom": str(data.get("name", "")),
                "type_voie": str(data.get("highway", "")),
                "pont": str(data.get("bridge", "")),
                "longueur_m": round(float(data.get("length", 0.0)), 1),
            }
        )
    return pd.DataFrame(rows)


def remove_crossing_edges(graph, crossings):
    """Retourne une copie du graphe sans les liens traversants (scenario barriere)."""
    cut_graph = graph.copy()
    for u, v, key in crossings:
        if cut_graph.has_edge(u, v, key):
            cut_graph.remove_edge(u, v, key)
    return cut_graph
