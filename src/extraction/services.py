"""Services essentiels OpenStreetMap, lecture et typage par le projet.

Chaque point d'interet recoit le type de service du projet, epicerie,
pharmacie et les autres, selon les etiquettes amenity et shop declarees
dans config.yaml. Les entites sans type reconnu sont ecartees.
"""

from __future__ import annotations

import os

import geopandas as gpd

from src.io import reproject


def flatten_service_tags(services_config):
    """Fusionne les etiquettes de tous les types pour la requete OSM."""
    tags = {}
    for type_tags in services_config.values():
        for tag_key, values in type_tags.items():
            tags.setdefault(tag_key, [])
            for value in values:
                if value not in tags[tag_key]:
                    tags[tag_key].append(value)
    return tags


def assign_service_type(pois_gdf, services_config):
    """Attribue a chaque point d'interet son type de service du projet.

    Le premier type dont une etiquette correspond est retenu. Les entites
    sans correspondance recoivent None et seront ecartees par l'appelant.
    """

    def type_for_row(row):
        for service_type, type_tags in services_config.items():
            for tag_key, values in type_tags.items():
                if tag_key in row and row[tag_key] in values:
                    return service_type
        return None

    pois_gdf = pois_gdf.copy()
    pois_gdf["service_type"] = pois_gdf.apply(type_for_row, axis=1)
    return pois_gdf


def load_services(config, logger=None):
    """Charge les points d'interet OSM, les type et les projette."""
    path = os.path.join(
        config["chemins"]["data_raw"], config["chemins"]["fichiers_osm"]["services"]
    )
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Services OSM introuvables, {path}. Lancer d'abord download_data.py"
        )
    pois = gpd.read_file(path)
    pois = assign_service_type(pois, config["services_essentiels"])
    typed = pois[pois["service_type"].notna()].copy()
    # Les surfaces deviennent des points pour le calcul des distances.
    typed["geometry"] = typed.geometry.representative_point()
    if logger is not None:
        logger.info(
            "Services essentiels types, %d sur %d points d'interet",
            len(typed),
            len(pois),
        )
    return reproject(typed, config["crs_cible"])
