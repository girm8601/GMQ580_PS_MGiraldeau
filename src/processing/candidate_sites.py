"""Definition des sites candidats a partir d'une couche d'usage du sol OpenStreetMap.

Un site candidat est le point representatif d'un terrain OpenStreetMap d'un usage donne,
terrains commerciaux pour la validation d'ajout de services, terrains brownfield pour le
levier de logement aine. Chaque terrain retenu devient un point interieur, verifiable
dans QGIS. Le filtrage de proximite au reseau se fait ensuite dans le pipeline, ou le
graphe est disponible.
"""

from __future__ import annotations

import geopandas as gpd


def build_candidate_sites(landuse_gdf, demand_zone, source, logger=None):
    """Construit la couche des sites candidats en points a partir d'un usage du sol.

    landuse_gdf regroupe les polygones d'un usage OpenStreetMap deja ramenes au CRS
    cible. Chaque terrain dont le point representatif tombe dans la zone de demande
    devient un point candidat. source nomme la provenance affichee, commercial ou
    brownfield. Retourne un GeoDataFrame avec un identifiant de site et la provenance.
    """
    points = landuse_gdf.geometry.representative_point()
    zone_union = demand_zone.union_all()
    kept = points[points.within(zone_union)]

    candidates = gpd.GeoDataFrame(
        {"source": [source] * len(kept)},
        geometry=list(kept.values),
        crs=landuse_gdf.crs,
    )
    candidates = candidates.reset_index(drop=True)
    candidates["site_id"] = candidates.index
    if logger is not None:
        logger.info("Sites candidats %s construits, %d sites", source, len(candidates))
    return candidates
