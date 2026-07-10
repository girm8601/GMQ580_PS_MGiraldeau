"""Regeneration des donnees brutes du projet.

Les couches OpenStreetMap, reseau pietonnier, services, batiments, adresses
et plans d'eau, se telechargent ici avec OSMnx et s'ecrivent dans data/raw.
Les autres sources, recensement, limites, utilisation du sol et transport
exo, se telechargent manuellement depuis les liens du README, section
Donnees. Ce script verifie leur presence et signale ce qui manque.

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

# Colonnes conservees dans les fichiers OSM ecrits, le reste est du bruit.
SERVICE_COLUMNS = ["amenity", "shop", "name", "geometry"]
BUILDING_COLUMNS = ["building", "name", "geometry"]
ADDRESS_COLUMNS = ["addr:housenumber", "building", "geometry"]
WATER_COLUMNS = ["natural", "water", "name", "geometry"]


def check_manual_sources(config, logger):
    """Verifie la presence des sources telechargees manuellement."""
    raw_folder = config["chemins"]["data_raw"]
    missing = []
    for key, relative in config["chemins"]["fichiers"].items():
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
    polygon = study_zone.to_crs(config["crs_sources"]["osm"]).geometry.iloc[0]
    logger.info("Zone d'etude construite a partir des limites municipales")
    return polygon


def _osm_path(config, key):
    """Chemin complet d'un fichier OSM regenerable."""
    return os.path.join(
        config["chemins"]["data_raw"], config["chemins"]["fichiers_osm"][key]
    )


def _write_features(gdf, columns, path, logger, label):
    """Ecrit une couche OSM en GeoPackage avec les seules colonnes utiles."""
    kept = [column for column in columns if column in gdf.columns]
    gdf = gdf[kept].reset_index(drop=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gdf.to_file(path, driver="GPKG")
    logger.info("%s ecrits, %d entite(s), %s", label, len(gdf), path)


def download_osm(config, logger):
    """Telecharge les couches OpenStreetMap absentes de data/raw."""
    import osmnx as ox

    polygon = extraction_polygon(config, logger)

    graph_path = _osm_path(config, "graphe_pieton")
    if os.path.exists(graph_path):
        logger.info("Graphe deja present, %s, telechargement saute", graph_path)
    else:
        logger.info("Telechargement du reseau pietonnier OSM en cours")
        graph = ox.graph_from_polygon(
            polygon, network_type=config["reseau_pieton"]["network_type"]
        )
        os.makedirs(os.path.dirname(graph_path), exist_ok=True)
        ox.save_graphml(graph, graph_path)
        logger.info("Graphe pietonnier ecrit, %s", graph_path)

    services_path = _osm_path(config, "services")
    if os.path.exists(services_path):
        logger.info("Services deja presents, %s, telechargement saute", services_path)
    else:
        logger.info("Telechargement des services essentiels OSM en cours")
        tags = flatten_service_tags(config["services_essentiels"])
        services = ox.features_from_polygon(polygon, tags=tags)
        _write_features(services, SERVICE_COLUMNS, services_path, logger, "Services")

    buildings_path = _osm_path(config, "batiments")
    if os.path.exists(buildings_path):
        logger.info("Batiments deja presents, %s, telechargement saute", buildings_path)
    else:
        logger.info("Telechargement des batiments OSM en cours")
        buildings = ox.features_from_polygon(
            polygon, tags={config["batiments_residentiels"]["champ"]: True}
        )
        _write_features(
            buildings, BUILDING_COLUMNS, buildings_path, logger, "Batiments"
        )

    addresses_path = _osm_path(config, "adresses")
    if os.path.exists(addresses_path):
        logger.info("Adresses deja presentes, %s, telechargement saute", addresses_path)
    else:
        logger.info("Telechargement des noeuds d'adresse OSM en cours")
        addresses = ox.features_from_polygon(
            polygon, tags={config["batiments_residentiels"]["tag_adresses"]: True}
        )
        _write_features(addresses, ADDRESS_COLUMNS, addresses_path, logger, "Adresses")

    water_path = _osm_path(config, "hydrographie")
    if os.path.exists(water_path):
        logger.info("Hydrographie deja presente, %s, telechargement saute", water_path)
    else:
        logger.info("Telechargement des plans d'eau OSM en cours")
        water = ox.features_from_polygon(polygon, tags={"natural": "water"})
        water = water[water.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        _write_features(water, WATER_COLUMNS, water_path, logger, "Plans d'eau")


def main():
    """Point d'entree de la regeneration des donnees brutes."""
    config = load_config()
    logger = setup_logger(config["chemins"]["log_file"])
    logger.info("Regeneration des donnees brutes")
    if not check_manual_sources(config, logger):
        sys.exit(1)
    download_osm(config, logger)
    logger.info("Donnees brutes completes, lancer ensuite python main.py")


if __name__ == "__main__":
    main()
