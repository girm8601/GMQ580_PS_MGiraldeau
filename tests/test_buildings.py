# Objectif, verifier le filtrage des batiments residentiels, en particulier
# le sort de la valeur generique yes selon l'usage du sol.

import geopandas as gpd
from shapely.geometry import Polygon

from src.extraction.buildings import filter_residential

BUILDINGS_CONFIG = {
    "champ": "building",
    "types_retenus": ["house", "detached", "yes"],
    "codes_sol_residentiels": [100],
    "tag_adresses": "addr:housenumber",
}


def square(x, y, size=1.0):
    """Petit carre synthetique place en x, y."""
    return Polygon([(x, y), (x + size, y), (x + size, y + size), (x, y + size)])


def make_buildings():
    """Quatre batiments, deux types clairs, un yes dedans et un yes dehors."""
    return gpd.GeoDataFrame(
        {"building": ["house", "commercial", "yes", "yes"]},
        geometry=[square(0, 0), square(2, 0), square(4, 0), square(6, 0)],
        crs="EPSG:2950",
    )


def make_residential_zone():
    """Zone residentielle qui couvre seulement le premier batiment yes."""
    return gpd.GeoDataFrame(
        {"UTIL_SOL": [100]}, geometry=[square(3.5, -1, 3.0)], crs="EPSG:2950"
    )


def test_types_clairs_filtres():
    """Le type house passe et le type commercial est ecarte puis compte."""
    kept, excluded = filter_residential(
        make_buildings(), BUILDINGS_CONFIG, make_residential_zone()
    )
    assert "commercial" in excluded
    assert (kept["building"] == "house").any()


def test_yes_selon_usage_du_sol():
    """Un batiment yes ne passe que s'il tombe en zone residentielle."""
    kept, excluded = filter_residential(
        make_buildings(), BUILDINGS_CONFIG, make_residential_zone()
    )
    yes_kept = kept[kept["building"] == "yes"]
    assert len(yes_kept) == 1
    assert excluded.get("yes", 0) == 1


def test_yes_sans_couche_de_sol():
    """Sans couche de sol fournie, le comportement de GMQ210 est conserve."""
    kept, excluded = filter_residential(make_buildings(), BUILDINGS_CONFIG, None)
    assert len(kept[kept["building"] == "yes"]) == 2
