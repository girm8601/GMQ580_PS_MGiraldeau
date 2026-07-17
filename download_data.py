"""Regeneration des couches OpenStreetMap du projet.

Les couches OpenStreetMap, reseau pietonnier, services, batiments, adresses,
plans d'eau et sites commerciaux, se telechargent ici avec OSMnx et s'ecrivent
dans data/processed, car elles sont generees par le pipeline et non fournies
telles quelles. Les autres sources, recensement, limites, utilisation du sol et
transport exo, se telechargent manuellement depuis les liens du README, section
Donnees, et vont dans data/raw. Ce script verifie leur presence et signale ce
qui manque.

Lancement, python download_data.py
"""

from __future__ import annotations

from src import _gdal_fix  # noqa: F401  (corrige le chargement de GDAL, comme au TD2)

import os
import sys

from config_loader import load_config
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


def download_osm(config, logger):
    """Telecharge les couches OpenStreetMap absentes de data/processed."""
    import osmnx as ox

    polygon = extraction_polygon(config, logger)
    columns = config["osm_columns"]
    extra_tags = config["osm_extra_tags"]

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

    services_path = _osm_path(config, "services")
    if os.path.exists(services_path):
        logger.info("Services deja presents, %s, telechargement saute", services_path)
    else:
        logger.info("Telechargement des services essentiels OSM en cours")
        tags = flatten_service_tags(config["essential_services"])
        services = ox.features_from_polygon(polygon, tags=tags)
        _write_features(
            services, columns["services"], services_path, logger, "Services"
        )

    buildings_path = _osm_path(config, "buildings")
    if os.path.exists(buildings_path):
        logger.info("Batiments deja presents, %s, telechargement saute", buildings_path)
    else:
        logger.info("Telechargement des batiments OSM en cours")
        buildings = ox.features_from_polygon(
            polygon, tags={config["residential_buildings"]["field"]: True}
        )
        _write_features(
            buildings, columns["buildings"], buildings_path, logger, "Batiments"
        )

    addresses_path = _osm_path(config, "addresses")
    if os.path.exists(addresses_path):
        logger.info("Adresses deja presentes, %s, telechargement saute", addresses_path)
    else:
        logger.info("Telechargement des noeuds d'adresse OSM en cours")
        addresses = ox.features_from_polygon(
            polygon, tags={config["residential_buildings"]["address_tag"]: True}
        )
        _write_features(
            addresses, columns["addresses"], addresses_path, logger, "Adresses"
        )

    water_path = _osm_path(config, "water")
    if os.path.exists(water_path):
        logger.info("Hydrographie deja presente, %s, telechargement saute", water_path)
    else:
        logger.info("Telechargement des plans d'eau OSM en cours")
        water = ox.features_from_polygon(polygon, tags=extra_tags["water"])
        water = water[water.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        _write_features(water, columns["water"], water_path, logger, "Plans d'eau")

    commercial_path = _osm_path(config, "commercial")
    if os.path.exists(commercial_path):
        logger.info(
            "Terrains commerciaux deja presents, %s, telechargement saute",
            commercial_path,
        )
    else:
        logger.info("Telechargement des terrains commerciaux OSM en cours")
        try:
            commercial = ox.features_from_polygon(
                polygon, tags=extra_tags["commercial"]
            )
            commercial = commercial[
                commercial.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
            ]
            _write_features(
                commercial,
                columns["commercial"],
                commercial_path,
                logger,
                "Terrains commerciaux",
            )
        except Exception as error:
            logger.warning(
                "Terrains commerciaux non recuperes (%s), croisement des sites "
                "candidats saute",
                error,
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
