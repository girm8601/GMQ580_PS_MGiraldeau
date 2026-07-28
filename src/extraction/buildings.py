"""Batiments residentiels OpenStreetMap, filtrage et points d'origine.

L'experience de GMQ210 a montre qu'une seule etiquette ne suffit pas. La liste
des valeurs retenues vient de config.yaml. La valeur generique yes ne compte
comme residentielle que si le batiment tombe dans un polygone OpenStreetMap
landuse=residential, decision documentee au README. Les noeuds d'adresse isoles
completent les batiments manquants. Chaque residence porte une etiquette
d'adresse construite a partir du numero civique et de la rue.
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd

from src.io import reproject


def build_address_label(row, housenumber_field, street_field):
    """Construit l'etiquette d'adresse a partir du numero civique et de la rue.

    Retourne None si aucune information d'adresse n'est disponible, l'appelant
    remplace alors par une etiquette generique.
    """
    housenumber = row.get(housenumber_field)
    street = row.get(street_field)
    housenumber = "" if pd.isna(housenumber) else str(housenumber)
    street = "" if pd.isna(street) else str(street)
    combined = (housenumber + " " + street).strip()
    return combined if combined else None


def filter_residential(buildings_gdf, buildings_config, residential_zones=None):
    """Filtre les batiments residentiels et compte les types ecartes.

    Retourne le GeoDataFrame filtre et un dictionnaire des types ecartes avec
    leur compte, journalise ensuite pour verifier qu'aucun type pertinent ne
    manque dans la zone.
    """
    tag_field = buildings_config["field"]
    kept_types = list(buildings_config["kept_types"])
    generic_value = buildings_config["generic_value"]

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


def load_residences(config, residential_gdf, logger=None):
    """Charge les residences, batiments filtres et adresses isolees en points.

    residential_gdf est la couche OpenStreetMap landuse=residential, ou None si elle
    n'a pas ete telechargee. Elle sert a trancher le sort des batiments generiques yes.
    """
    buildings_config = config["residential_buildings"]
    housenumber_field = buildings_config["housenumber_field"]
    street_field = buildings_config["street_field"]
    tag_field = buildings_config["field"]
    processed_folder = config["paths"]["data_processed"]

    buildings_path = os.path.join(
        processed_folder, config["paths"]["osm_files"]["buildings"]
    )
    addresses_path = os.path.join(
        processed_folder, config["paths"]["osm_files"]["addresses"]
    )
    if not os.path.exists(buildings_path):
        raise FileNotFoundError(
            f"Batiments OSM introuvables, {buildings_path}. Lancer d'abord download_data.py"
        )

    buildings = gpd.read_file(buildings_path)
    buildings = reproject(buildings, config["target_crs"])
    residential, excluded_counts = filter_residential(
        buildings, buildings_config, residential_gdf
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

    def with_address(gdf, source):
        """Ajoute l'etiquette d'adresse, la source et le point representatif."""
        gdf = gdf.copy()
        gdf["address"] = gdf.apply(
            lambda row: build_address_label(row, housenumber_field, street_field),
            axis=1,
        )
        gdf["geometry"] = gdf.geometry.representative_point()
        gdf["source"] = source
        return gdf[["geometry", "source", "address"]]

    frames = [with_address(residential, "batiment")]

    # Les noeuds d'adresse isoles completent les batiments non cartographies.
    if os.path.exists(addresses_path):
        addresses = gpd.read_file(addresses_path)
        addresses = reproject(addresses, config["target_crs"])
        if tag_field in addresses.columns:
            addresses = addresses[addresses[tag_field].isna()]
        frames.append(with_address(addresses, "adresse"))
        if logger is not None:
            logger.info("Noeuds d'adresse isoles ajoutes, %d", len(frames[-1]))

    residences = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), crs=config["target_crs"]
    )
    residences = residences.drop_duplicates(subset=["geometry"]).reset_index(drop=True)
    residences["residence_id"] = residences.index
    missing_address = residences["address"].isna()
    residences.loc[missing_address, "address"] = "Residence " + residences.loc[
        missing_address, "residence_id"
    ].astype(str)
    return residences
