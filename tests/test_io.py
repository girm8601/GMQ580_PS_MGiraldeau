# Objectif, verifier qu'un GeoDataFrame en EPSG:4326 est bien ramene a EPSG:2950.

import geopandas as gpd
from shapely.geometry import Point

from src.io import reproject


def test_reproject_to_2950():
    """Toute couche doit etre ramenee au CRS cible EPSG:2950 avant analyse."""
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(-73.19, 45.57)],  # un point pres de Beloeil, en EPSG:4326
        crs="EPSG:4326",
    )
    result = reproject(gdf, "EPSG:2950")
    assert result.crs.to_epsg() == 2950


def test_reproject_preserves_features():
    """La reprojection ne doit ni ajouter ni supprimer d'entites."""
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(-73.19, 45.57), Point(-73.20, 45.56)],
        crs="EPSG:4326",
    )
    result = reproject(gdf, "EPSG:2950")
    assert len(result) == len(gdf)
