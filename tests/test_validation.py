# Objectif, verifier les regles d'audit et la detection des ponts sur des
# donnees synthetiques, jamais sur les donnees reelles du projet.

import logging

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import Point, Polygon

from src.validation.audit import (
    AuditError,
    check_crs,
    check_duplicates,
    check_empty_geometries,
    check_required_fields,
    check_valid_geometries,
    run_audit,
)
from src.validation.bridges import (
    find_crossing_edges,
    remove_crossing_edges,
    river_polygon,
    unclassified_edges,
)

logger = logging.getLogger("test_audit")


def make_gdf(crs="EPSG:2950"):
    """Petit GeoDataFrame synthetique valide pour les tests."""
    return gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs=crs,
    )


def test_expected_crs_detected():
    """Un CRS conforme passe et un CRS different echoue."""
    gdf = make_gdf()
    assert check_crs(gdf, "EPSG:2950")[0] is True
    assert check_crs(gdf, "EPSG:4326")[0] is False


def test_missing_crs_detected():
    """Une couche sans CRS declare doit echouer."""
    gdf = make_gdf().set_crs(None, allow_override=True)
    assert check_crs(gdf, "EPSG:2950")[0] is False


def test_invalid_geometry_detected():
    """Un polygone papillon auto intersectant doit etre signale."""
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[bowtie], crs="EPSG:2950")
    assert check_valid_geometries(gdf)[0] is False


def test_empty_geometry_detected():
    """Une geometrie absente doit etre signalee."""
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), None], crs="EPSG:2950"
    )
    assert check_empty_geometries(gdf)[0] is False


def test_duplicates_detected():
    """Deux entites identiques doivent etre signalees."""
    gdf = gpd.GeoDataFrame(
        {"id": [1, 1]},
        geometry=[Point(0, 0), Point(0, 0)],
        crs="EPSG:2950",
    )
    assert check_duplicates(gdf)[0] is False


def test_required_fields_detected():
    """Un champ manquant doit etre signale."""
    gdf = make_gdf()
    assert check_required_fields(gdf, ["id"])[0] is True
    assert check_required_fields(gdf, ["absent"])[0] is False


def test_audit_blocks_pipeline(tmp_path):
    """Une couche au mauvais CRS doit bloquer l'audit avec une erreur claire."""
    entries = [{"gdf": make_gdf(crs="EPSG:4326"), "name": "test", "crs": "EPSG:2950"}]
    report_path = tmp_path / "audit_report.csv"
    with pytest.raises(AuditError):
        run_audit(entries, str(report_path), logger)
    assert report_path.exists()


def test_audit_passes_and_writes_report(tmp_path):
    """Une couche conforme doit passer l'audit et produire le rapport CSV."""
    entries = [{"gdf": make_gdf(), "name": "test", "crs": "EPSG:2950"}]
    report_path = tmp_path / "audit_report.csv"
    report = run_audit(entries, str(report_path), logger)
    assert (report["status"] == "ok").all()
    assert report_path.exists()


def make_two_bank_graph():
    """Mini graphe avec deux noeuds par rive et un seul lien qui traverse."""
    graph = nx.MultiGraph()
    graph.add_edge(1, 2, length=100.0)
    graph.add_edge(3, 4, length=100.0)
    graph.add_edge(2, 3, length=300.0, bridge="yes")
    banks = {1: "west", 2: "west", 3: "east", 4: "east"}
    return graph, banks


def test_crossing_edges_detected():
    """Le seul lien entre les deux rives doit etre identifie."""
    graph, banks = make_two_bank_graph()
    crossings = find_crossing_edges(graph, banks)
    assert len(crossings) == 1
    assert (2, 3) in [(u, v) for u, v, k in crossings]


def test_removing_crossing_edges_cuts_banks():
    """Sans les liens traversants, plus aucun chemin ne relie les deux rives."""
    graph, banks = make_two_bank_graph()
    crossings = find_crossing_edges(graph, banks)
    cut_graph = remove_crossing_edges(graph, crossings)
    assert not nx.has_path(cut_graph, 1, 4)


def make_two_bank_municipalities():
    """Deux villes separees par une bande d'eau, plus un etang dans une seule ville."""
    municipalities = gpd.GeoDataFrame(
        {"MUS_NM_MUN": ["Ouest", "Est"]},
        geometry=[
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
            Polygon([(10, 0), (20, 0), (20, 10), (10, 10)]),
        ],
        crs="EPSG:2950",
    )
    water = gpd.GeoDataFrame(
        {"name": ["Riviere", "Etang"]},
        geometry=[
            # La riviere longe la limite et touche donc les deux villes.
            Polygon([(9, 0), (11, 0), (11, 10), (9, 10)]),
            # L'etang tient entierement dans la ville de l'ouest.
            Polygon([(2, 2), (4, 2), (4, 4), (2, 4)]),
        ],
        crs="EPSG:2950",
    )
    return municipalities, water


def test_river_is_the_only_water_touching_both_banks():
    """L'etang ne doit pas compter comme barriere, seule la riviere separe les rives.

    Sans ce tri, le controle croise des ponts comparerait les liens du pont a tous les
    liens qui franchissent n'importe quelle eau, y compris une passerelle sur un etang.
    """
    municipalities, water = make_two_bank_municipalities()
    river = river_polygon(water, municipalities, ["Ouest"], ["Est"], "MUS_NM_MUN")
    assert river is not None
    # L'aire retenue est celle de la riviere seule, l'etang est ecarte.
    assert river.area == 20.0


def test_no_river_without_water_layer():
    """Sans couche d'eau, le controle croise ne peut pas se faire et le dit."""
    municipalities, _ = make_two_bank_municipalities()
    assert river_polygon(None, municipalities, ["Ouest"], ["Est"], "MUS_NM_MUN") is None


def test_no_river_when_no_water_separates_the_banks():
    """Une eau contenue dans une seule ville ne fait pas barriere entre les rives."""
    municipalities, water = make_two_bank_municipalities()
    etang = water[water["name"] == "Etang"]
    assert (
        river_polygon(etang, municipalities, ["Ouest"], ["Est"], "MUS_NM_MUN") is None
    )


def test_only_edges_without_a_known_bank_are_suspect():
    """Un pont detecte et un sentier de berge sont normaux, un bout sans rive ne l'est pas.

    C'est le seul cas ou un pont pourrait echapper a la detection, par exemple si un noeud
    est pose au milieu du pont, hors de toute limite municipale.
    """
    banks = {1: "west", 2: "east", 3: "east", 4: "east"}
    edges = [
        (1, 2, 0),  # un pont, les deux rives sont connues et opposees
        (3, 4, 0),  # un sentier de berge, les deux bouts sur la rive est
        (2, 99, 0),  # un bout hors des municipalites connues, a verifier
    ]
    assert unclassified_edges(edges, banks) == [(2, 99, 0)]


def test_no_suspect_edge_when_every_bank_is_known():
    """Si toutes les extremites ont une rive, rien n'est signale."""
    banks = {1: "west", 2: "east"}
    assert unclassified_edges([(1, 2, 0)], banks) == []
