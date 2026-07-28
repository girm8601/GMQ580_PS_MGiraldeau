# Objectif, verifier la selection de la meilleure aire de diffusion de chaque municipalite,
# sur des donnees synthetiques aux reponses connues.

import geopandas as gpd
from shapely.geometry import Point, Polygon

from src.processing.sectors import best_sectors

CONFIG = {
    "vulnerability": {"ad_join_field": "IDUGD"},
    "study_area": {"municipality_name_field": "MUS_NM_MUN"},
    "overall_quality_ratios": [
        [0.80, "Excellent"],
        [0.60, "Très bien"],
        [0.40, "Bien"],
        [0.20, "Acceptable"],
        [0.00, "Insuffisant"],
    ],
}


def rectangle(x, y, width, height):
    """Petit rectangle synthetique dont le coin bas gauche est en x, y."""
    return Polygon([(x, y), (x + width, y), (x + width, y + height), (x, y + height)])


def make_municipalities():
    """Deux villes voisines, l'ouest de 0 a 30 et l'est de 30 a 60."""
    return gpd.GeoDataFrame(
        {"MUS_NM_MUN": ["Ouest", "Est"]},
        geometry=[rectangle(0, 0, 30, 20), rectangle(30, 0, 30, 20)],
        crs="EPSG:2950",
    )


def make_areas():
    """Deux aires par ville, la derniere deborde a l'est mais reste surtout a l'ouest."""
    return gpd.GeoDataFrame(
        {"IDUGD": ["O1", "O2", "E1", "E2"]},
        geometry=[
            rectangle(0, 0, 10, 20),
            rectangle(10, 0, 10, 20),
            rectangle(35, 0, 10, 20),
            rectangle(45, 0, 10, 20),
        ],
        crs="EPSG:2950",
    )


def make_points():
    """Points notes, O2 est la meilleure aire de l'ouest et E1 celle de l'est."""
    return gpd.GeoDataFrame(
        {"score_percent": [40.0, 90.0, 70.0, 75.0, 30.0]},
        geometry=[
            Point(5, 5),
            Point(12, 5),
            Point(16, 5),
            Point(38, 5),
            Point(48, 5),
        ],
        crs="EPSG:2950",
    )


def test_best_sectors_keeps_one_area_per_municipality():
    """Chaque ville donne une seule aire, la mieux cotee, triee par cote decroissante."""
    sectors = best_sectors(make_points(), make_areas(), make_municipalities(), CONFIG)
    assert list(sectors["ad_id"]) == ["O2", "E1"]
    assert list(sectors["municipality"]) == ["Ouest", "Est"]
    assert sectors.iloc[0]["mean_score_percent"] == 80.0
    assert sectors.iloc[0]["n_points"] == 2
    assert sectors.iloc[0]["mean_quality"] == "Excellent"


def test_best_sectors_skips_municipality_without_point():
    """Une ville sans point candidat ne produit aucune ligne."""
    points = gpd.GeoDataFrame(
        {"score_percent": [90.0]}, geometry=[Point(5, 5)], crs="EPSG:2950"
    )
    sectors = best_sectors(points, make_areas(), make_municipalities(), CONFIG)
    assert list(sectors["municipality"]) == ["Ouest"]


def test_best_sectors_returns_empty_without_point():
    """Aucun point dans une aire donne un resultat vide et non une erreur."""
    points = gpd.GeoDataFrame(
        {"score_percent": [90.0]}, geometry=[Point(500, 500)], crs="EPSG:2950"
    )
    sectors = best_sectors(points, make_areas(), make_municipalities(), CONFIG)
    assert len(sectors) == 0
