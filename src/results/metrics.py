"""Resultats chiffres du projet, tableaux exportes en CSV.

Ce module ne calcule rien de spatial, il met en forme et exporte les resultats produits
par les modules d'analyse, pour le rapport et la presentation. Les colonnes portent leur
unite, distances en metres avec le suffixe _m, parts en pourcentage avec _percent, comptes
de personnes avec _persons. Les positions sont donnees en latitude et longitude, en degres
decimaux, directement utilisables dans un outil de cartographie.
"""

from __future__ import annotations

import os

import pandas as pd

from src.io import latitude_longitude


def export_table(df, path, logger=None):
    """Ecrit un tableau CSV en creant le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    if logger is not None:
        logger.info("Tableau exporte, %s, %d ligne(s)", path, len(df))


def barrier_effect_table(rows):
    """Effet de barriere par groupe et par service, avec et sans le pont pietonnier.

    Chaque ligne d'entree donne le groupe, le type de service, le seuil, la demande
    couverte avec et sans les ponts et la demande totale du groupe. Retourne le tableau
    avec l'effet de barriere en personnes et en part du groupe.
    """
    table = pd.DataFrame(rows)
    table["barrier_effect_persons"] = (
        table["covered_with_bridges_persons"] - table["covered_without_bridges_persons"]
    ).round(1)
    totals = table["group_total_persons"].replace(0.0, pd.NA)
    table["barrier_effect_percent"] = (
        (100.0 * table["barrier_effect_persons"] / totals).fillna(0.0).round(1)
    )
    return table.sort_values(["group", "service_type"]).reset_index(drop=True)


def _coverage_part(summary, population, mode, threshold, column):
    """Extrait une part de couverture du sommaire, renommee pour la comparaison."""
    subset = summary[
        (summary["population"] == population)
        & (summary["mode"] == mode)
        & (summary["threshold_m"] == threshold)
    ]
    return subset[["service_type", "covered_percent"]].rename(
        columns={"covered_percent": column}
    )


def population_comparison_table(summary, config):
    """Compare la couverture des aines et du reste de la population, marche et transport.

    Pour chaque type de service, les aines sont pris a 800 m et le reste a 1000 m, a la
    marche puis au transport. L'ecart montre que le reste est mieux desservi, donc que les
    besoins des deux groupes different. Retourne un tableau par type de service.
    """
    thr_seniors = config["optimization"]["coverage_threshold_seniors_m"]
    thr_rest = config["optimization"]["coverage_threshold_rest_m"]
    table = _coverage_part(
        summary, "seniors", "marche", thr_seniors, "seniors_walk_percent"
    )
    for population, mode, threshold, column in (
        ("rest", "marche", thr_rest, "rest_walk_percent"),
        ("seniors", "marche_transport", thr_seniors, "seniors_transit_percent"),
        ("rest", "marche_transport", thr_rest, "rest_transit_percent"),
    ):
        table = table.merge(
            _coverage_part(summary, population, mode, threshold, column),
            on="service_type",
            how="outer",
        )
    table["diff_walk_percent"] = (
        table["seniors_walk_percent"] - table["rest_walk_percent"]
    ).round(1)
    table["diff_transit_percent"] = (
        table["seniors_transit_percent"] - table["rest_transit_percent"]
    ).round(1)
    return table.sort_values("service_type").reset_index(drop=True)


def same_threshold_gap(summary, threshold_m):
    """Ecart de couverture a pied entre aines et reste, les deux au meme seuil.

    Le tableau de comparaison du projet mesure chaque groupe a sa propre distance
    tolerable, c'est le sens meme d'une lecture d'equite. Il ne dit pas pour autant si
    l'ecart obtenu vient de cette tolerance ou de la localisation des deux groupes. Placer
    les deux au meme seuil isole la localisation, la seule difference qui reste entre eux
    est alors la part d'aines de chaque aire de diffusion.

    Retourne le nombre de types de service ou les aines sont devant, le nombre de types
    compares et l'ecart moyen en points de pourcentage, ou None si le seuil demande est
    absent du sommaire pour l'un des deux groupes.
    """
    walk = summary[
        (summary["mode"] == "marche") & (summary["threshold_m"] == threshold_m)
    ]
    shares = walk.pivot_table(
        index="service_type", columns="population", values="covered_percent"
    )
    if "seniors" not in shares.columns or "rest" not in shares.columns:
        return None
    gap = (shares["seniors"] - shares["rest"]).dropna()
    if gap.empty:
        return None
    return int((gap > 0).sum()), len(gap), round(float(gap.mean()), 1)


def service_addition_effect_table(gains):
    """Effet de chaque ajout de service, par groupe.

    Une ligne par ajout, le groupe, le rang de l'ajout, le type ajoute, le site et sa
    position en degres, le seuil en metres, la part du groupe couverte apres cet ajout et
    le gain depuis le depart. La ligne de depart sans ajout est ecartee du tableau, mais
    elle sert de reference au gain, sinon le lecteur ne verrait qu'un niveau et jamais un
    gain.
    """
    baseline = (
        gains[gains["n_services"] == 0]
        .set_index("group")["weighted_covered_percent"]
        .to_dict()
    )
    effect = gains[gains["n_services"] >= 1].copy()
    effect["gain_percent"] = (
        effect["weighted_covered_percent"] - effect["group"].map(baseline)
    ).round(1)
    columns = [
        "group",
        "n_services",
        "added_type",
        "site_id",
        "latitude",
        "longitude",
        "threshold_m",
        "weighted_covered_percent",
        "gain_percent",
    ]
    return effect[columns].reset_index(drop=True)


def sector_table(address_sectors, site_sectors, geographic_crs, precision):
    """Tableau des secteurs d'un mode, adresses existantes et sites a implanter.

    Les deux types sont separes et donnent une seule aire par municipalite. Colonnes, type,
    municipalite, identifiant d'aire de diffusion, cote moyenne sur 100, cote qualitative
    moyenne, nombre de points, latitude et longitude du centroide.
    """
    blocks = []
    for layer, kind in (
        (address_sectors, "adresse existante"),
        (site_sectors, "site à implanter"),
    ):
        if layer is None or len(layer) == 0:
            continue
        latitude, longitude = latitude_longitude(
            layer.geometry.centroid, geographic_crs, precision
        )
        blocks.append(
            pd.DataFrame(
                {
                    "type": kind,
                    "municipality": layer["municipality"].to_numpy(),
                    "ad_id": layer["ad_id"].to_numpy(),
                    "mean_score_percent": layer["mean_score_percent"].to_numpy(),
                    "mean_quality": layer["mean_quality"].to_numpy(),
                    "n_points": layer["n_points"].to_numpy(),
                    "latitude": latitude.to_numpy(),
                    "longitude": longitude.to_numpy(),
                }
            )
        )
    return pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()
