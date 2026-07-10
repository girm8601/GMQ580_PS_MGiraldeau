"""Batiments residentiels OpenStreetMap, filtrage et points d'origine.

L'experience de GMQ210 a montre qu'une seule etiquette ne suffit pas. La
liste des valeurs retenues vient de config.yaml. La valeur generique yes ne
compte comme residentielle que si le batiment tombe dans un polygone d'usage
residentiel de la CMM, decision documentee au README. Les noeuds d'adresse
isoles completent les batiments manquants.
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd

from src.io import reproject


def filter_residential(buildings_gdf, buildings_config, residential_zones=None):
    """Filtre les batiments residentiels et compte les types ecartes.

    Retourne le GeoDataFrame filtre et un dictionnaire des types ecartes avec
    leur compte, journalise ensuite pour verifier qu'aucun type pertinent ne
    manque dans la zone.
    """
    tag_field = buildings_config["champ"]
    kept_types = list(buildings_config["types_retenus"])
    generic_value = "yes"

    values = buildings_gdf[tag_field]
    keep_mask = values.isin([t for t in kept_types if t != generic_value])

    if generic_value in kept_types:
        generic_mask = values == generic_value
        if residential_zones is not None and generic_mask.any():
            zones_union = residential_zones.union_all()
            inside = buildings_gdf.geometry.representative_point().within(zones_union)
            keep_mask = keep_mask | (generic_mask & inside)
        elif residential_zones is None:
            keep_mask = keep_mask | generic_mask

    excluded = buildings_gdf[~keep_mask]
    excluded_counts = excluded[tag_field].value_counts().to_dict()
    return buildings_gdf[keep_mask].copy(), excluded_counts


def residential_land_use(land_use_gdf, config):
    """Retourne les polygones d'usage residentiel de la CMM."""
    code_field = config["utilisation_sol"]["champ_code"]
    residential_codes = config["batiments_residentiels"]["codes_sol_residentiels"]
    codes = pd.to_numeric(land_use_gdf[code_field], errors="coerce")
    return land_use_gdf[codes.isin(residential_codes)].copy()


def load_residences(config, land_use_gdf, logger=None):
    """Charge les residences, batiments filtres et adresses isolees en points."""
    raw_folder = config["chemins"]["data_raw"]
    buildings_path = os.path.join(
        raw_folder, config["chemins"]["fichiers_osm"]["batiments"]
    )
    addresses_path = os.path.join(
        raw_folder, config["chemins"]["fichiers_osm"]["adresses"]
    )
    if not os.path.exists(buildings_path):
        raise FileNotFoundError(
            f"Batiments OSM introuvables, {buildings_path}. Lancer d'abord download_data.py"
        )

    buildings = gpd.read_file(buildings_path)
    buildings = reproject(buildings, config["crs_cible"])
    zones = residential_land_use(land_use_gdf, config)
    residential, excluded_counts = filter_residential(
        buildings, config["batiments_residentiels"], zones
    )
    if logger is not None:
        logger.info(
            "Batiments residentiels retenus, %d sur %d",
            len(residential),
            len(buildings),
        )
        for tag_value, count in sorted(excluded_counts.items(), key=lambda x: -x[1])[
            :10
        ]:
            logger.info("Type de batiment ecarte, %s, %d entite(s)", tag_value, count)

    residential = residential.copy()
    residential["geometry"] = residential.geometry.representative_point()
    residential["source"] = "batiment"
    frames = [residential[["geometry", "source"]]]

    # Les noeuds d'adresse isoles completent les batiments non cartographies.
    if os.path.exists(addresses_path):
        addresses = gpd.read_file(addresses_path)
        addresses = reproject(addresses, config["crs_cible"])
        tag_field = config["batiments_residentiels"]["champ"]
        if tag_field in addresses.columns:
            addresses = addresses[addresses[tag_field].isna()]
        addresses = addresses.copy()
        addresses["geometry"] = addresses.geometry.representative_point()
        addresses["source"] = "adresse"
        frames.append(addresses[["geometry", "source"]])
        if logger is not None:
            logger.info("Noeuds d'adresse isoles ajoutes, %d", len(addresses))

    residences = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), crs=config["crs_cible"]
    )
    residences = residences.drop_duplicates(subset=["geometry"]).reset_index(drop=True)
    residences["residence_id"] = residences.index
    return residences
