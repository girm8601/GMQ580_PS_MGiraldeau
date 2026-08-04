# Objectif, verifier les tableaux de resultats, ecart aines reste, effet d'ajout, effet de
# barriere par groupe et secteurs, sur des donnees synthetiques aux reponses connues.

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.results.metrics import (
    barrier_effect_table,
    population_comparison_table,
    sector_table,
    service_addition_effect_table,
)

COMPARISON_CONFIG = {
    "optimization": {
        "coverage_threshold_seniors_m": 800,
        "coverage_threshold_rest_m": 1000,
    }
}


def make_summary():
    """Un service, les quatre plans du sommaire de couverture."""
    return pd.DataFrame(
        [
            {
                "population": "seniors",
                "mode": "marche",
                "service_type": "a",
                "threshold_m": 800,
                "covered_percent": 50.0,
            },
            {
                "population": "rest",
                "mode": "marche",
                "service_type": "a",
                "threshold_m": 1000,
                "covered_percent": 80.0,
            },
            {
                "population": "seniors",
                "mode": "marche_transport",
                "service_type": "a",
                "threshold_m": 800,
                "covered_percent": 60.0,
            },
            {
                "population": "rest",
                "mode": "marche_transport",
                "service_type": "a",
                "threshold_m": 1000,
                "covered_percent": 90.0,
            },
        ]
    )


def test_population_comparison_signed_gap():
    """L'ecart doit soustraire le reste des aines, a la marche et au transport."""
    table = population_comparison_table(make_summary(), COMPARISON_CONFIG)
    row = table.iloc[0]
    assert row["diff_walk_percent"] == -30.0
    assert row["diff_transit_percent"] == -30.0


def test_service_addition_effect_keeps_coordinates():
    """La ligne de depart est ecartee et le site retient sa position en degres."""
    gains = pd.DataFrame(
        [
            {
                "n_services": 0,
                "group": "seniors",
                "threshold_m": 800,
                "added_type": "",
                "site_id": "",
                "latitude": "",
                "longitude": "",
                "weighted_covered_percent": 20.0,
            },
            {
                "n_services": 1,
                "group": "seniors",
                "threshold_m": 800,
                "added_type": "a",
                "site_id": 3,
                "latitude": 45.567,
                "longitude": -73.201,
                "weighted_covered_percent": 25.0,
            },
        ]
    )
    effect = service_addition_effect_table(gains)
    assert len(effect) == 1
    assert effect.iloc[0]["added_type"] == "a"
    assert effect.iloc[0]["latitude"] == 45.567
    # Le gain se mesure depuis la ligne de depart, ecartee du tableau mais gardee en
    # reference. Sans cette colonne le lecteur ne verrait qu'un niveau, jamais un gain.
    assert effect.iloc[0]["gain_percent"] == 5.0
    assert list(effect.columns) == [
        "group",
        "n_services",
        "added_type",
        "site_id",
        "latitude",
        "longitude",
        "threshold_m",
        "weighted_covered_percent",
        "gain_percent",
    ]


def test_barrier_effect_persons_and_percent():
    """L'effet de barriere est la difference avec et sans pont, en personnes et en part."""
    rows = [
        {
            "group": "seniors",
            "service_type": "a",
            "threshold_m": 800,
            "covered_with_bridges_persons": 100.0,
            "covered_without_bridges_persons": 80.0,
            "group_total_persons": 200.0,
        },
    ]
    table = barrier_effect_table(rows)
    assert table.iloc[0]["barrier_effect_persons"] == 20.0
    assert table.iloc[0]["barrier_effect_percent"] == 10.0


def _square(x, y):
    """Petit carre synthetique place en x, y."""
    return Polygon([(x, y), (x + 2, y), (x + 2, y + 2), (x, y + 2)])


def _sector_layer(ad_id, municipality, score, quality, n_points, x, y):
    """Un secteur synthetique, un carre de deux metres de cote."""
    return gpd.GeoDataFrame(
        {
            "municipality": [municipality],
            "ad_id": [ad_id],
            "mean_score_percent": [score],
            "mean_quality": [quality],
            "n_points": [n_points],
        },
        geometry=[_square(x, y)],
        crs="EPSG:2950",
    )


def test_sector_table_separates_types():
    """Le tableau garde les secteurs d'adresses et de sites separes, avec leur ville."""
    addresses = _sector_layer("A1", "Beloeil", 90.0, "Excellent", 5, 0, 0)
    sites = _sector_layer("A2", "Otterburn Park", 70.0, "Bien", 3, 10, 10)
    table = sector_table(addresses, sites, "EPSG:4326", 6)
    assert list(table["type"]) == ["adresse existante", "site à implanter"]
    assert list(table["municipality"]) == ["Beloeil", "Otterburn Park"]
    assert table.iloc[0]["ad_id"] == "A1"
    assert list(table.columns) == [
        "type",
        "municipality",
        "ad_id",
        "mean_score_percent",
        "mean_quality",
        "n_points",
        "latitude",
        "longitude",
    ]
