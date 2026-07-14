# Objectif, verifier l'extraction de la population, la ponderation de la demande
# et la repartition des aines sur les residences, sur des donnees synthetiques.

import logging

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.processing.demand import (
    distribute_demand_to_residences,
    extract_population,
    weight_demand,
)

logger = logging.getLogger("test_demand")

# Configuration synthetique identique aux cles de config.yaml.
VULN_CONFIG = {
    "ad_join_field": "IDUGD",
    "characteristic_column": "ID_CARAC",
    "value_column": "VALEUR",
    "characteristic_id": 24,
    "total_population_id": 1,
}


def make_census():
    """Profil synthetique de deux aires avec population totale et aines."""
    return pd.DataFrame(
        {
            "IDUGD": ["A1", "A1", "A2", "A2", "A2"],
            "ID_CARAC": [1, 24, 1, 24, 99],
            "VALEUR": ["1000", "200", "500", "50", "7"],
        }
    )


def test_extract_population():
    """Les bonnes caracteristiques doivent etre extraites et typees."""
    population = extract_population(make_census(), VULN_CONFIG)
    row_a1 = population[population["IDUGD"] == "A1"].iloc[0]
    assert row_a1["population_total"] == 1000.0
    assert row_a1["seniors"] == 200.0


def test_non_numeric_value_becomes_zero():
    """Une valeur supprimee par confidentialite ne doit pas casser l'extraction."""
    census = make_census()
    census.loc[1, "VALEUR"] = ".."
    population = extract_population(census, VULN_CONFIG)
    assert population[population["IDUGD"] == "A1"].iloc[0]["seniors"] == 0.0


def make_ad_gdf():
    """Deux aires de diffusion carrees synthetiques."""
    return gpd.GeoDataFrame(
        {"IDUGD": ["A1", "A3"]},
        geometry=[
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]),
        ],
        crs="EPSG:2950",
    )


def test_join_and_rate():
    """L'aire sans correspondance recoit zero et le taux reflete la jointure."""
    population = extract_population(make_census(), VULN_CONFIG)
    merged, join_rate = weight_demand(make_ad_gdf(), population, "IDUGD", logger)
    assert join_rate == 0.5
    row_a3 = merged[merged["IDUGD"] == "A3"].iloc[0]
    assert row_a3["seniors"] == 0.0
    row_a1 = merged[merged["IDUGD"] == "A1"].iloc[0]
    assert row_a1["seniors"] == 200.0


def test_distribute_demand_to_residences():
    """Les aines d'une aire doivent se repartir egalement sur ses residences."""
    areas = pd.DataFrame(
        {
            "IDUGD": ["A1", "A2"],
            "seniors": [10.0, 4.0],
            "population_total": [100.0, 40.0],
        }
    )
    residences = pd.DataFrame(
        {"residence_id": [0, 1, 2, 3], "IDUGD": ["A1", "A1", "A2", "A2"]}
    )
    out = distribute_demand_to_residences(residences, areas, "IDUGD")
    assert out.loc[out["residence_id"] == 0, "seniors_weight"].iloc[0] == 5.0
    assert out.loc[out["residence_id"] == 2, "seniors_weight"].iloc[0] == 2.0
    assert abs(out["seniors_weight"].sum() - 14.0) < 1e-9
    assert abs(out["population_weight"].sum() - 140.0) < 1e-9
