"""Definition et filtrage des sites candidats pour de nouveaux services.

Les candidats sont les polygones d'utilisation du sol de la zone d'etude
dont le code n'est pas exclu par la configuration, representes par un point
interieur. Des points d'ancrage supplementaires peuvent s'ajouter par le
parametre optionnel, le scenario actuel a pied n'en utilise aucun.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def filter_candidate_polygons(land_use_gdf, config, demand_zone):
    """Retient les polygones batissables de la zone de demande."""
    code_field = config["utilisation_sol"]["champ_code"]
    excluded_codes = config["utilisation_sol"]["codes_exclus"]
    codes = pd.to_numeric(land_use_gdf[code_field], errors="coerce")
    kept = land_use_gdf[codes.notna() & ~codes.isin(excluded_codes)].copy()
    zone_union = demand_zone.union_all()
    kept = kept[kept.geometry.representative_point().within(zone_union)]
    return kept


def build_candidate_sites(
    land_use_gdf, config, demand_zone, stations_gdf=None, logger=None
):
    """Construit la couche des sites candidats en points.

    Chaque polygone retenu devient un point interieur. Les gares s'ajoutent
    comme candidats d'ancrage. Retourne un GeoDataFrame avec un identifiant
    de site, le code d'usage du sol et la provenance.
    """
    code_field = config["utilisation_sol"]["champ_code"]
    polygons = filter_candidate_polygons(land_use_gdf, config, demand_zone)

    candidates = gpd.GeoDataFrame(
        {
            "code_sol": pd.to_numeric(polygons[code_field], errors="coerce").values,
            "provenance": "utilisation_sol",
        },
        geometry=polygons.geometry.representative_point().values,
        crs=land_use_gdf.crs,
    )

    if stations_gdf is not None and len(stations_gdf) > 0:
        stations = gpd.GeoDataFrame(
            {
                "code_sol": [None] * len(stations_gdf),
                "provenance": "gare",
            },
            geometry=stations_gdf.geometry.values,
            crs=stations_gdf.crs,
        )
        candidates = gpd.GeoDataFrame(
            pd.concat([candidates, stations], ignore_index=True), crs=candidates.crs
        )

    candidates = candidates.reset_index(drop=True)
    candidates["site_id"] = candidates.index
    if logger is not None:
        logger.info("Sites candidats construits, %d sites", len(candidates))
    return candidates
