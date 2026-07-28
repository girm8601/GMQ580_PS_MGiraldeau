"""Regeneration des couches OpenStreetMap du projet.

Les couches OpenStreetMap, reseau pietonnier, services, batiments, adresses,
plans d'eau, terrains commerciaux, residentiels et a developper, se telechargent
ici avec OSMnx et s'ecrivent dans data/processed, car elles sont generees par le
pipeline et non fournies telles quelles. Les autres sources, recensement, limites
et transport exo, se telechargent manuellement depuis les liens du README, section
Donnees, et vont dans data/raw. Ce script verifie leur presence et signale ce
qui manque.

Lancement, python download_data.py
"""

from __future__ import annotations

import os
import sys

from config_loader import load_config
from src import _gdal_fix  # noqa: F401  (corrige le chargement de GDAL, comme au TD2)
from src.extraction.reference_layers import load_municipalities
from src.extraction.services import flatten_service_tags
from src.logger import setup_logger
from src.processing.study_area import build_zone


def check_manual_sources(config, logger):
    """Verifie la presence des sources telechargees manuellement."""
    raw_folder = config["paths"]["data_raw"]
    missing = []
    for key, relative in config["paths"]["manual_files"].items():
        paths = relative if isinstance(relative, list) else [relative]
        for path in paths:
            full_path = os.path.join(raw_folder, path)
            if not os.path.exists(full_path):
                missing.append(f"{key} attendu dans {full_path}")
    if missing:
        for line in missing:
            logger.error("Source manquante, %s", line)
        logger.error(
            "Telecharger ces sources depuis les liens du README, section Donnees"
        )
        return False
    logger.info("Toutes les sources manuelles sont presentes")
    return True


def extraction_polygon(config, logger):
    """Construit le polygone de la zone d'etude en coordonnees geographiques."""
    municipalities = load_municipalities(config)
    study_zone = build_zone(municipalities, config)
    polygon = study_zone.to_crs(config["source_crs"]["osm"]).geometry.iloc[0]
    logger.info("Zone d'etude construite a partir des limites municipales")
    return polygon


def _osm_path(config, key):
    """Chemin complet d'une couche OSM regeneree, ecrite dans data_processed."""
    return os.path.join(
        config["paths"]["data_processed"], config["paths"]["osm_files"][key]
    )


def _write_features(gdf, columns, path, logger, label):
    """Ecrit une couche OSM en GeoPackage avec les seules colonnes utiles."""
    kept = [column for column in columns if column in gdf.columns]
    gdf = gdf[kept].reset_index(drop=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gdf.to_file(path, driver="GPKG")
    logger.info("%s ecrits, %d entite(s), %s", label, len(gdf), path)


def _download_layer(
    polygon,
    config,
    path_key,
    columns_key,
    tags,
    label,
    logger,
    polygons_only=False,
    optional_note=None,
):
    """Telecharge une couche vectorielle OSM si elle est absente de data/processed.

    tags est la requete OSMnx. polygons_only ne garde que les polygones. Si optional_note
    est fourni, un echec est journalise en avertissement suivi de cette note sur la
    consequence, plutot que de bloquer le pipeline.
    """
    import osmnx as ox

    path = _osm_path(config, path_key)
    if os.path.exists(path):
        logger.info("%s, couche deja presente (%s), telechargement saute", label, path)
        return
    logger.info("Telechargement OSM en cours, %s", label)
    try:
        features = ox.features_from_polygon(polygon, tags=tags)
        if polygons_only:
            keep = features.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
            features = features[keep]
        _write_features(
            features, config["osm_columns"][columns_key], path, logger, label
        )
    except Exception as error:
        if optional_note is None:
            raise
        logger.warning("%s non recuperes (%s), %s", label, error, optional_note)


def download_osm(config, logger):
    """Telecharge les couches OpenStreetMap absentes de data/processed."""
    import osmnx as ox

    polygon = extraction_polygon(config, logger)
    extra_tags = config["osm_extra_tags"]
    buildings_field = config["residential_buildings"]["field"]
    address_tag = config["residential_buildings"]["address_tag"]

    graph_path = _osm_path(config, "walk_graph")
    if os.path.exists(graph_path):
        logger.info("Graphe deja present, %s, telechargement saute", graph_path)
    else:
        logger.info("Telechargement du reseau pietonnier OSM en cours")
        graph = ox.graph_from_polygon(
            polygon, network_type=config["walk_network"]["network_type"]
        )
        os.makedirs(os.path.dirname(graph_path), exist_ok=True)
        ox.save_graphml(graph, graph_path)
        logger.info("Graphe pietonnier ecrit, %s", graph_path)

    _download_layer(
        polygon,
        config,
        "services",
        "services",
        flatten_service_tags(config["essential_services"]),
        "Services",
        logger,
    )
    _download_layer(
        polygon,
        config,
        "buildings",
        "buildings",
        {buildings_field: True},
        "Batiments",
        logger,
    )
    _download_layer(
        polygon,
        config,
        "addresses",
        "addresses",
        {address_tag: True},
        "Adresses",
        logger,
    )
    _download_layer(
        polygon,
        config,
        "water",
        "water",
        extra_tags["water"],
        "Plans d'eau",
        logger,
        polygons_only=True,
    )
    _download_layer(
        polygon,
        config,
        "commercial",
        "commercial",
        extra_tags["commercial"],
        "Terrains commerciaux",
        logger,
        polygons_only=True,
        optional_note="validation d'ajout de services sautee",
    )
    _download_layer(
        polygon,
        config,
        "residential_landuse",
        "residential",
        extra_tags["residential"],
        "Terrains residentiels",
        logger,
        polygons_only=True,
    )
    _download_layer(
        polygon,
        config,
        "development",
        "development",
        extra_tags["development"],
        "Terrains a developper",
        logger,
        polygons_only=True,
        optional_note="siting du logement aine saute",
    )


def main():
    """Point d'entree de la regeneration des couches OSM."""
    config = load_config()
    logger = setup_logger(config["paths"]["log_file"], config["logging"]["level"])
    logger.info("Regeneration des couches OpenStreetMap")
    if not check_manual_sources(config, logger):
        sys.exit(1)
    download_osm(config, logger)
    logger.info("Couches OSM completes, lancer ensuite python main.py")


if __name__ == "__main__":
    main()
