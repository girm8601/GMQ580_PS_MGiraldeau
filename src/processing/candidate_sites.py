"""Definition et filtrage des sites candidats pour de nouveaux services.

Un site candidat doit etre un vrai terrain commercial. Les terrains commerciaux de
la CMM (code 200) sont croises avec les polygones OpenStreetMap landuse=commercial,
ce qui ecarte les erreurs de classement de la CMM situees en zone non commerciale.
Chaque terrain retenu devient un point interieur, verifiable dans QGIS. Le filtrage
de proximite au reseau se fait ensuite dans le pipeline, ou le graphe est disponible.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def filter_candidate_polygons(land_use_gdf, config, demand_zone):
    """Retient les terrains commerciaux de la CMM dans la zone de demande."""
    code_field = config["land_use"]["code_field"]
    candidate_codes = config["land_use"]["candidate_codes"]
    codes = pd.to_numeric(land_use_gdf[code_field], errors="coerce")
    kept = land_use_gdf[codes.isin(candidate_codes)].copy()
    zone_union = demand_zone.union_all()
    kept = kept[kept.geometry.representative_point().within(zone_union)]
    return kept


def build_candidate_sites(
    land_use_gdf, config, demand_zone, commercial_gdf=None, logger=None
):
    """Construit la couche des sites candidats en points.

    Les terrains commerciaux de la CMM sont d'abord retenus, puis croises avec les
    polygones OpenStreetMap landuse=commercial quand cette couche est disponible.
    Chaque terrain retenu devient un point interieur. Retourne un GeoDataFrame avec un
    identifiant de site, la provenance et le code d'usage du sol.
    """
    code_field = config["land_use"]["code_field"]
    cmm = filter_candidate_polygons(land_use_gdf, config, demand_zone)

    if commercial_gdf is not None and len(commercial_gdf) > 0:
        commercial_union = commercial_gdf.union_all()
        inside_commercial = cmm.geometry.representative_point().within(commercial_union)
        kept = cmm[inside_commercial].copy()
        if logger is not None:
            logger.info(
                "Terrains CMM commerciaux croises avec OSM, %d sur %d retenus",
                len(kept),
                len(cmm),
            )
    else:
        kept = cmm
        if logger is not None:
            logger.warning(
                "Couche OSM commerciale absente, croisement saute, %d terrains CMM",
                len(kept),
            )

    candidates = gpd.GeoDataFrame(
        {
            "land_use_code": pd.to_numeric(kept[code_field], errors="coerce").values,
            "source": "commercial",
        },
        geometry=kept.geometry.representative_point().values,
        crs=land_use_gdf.crs,
    )
    candidates = candidates.reset_index(drop=True)
    candidates["site_id"] = candidates.index
    if logger is not None:
        logger.info("Sites candidats construits, %d sites", len(candidates))
    return candidates
