"""Couches de reference, limites municipales, aires de diffusion et usage du sol OSM.

Chaque fonction lit une source de data_raw ou une couche OSM de data_processed, la
ramene au CRS cible et retourne un GeoDataFrame pret pour l'audit puis l'analyse. Les
chemins et les noms de champs viennent tous de config.yaml.
"""

from __future__ import annotations

import os

import geopandas as gpd

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


def load_commercial(config, study_zone, logger=None):
    """Charge les terrains commerciaux OSM (landuse commercial et retail) pour l'ajout.

    Ces polygones fournissent les sites candidats de la validation qui verifie que
    l'ajout de services essentiels ne rapporte pas assez pour etre la solution. Les sites
    commerciaux sont un choix plus simple car les locaux et les sites sont parfois deja
    disponibles. Retourne None si le fichier n'a pas encore ete telecharge, la validation
    d'ajout est alors simplement sautee.
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


def load_residential(config, study_zone, logger=None):
    """Charge les terrains residentiels OSM (landuse=residential).

    Ces polygones confirment qu'un batiment generique yes est bien residentiel, en
    remplacement des anciennes donnees d'usage du sol de la CMM. Retourne None si le
    fichier n'a pas encore ete telecharge, le filtrage des residences se rabat alors
    sur le seul comportement de GMQ210.
    """
    path = _osm_path(config, "residential_landuse")
    if not os.path.exists(path):
        if logger is not None:
            logger.warning(
                "Terrains residentiels OSM absents, %s. Relancer download_data.py",
                path,
            )
        return None
    residential = gpd.read_file(path)
    residential = reproject(residential, config["target_crs"])
    residential = gpd.clip(residential, study_zone)
    residential = residential[~residential.geometry.is_empty].copy()
    if logger is not None:
        logger.info("Terrains residentiels OSM charges, %d entite(s)", len(residential))
    return residential


def load_development(config, study_zone, logger=None):
    """Charge les terrains a developper OSM pour le logement aine.

    Ces terrains regroupent les friches (brownfield), les terrains vierges (greenfield) et
    les chantiers (construction). Ce sont les sites candidats ou du logement pour aines
    pourrait etre implante, retenus par l'optimisation selon leur accessibilite a pied aux
    services. Retourne None si le fichier n'a pas encore ete telecharge ou si la zone n'en
    compte aucun, le siting du logement est alors simplement saute.
    """
    path = _osm_path(config, "development")
    if not os.path.exists(path):
        if logger is not None:
            logger.warning(
                "Terrains a developper OSM absents, %s. Relancer download_data.py",
                path,
            )
        return None
    development = gpd.read_file(path)
    development = reproject(development, config["target_crs"])
    development = gpd.clip(development, study_zone)
    development = development[~development.geometry.is_empty].copy()
    if logger is not None:
        logger.info("Terrains a developper OSM charges, %d entite(s)", len(development))
    return development


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
