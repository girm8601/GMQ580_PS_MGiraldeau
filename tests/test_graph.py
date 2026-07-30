# Objectif, verifier les distances de plus court chemin sur un mini graphe
# connu, ou les bonnes reponses se calculent a la main.

import networkx as nx

from src.processing.graph import distances_from_sources


def make_line_graph():
    """Graphe en ligne 1 a 4 avec des longueurs connues, 100, 200, 300."""
    graph = nx.Graph()
    graph.add_edge(1, 2, length=100.0)
    graph.add_edge(2, 3, length=200.0)
    graph.add_edge(3, 4, length=300.0)
    return graph


def test_multi_source_distances():
    """Chaque noeud doit recevoir la distance vers la source la plus proche."""
    graph = make_line_graph()
    distances = distances_from_sources(graph, [1, 4])
    assert distances[1] == 0.0
    assert distances[2] == 100.0
    assert distances[3] == 300.0
    assert distances[4] == 0.0


def test_cutoff_limits_reach():
    """Au dela du cutoff, les noeuds ne doivent pas apparaitre."""
    graph = make_line_graph()
    distances = distances_from_sources(graph, [1], cutoff=250.0)
    assert 3 not in distances
    assert distances[2] == 100.0


def test_empty_sources():
    """Une liste de sources vide retourne un dictionnaire vide."""
    graph = make_line_graph()
    assert distances_from_sources(graph, []) == {}
