"""Fonctions d'entree/sortie partagees, lecture, ecriture et reprojection.

Toutes les couches du projet sont ramenees au CRS cible commun defini dans
config.yaml (EPSG:2950, NAD83(CSRS) / MTM zone 8) avant analyse, pour eviter
les jointures spatiales silencieusement fausses. Le CRS n'est pas code en dur
ici, chaque appelant le recoit de la configuration (config_loader.py). Les
coordonnees des tableaux exportes repassent en degres par ce meme module.
"""

import geopandas as gpd


def reproject(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """Reprojette un GeoDataFrame vers le CRS cible.

    Leve une erreur explicite si la couche n'a pas de CRS defini, car une
    reprojection depuis un CRS inconnu produirait un resultat spatialement faux.
    """
    if gdf.crs is None:
        raise ValueError(
            "Le GeoDataFrame n'a pas de CRS defini, reprojection impossible."
        )
    return gdf.to_crs(target_crs)


def latitude_longitude(geometries, geographic_crs, precision):
    """Latitude et longitude en degres d'une serie de points, pour les tableaux exportes.

    geometries est une serie de points dans le CRS cible du projet. Retourne le couple des
    deux series arrondies, dans l'ordre latitude puis longitude.
    """
    points = gpd.GeoSeries(geometries).to_crs(geographic_crs)
    return points.y.round(precision), points.x.round(precision)
