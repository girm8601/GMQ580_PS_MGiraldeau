"""Agregation des points notes en secteurs, les aires de diffusion du levier.

Le levier ne propose pas des points precis mais des secteurs, les aires de diffusion, ce
qui evite la concentration de points et donne des options plus lisibles. Chaque point note,
adresse existante ou terrain a developper, est rattache a son aire de diffusion. On calcule
la cote moyenne de l'aire et sa cote qualitative, puis on garde la meilleure aire de chaque
municipalite, ce qui repartit les recommandations sur tout le territoire. Chaque secteur
porte le polygone de l'aire, pret pour la carte et le tableau.
"""

from __future__ import annotations

import geopandas as gpd

from src.processing.accessibility import overall_quality_label

COLUMNS = [
    "municipality",
    "ad_id",
    "mean_score_percent",
    "n_points",
    "mean_quality",
    "geometry",
]


def _areas_with_municipality(areas, municipalities, join_field, name_field):
    """Rattache chaque aire de diffusion a sa municipalite, par recouvrement maximal.

    Une aire appartient a une seule municipalite. Le recouvrement maximal reste exact meme
    pour une aire a cheval sur la limite de la zone d'etude.
    """
    pieces = gpd.overlay(
        areas[[join_field, "geometry"]],
        municipalities[[name_field, "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    pieces["overlap_area"] = pieces.geometry.area
    largest = pieces.sort_values("overlap_area", ascending=False).drop_duplicates(
        subset=[join_field]
    )
    owners = largest[[join_field, name_field]].rename(
        columns={name_field: "municipality"}
    )
    return areas[[join_field, "geometry"]].merge(owners, on=join_field, how="inner")


def best_sectors(points_scored, areas, municipalities, config, logger=None):
    """Retourne la meilleure aire de diffusion de chaque municipalite.

    points_scored porte une cote sur 100 par point, areas porte la geometrie des aires et
    municipalities leurs limites. On joint chaque point a son aire, on calcule la cote
    moyenne de l'aire, et on garde l'aire la mieux cotee de chaque municipalite. Une ville
    sans point candidat ne produit aucune ligne. Retourne les secteurs tries par cote
    moyenne decroissante.
    """
    join_field = config["vulnerability"]["ad_join_field"]
    name_field = config["study_area"]["municipality_name_field"]
    ratios = config["overall_quality_ratios"]

    owned = _areas_with_municipality(areas, municipalities, join_field, name_field)
    joined = gpd.sjoin(
        points_scored[["score_percent", "geometry"]],
        owned,
        how="inner",
        predicate="within",
    )
    if len(joined) == 0:
        return gpd.GeoDataFrame(columns=COLUMNS, geometry="geometry", crs=areas.crs)

    grouped = (
        joined.groupby(["municipality", join_field])["score_percent"]
        .agg(mean_score_percent="mean", n_points="count")
        .reset_index()
    )
    grouped["mean_score_percent"] = grouped["mean_score_percent"].round(1)
    best = (
        grouped.sort_values("mean_score_percent", ascending=False)
        .drop_duplicates(subset=["municipality"])
        .reset_index(drop=True)
    )
    best["mean_quality"] = best["mean_score_percent"].map(
        lambda p: overall_quality_label(p / 100.0, ratios)
    )

    sectors = owned.merge(best, on=["municipality", join_field], how="inner")
    sectors = sectors.rename(columns={join_field: "ad_id"}).sort_values(
        "mean_score_percent", ascending=False
    )
    if logger is not None:
        logger.info(
            "Secteurs retenus, %d sur %d aires notees", len(sectors), len(grouped)
        )
    return gpd.GeoDataFrame(
        sectors[COLUMNS], geometry="geometry", crs=areas.crs
    ).reset_index(drop=True)
