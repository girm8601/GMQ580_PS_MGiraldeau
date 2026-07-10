# Objectif, verifier l'extraction de la population et la ponderation de la
# demande par aire de diffusion sur des donnees synthetiques.

import logging

import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon

from src.processing.demand import extract_population, weight_demand

logger = logging.getLogger("test_demand")

# Configuration synthetique identique aux cles de config.yaml.
VULN_CONFIG = {
    "champ_jointure_ad": "IDUGD",
    "colonne_caracteristique": "ID_CARAC",
    "colonne_valeur": "VALEUR",
    "caracteristique_id": 24,
    "population_totale_id": 1,
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


def test_extraction_population():
    """Les bonnes caracteristiques doivent etre extraites et typees."""
    population = extract_population(make_census(), VULN_CONFIG)
    row_a1 = population[population["IDUGD"] == "A1"].iloc[0]
    assert row_a1["population_totale"] == 1000.0
    assert row_a1["aines"] == 200.0


def test_valeur_non_numerique_devient_zero():
    """Une valeur supprimee par confidentialite ne doit pas casser l'extraction."""
    census = make_census()
    census.loc[1, "VALEUR"] = ".."
    population = extract_population(census, VULN_CONFIG)
    assert population[population["IDUGD"] == "A1"].iloc[0]["aines"] == 0.0


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


def test_jointure_et_taux():
    """L'aire sans correspondance recoit zero et le taux reflete la jointure."""
    population = extract_population(make_census(), VULN_CONFIG)
    merged, join_rate = weight_demand(make_ad_gdf(), population, "IDUGD", logger)
    assert join_rate == 0.5
    row_a3 = merged[merged["IDUGD"] == "A3"].iloc[0]
    assert row_a3["aines"] == 0.0
    row_a1 = merged[merged["IDUGD"] == "A1"].iloc[0]
    assert row_a1["aines"] == 200.0
