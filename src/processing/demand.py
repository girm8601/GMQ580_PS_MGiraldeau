"""Demande ponderee par la vulnerabilite, les aines par aire de diffusion.

Le profil du recensement fournit la population totale et les 65 ans et plus
par aire de diffusion. La demande retenue pour l'analyse est le compte des
aines, la population totale sert a l'analyse de sensibilite d'equite.
"""

from __future__ import annotations

import pandas as pd


def extract_population(census_df, vulnerability_config):
    """Extrait la population totale et les aines par aire de diffusion.

    Retourne un tableau avec une ligne par aire de diffusion et les colonnes
    population_totale et aines. Les valeurs non numeriques du recensement,
    comme les valeurs supprimees par confidentialite, deviennent zero.
    """
    join_field = vulnerability_config["champ_jointure_ad"]
    id_field = vulnerability_config["colonne_caracteristique"]
    value_field = vulnerability_config["colonne_valeur"]
    seniors_id = vulnerability_config["caracteristique_id"]
    total_id = vulnerability_config["population_totale_id"]

    subset = census_df[census_df[id_field].isin([seniors_id, total_id])].copy()
    subset[value_field] = pd.to_numeric(subset[value_field], errors="coerce")

    pivoted = subset.pivot_table(
        index=join_field, columns=id_field, values=value_field, aggfunc="first"
    ).reset_index()
    pivoted = pivoted.rename(
        columns={total_id: "population_totale", seniors_id: "aines"}
    )
    for column in ("population_totale", "aines"):
        if column not in pivoted.columns:
            pivoted[column] = 0.0
        pivoted[column] = pivoted[column].fillna(0.0)
    return pivoted[[join_field, "population_totale", "aines"]]


def weight_demand(ad_gdf, population_df, join_field, logger=None):
    """Joint la population aux aires de diffusion et controle le taux de jointure.

    Les aires sans correspondance recoivent une demande nulle plutot que des
    valeurs manquantes, et le taux de jointure est journalise pour reperer
    une cle de jointure defaillante.
    """
    merged = ad_gdf.merge(population_df, on=join_field, how="left")
    matched = merged["population_totale"].notna()
    join_rate = float(matched.mean()) if len(merged) > 0 else 0.0
    if logger is not None:
        logger.info(
            "Jointure du profil sur les AD, %d sur %d aires appariees (%.1f %%)",
            int(matched.sum()),
            len(merged),
            100.0 * join_rate,
        )
    for column in ("population_totale", "aines"):
        merged[column] = merged[column].fillna(0.0)
    return merged, join_rate
