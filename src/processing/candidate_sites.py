"""Sites candidats issus d'une couche d'usage du sol OpenStreetMap.

Un site candidat est le point representatif d'un terrain OpenStreetMap d'un usage donne,
les terrains commerciaux pour la validation d'ajout de services, les terrains a developper
pour le levier de logement aine. Chaque terrain retenu devient un point interieur,
verifiable dans QGIS.

Un site trop loin du reseau pietonnier est ecarte, on n'y marcherait pas. Les sites qui
tombent sur le meme noeud du graphe sont dedoublonnes, ils donneraient les memes distances.
Les deux usages du projet passent par prepare_candidates.
"""

from __future__ import annotations

import geopandas as gpd

from src.processing.graph import snap_points


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


def filter_candidates_near_road(candidates, graph, config, logger):
    """Ecarte les sites candidats trop loin du reseau pietonnier.

    L'ecart d'accrochage est conserve, il compte dans toute distance mesuree depuis le site.
    """
    candidates = candidates.copy()
    candidates["node"], candidates["snap_m"] = snap_points(graph, candidates)
    max_distance = config["optimization"]["site_road_max_distance_m"]
    kept = candidates[candidates["snap_m"] <= max_distance].copy()
    if logger is not None:
        logger.info(
            "Sites candidats pres du reseau, %d sur %d retenus",
            len(kept),
            len(candidates),
        )
    return kept.reset_index(drop=True)


def prepare_candidates(landuse_gdf, source, graph, study_zone, config, logger):
    """Points candidats d'un usage du sol, filtres pres du reseau et regroupes par noeud."""
    candidates = build_candidate_sites(landuse_gdf, study_zone, source, logger)
    candidates = filter_candidates_near_road(candidates, graph, config, logger)
    # Deux sites sur le meme noeud avec le meme ecart donneraient les memes distances.
    candidates = candidates.drop_duplicates(subset=["node", "snap_m"]).reset_index(
        drop=True
    )
    candidates["site_id"] = candidates.index
    return candidates
