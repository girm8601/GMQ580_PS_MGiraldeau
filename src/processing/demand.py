"""Demande ponderee par la vulnerabilite, les aines par aire de diffusion.

Le profil du recensement fournit la population totale et les 65 ans et plus par
aire de diffusion. Le compte d'aines et le compte du reste, population totale moins
aines, sont repartis egalement sur les residences de chaque aire. La population totale
sert seulement a l'effet de barriere.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def extract_population(census_df, vulnerability_config):
    """Extrait la population totale et les aines par aire de diffusion.

    Retourne un tableau avec une ligne par aire de diffusion et les colonnes
    population_total et seniors. Les valeurs non numeriques du recensement,
    comme les valeurs supprimees par confidentialite, deviennent zero.
    """
    join_field = vulnerability_config["ad_join_field"]
    id_field = vulnerability_config["characteristic_column"]
    value_field = vulnerability_config["value_column"]
    seniors_id = vulnerability_config["characteristic_id"]
    total_id = vulnerability_config["total_population_id"]

    subset = census_df[census_df[id_field].isin([seniors_id, total_id])].copy()
    subset[value_field] = pd.to_numeric(subset[value_field], errors="coerce")

    pivoted = subset.pivot_table(
        index=join_field, columns=id_field, values=value_field, aggfunc="first"
    ).reset_index()
    pivoted = pivoted.rename(
        columns={total_id: "population_total", seniors_id: "seniors"}
    )
    for column in ("population_total", "seniors"):
        if column not in pivoted.columns:
            pivoted[column] = 0.0
        pivoted[column] = pivoted[column].fillna(0.0)
    return pivoted[[join_field, "population_total", "seniors"]]


def weight_demand(ad_gdf, population_df, join_field, logger=None):
    """Joint la population aux aires de diffusion et controle le taux de jointure.

    Les aires sans correspondance recoivent une demande nulle plutot que des
    valeurs manquantes, et le taux de jointure est journalise pour reperer une
    cle de jointure defaillante.
    """
    merged = ad_gdf.merge(population_df, on=join_field, how="left")
    matched = merged["population_total"].notna()
    join_rate = float(matched.mean()) if len(merged) > 0 else 0.0
    if logger is not None:
        logger.info(
            "Jointure du profil sur les AD, %d sur %d aires appariees (%.1f %%)",
            int(matched.sum()),
            len(merged),
            100.0 * join_rate,
        )
    for column in ("population_total", "seniors"):
        merged[column] = merged[column].fillna(0.0)
    return merged, join_rate


def distribute_demand_to_residences(residences, areas, join_field):
    """Repartit la population de chaque aire sur ses residences.

    Le compte d'aines et la population totale d'une aire sont divises par le nombre de
    residences de cette aire. Chaque residence recoit un poids d'aines, un poids de
    population totale et un poids du reste, la population moins les aines. Les residences
    sans aire recoivent un poids nul. Retourne le GeoDataFrame des residences avec les
    colonnes de poids.
    """
    residences = residences.copy()
    counts = residences.groupby(join_field)["residence_id"].transform("count")
    seniors_by_area = residences[join_field].map(areas.set_index(join_field)["seniors"])
    population_by_area = residences[join_field].map(
        areas.set_index(join_field)["population_total"]
    )
    residences["seniors_weight"] = (seniors_by_area / counts).fillna(0.0)
    residences["population_weight"] = (population_by_area / counts).fillna(0.0)
    residences["rest_weight"] = (
        residences["population_weight"] - residences["seniors_weight"]
    ).clip(lower=0.0)
    return residences


def prepare_demand(layers, config, logger):
    """Pondere la demande et repartit les aines sur les residences de chaque AD."""
    join_field = config["vulnerability"]["ad_join_field"]
    population = extract_population(layers["census"], config["vulnerability"])
    areas, _ = weight_demand(layers["areas"], population, join_field, logger)

    zone_union = layers["study_zone"].union_all()
    residences = layers["residences"]
    residences = residences[residences.within(zone_union)].copy()
    logger.info("Residences dans la zone d'etude, %d", len(residences))

    joined = gpd.sjoin(
        residences, areas[[join_field, "geometry"]], how="left", predicate="within"
    ).drop(columns="index_right")
    without_area = int(joined[join_field].isna().sum())
    if without_area > 0:
        # Une residence posee juste sur la limite de deux aires ne tombe dans aucune.
        # Sans cette ligne, le compte final ne concorderait plus avec le compte precedent.
        logger.info(
            "Residences ecartees faute d'aire de diffusion, %d sur %d",
            without_area,
            len(joined),
        )
    joined = joined[joined[join_field].notna()].copy()
    joined = distribute_demand_to_residences(joined, areas, join_field)
    return areas, joined.reset_index(drop=True)
