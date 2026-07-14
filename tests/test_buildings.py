# Objectif, verifier le filtrage des batiments residentiels, en particulier le
# sort de la valeur generique yes selon l'usage du sol.

import geopandas as gpd
from shapely.geometry import Polygon

from src.extraction.buildings import build_address_label, filter_residential

BUILDINGS_CONFIG = {
    "field": "building",
    "kept_types": ["house", "detached", "yes"],
    "residential_land_use_codes": [100],
    "address_tag": "addr:housenumber",
    "housenumber_field": "addr:housenumber",
    "street_field": "addr:street",
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


def test_clear_types_filtered():
    """Le type house passe et le type commercial est ecarte puis compte."""
    kept, excluded = filter_residential(
        make_buildings(), BUILDINGS_CONFIG, make_residential_zone()
    )
    assert "commercial" in excluded
    assert (kept["building"] == "house").any()


def test_yes_by_land_use():
    """Un batiment yes ne passe que s'il tombe en zone residentielle."""
    kept, excluded = filter_residential(
        make_buildings(), BUILDINGS_CONFIG, make_residential_zone()
    )
    yes_kept = kept[kept["building"] == "yes"]
    assert len(yes_kept) == 1
    assert excluded.get("yes", 0) == 1


def test_yes_without_land_use_layer():
    """Sans couche de sol fournie, le comportement de GMQ210 est conserve."""
    kept, excluded = filter_residential(make_buildings(), BUILDINGS_CONFIG, None)
    assert len(kept[kept["building"] == "yes"]) == 2


def test_build_address_label():
    """L'etiquette d'adresse doit combiner le numero civique et la rue."""
    row = {"addr:housenumber": "123", "addr:street": "rue Principale"}
    assert (
        build_address_label(row, "addr:housenumber", "addr:street")
        == "123 rue Principale"
    )
    assert build_address_label({}, "addr:housenumber", "addr:street") is None
