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
from src.validation.bridges import find_crossing_edges, remove_crossing_edges

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
