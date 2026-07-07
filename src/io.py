"""Fonctions d'entree/sortie partagees : lecture, ecriture et reprojection.

Toutes les couches du projet sont ramenees au CRS cible commun (EPSG:2950,
NAD83(CSRS) / MTM zone 8) avant analyse, pour eviter les jointures spatiales
silencieusement fausses.
"""

import geopandas as gpd

CRS_CIBLE = "EPSG:2950"


def reproject(gdf: gpd.GeoDataFrame, crs_cible: str = CRS_CIBLE) -> gpd.GeoDataFrame:
    """Reprojette un GeoDataFrame vers le CRS cible.

    Leve une erreur explicite si la couche n'a pas de CRS defini, car une
    reprojection depuis un CRS inconnu produirait un resultat spatialement faux.
    """
    if gdf.crs is None:
        raise ValueError("Le GeoDataFrame n'a pas de CRS defini : reprojection impossible.")
    return gdf.to_crs(crs_cible)