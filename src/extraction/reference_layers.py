"""Couches de reference, limites municipales, aires de diffusion et sol.

Chaque fonction lit une source brute de data_raw, la ramene au CRS cible et
retourne un GeoDataFrame pret pour l'audit puis l'analyse. Les chemins et les
noms de champs viennent tous de config.yaml.
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd

from src.io import reproject


def _raw_path(config, key):
    """Chemin complet d'un fichier source declare dans la configuration."""
    return os.path.join(
        config["chemins"]["data_raw"], config["chemins"]["fichiers"][key]
    )


def load_municipalities(config):
    """Charge les limites des municipalites de la zone d'etude."""
    name_field = config["zone_etude"]["champ_nom_municipalite"]
    wanted = config["zone_etude"]["municipalites"]
    municipalities = gpd.read_file(_raw_path(config, "limites_municipales"))
    municipalities = municipalities[municipalities[name_field].isin(wanted)]
    return reproject(municipalities, config["crs_cible"])


def load_dissemination_areas(config, study_zone):
    """Charge les aires de diffusion de la zone d'etude.

    Le fichier national est volumineux, la lecture est donc limitee a
    l'emprise de la zone reprojetee dans le CRS source pour rester rapide.
    Une aire appartient a la zone si son point representatif s'y trouve, ce
    qui ecarte les aires des villes voisines qui ne font que toucher la
    limite.
    """
    source_crs = config["crs_sources"]["aires_diffusion"]
    bbox_zone = study_zone.to_crs(source_crs)
    areas = gpd.read_file(
        _raw_path(config, "aires_diffusion"), bbox=tuple(bbox_zone.total_bounds)
    )
    areas = reproject(areas, config["crs_cible"])
    zone_union = study_zone.union_all()
    return areas[areas.geometry.representative_point().within(zone_union)].copy()


def load_land_use(config):
    """Charge et fusionne les quatre fichiers d'utilisation du sol de la CMM."""
    parts = []
    for relative_path in config["chemins"]["fichiers"]["utilisation_sol"]:
        path = os.path.join(config["chemins"]["data_raw"], relative_path)
        parts.append(gpd.read_file(path))
    land_use = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    return reproject(land_use, config["crs_cible"])


def load_water(config, study_zone, logger=None):
    """Charge les plans d'eau OSM pour l'affichage de la riviere Richelieu.

    Couche de contexte cartographique seulement, elle n'entre dans aucun
    calcul et elle est decoupee a la zone d'etude pour ne pas deborder des
    cartes. Retourne None si le fichier n'a pas encore ete telecharge, la
    carte s'affiche alors sans la riviere plutot que de bloquer le pipeline.
    """
    path = os.path.join(
        config["chemins"]["data_raw"], config["chemins"]["fichiers_osm"]["hydrographie"]
    )
    if not os.path.exists(path):
        if logger is not None:
            logger.warning(
                "Hydrographie absente, %s. Relancer download_data.py pour l'ajouter",
                path,
            )
        return None
    water = gpd.read_file(path)
    water = reproject(water, config["crs_cible"])
    water = gpd.clip(water, study_zone)
    water = water[~water.geometry.is_empty].copy()
    if logger is not None:
        logger.info("Plans d'eau charges pour la carte, %d entite(s)", len(water))
    return water
