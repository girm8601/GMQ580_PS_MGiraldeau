"""Couches de reference, limites municipales, aires de diffusion et sol.

Chaque fonction lit une source brute de data_raw, la ramene au CRS cible et
retourne un GeoDataFrame pret pour l'audit puis l'analyse. Les couches OSM
regenerees par download_data.py sont lues dans data_processed. Les chemins et
les noms de champs viennent tous de config.yaml.
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd

from src.io import reproject


def _raw_path(config, key):
    """Chemin complet d'une source manuelle declaree dans la configuration."""
    return os.path.join(
        config["paths"]["data_raw"], config["paths"]["manual_files"][key]
    )


def _osm_path(config, key):
    """Chemin complet d'une couche OSM regeneree, ecrite dans data_processed."""
    return os.path.join(
        config["paths"]["data_processed"], config["paths"]["osm_files"][key]
    )


def load_municipalities(config):
    """Charge les limites des municipalites de la zone d'etude."""
    name_field = config["study_area"]["municipality_name_field"]
    wanted = config["study_area"]["municipalities"]
    municipalities = gpd.read_file(_raw_path(config, "municipal_limits"))
    municipalities = municipalities[municipalities[name_field].isin(wanted)]
    return reproject(municipalities, config["target_crs"])


def load_dissemination_areas(config, study_zone):
    """Charge les aires de diffusion de la zone d'etude.

    Le fichier national est volumineux, la lecture est donc limitee a l'emprise
    de la zone reprojetee dans le CRS source pour rester rapide. Une aire
    appartient a la zone si son point representatif s'y trouve, ce qui ecarte
    les aires des villes voisines qui ne font que toucher la limite.
    """
    source_crs = config["source_crs"]["dissemination_areas"]
    bbox_zone = study_zone.to_crs(source_crs)
    areas = gpd.read_file(
        _raw_path(config, "dissemination_areas"), bbox=tuple(bbox_zone.total_bounds)
    )
    areas = reproject(areas, config["target_crs"])
    zone_union = study_zone.union_all()
    return areas[areas.geometry.representative_point().within(zone_union)].copy()


def load_land_use(config):
    """Charge et fusionne les quatre fichiers d'utilisation du sol de la CMM."""
    parts = []
    for relative_path in config["paths"]["manual_files"]["land_use"]:
        path = os.path.join(config["paths"]["data_raw"], relative_path)
        parts.append(gpd.read_file(path))
    land_use = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    return reproject(land_use, config["target_crs"])


def load_commercial(config, study_zone, logger=None):
    """Charge les terrains commerciaux OSM (landuse=commercial) pour les sites candidats.

    Ces polygones servent a croiser les terrains commerciaux de la CMM (code 200) afin
    d'ecarter les erreurs de classement de la CMM. Retourne None si le fichier n'a pas
    encore ete telecharge, le pipeline se rabat alors sur les seuls terrains de la CMM.
    """
    path = _osm_path(config, "commercial")
    if not os.path.exists(path):
        if logger is not None:
            logger.warning(
                "Terrains commerciaux OSM absents, %s. Relancer download_data.py",
                path,
            )
        return None
    commercial = gpd.read_file(path)
    commercial = reproject(commercial, config["target_crs"])
    commercial = gpd.clip(commercial, study_zone)
    commercial = commercial[~commercial.geometry.is_empty].copy()
    if logger is not None:
        logger.info("Terrains commerciaux OSM charges, %d entite(s)", len(commercial))
    return commercial


def load_water(config, study_zone, logger=None):
    """Charge les plans d'eau OSM pour l'affichage de la riviere Richelieu.

    Couche de contexte cartographique seulement, elle n'entre dans aucun calcul
    et elle est decoupee a la zone d'etude pour ne pas deborder des cartes.
    Retourne None si le fichier n'a pas encore ete telecharge, la carte s'affiche
    alors sans la riviere plutot que de bloquer le pipeline.
    """
    path = _osm_path(config, "water")
    if not os.path.exists(path):
        if logger is not None:
            logger.warning(
                "Hydrographie absente, %s. Relancer download_data.py pour l'ajouter",
                path,
            )
        return None
    water = gpd.read_file(path)
    water = reproject(water, config["target_crs"])
    water = gpd.clip(water, study_zone)
    water = water[~water.geometry.is_empty].copy()
    if logger is not None:
        logger.info("Plans d'eau charges pour la carte, %d entite(s)", len(water))
    return water
