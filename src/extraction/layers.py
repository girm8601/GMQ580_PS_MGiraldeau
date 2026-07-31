"""Chargement de toutes les couches du projet, en une seule etape.

Ce module appelle chaque lecteur de src/extraction dans le bon ordre et retourne un
dictionnaire de couches pretes pour l'audit puis l'analyse. Les geometries invalides sont
corrigees ici, les arrets hors de la zone d'etude sont ecartes et les lignes de train sont
decoupees a la zone. Tout ce qui suit dans le pipeline part de ce dictionnaire.
"""

from __future__ import annotations

import geopandas as gpd

from src.extraction.buildings import load_residences
from src.extraction.census import load_census_profile
from src.extraction.network import load_walk_graph
from src.extraction.reference_layers import (
    load_commercial,
    load_development,
    load_dissemination_areas,
    load_municipalities,
    load_residential,
    load_water,
)
from src.extraction.services import load_services
from src.extraction.transit import (
    load_bus_stops,
    load_route_stops,
    load_train_lines,
    load_train_stations,
)
from src.processing.study_area import build_zone
from src.validation.audit import fix_invalid_geometries


def load_all_layers(config, logger):
    """Charge toutes les couches du projet et retourne un dictionnaire."""
    municipalities = load_municipalities(config)
    study_zone = build_zone(municipalities, config)
    areas = load_dissemination_areas(config, study_zone)
    areas, _ = fix_invalid_geometries(areas, "dissemination_areas", logger)
    residential = load_residential(config, study_zone, logger)
    if residential is not None:
        residential, _ = fix_invalid_geometries(residential, "residential", logger)
    layers = {
        "municipalities": municipalities,
        "study_zone": study_zone,
        "areas": areas,
        "residential": residential,
        "census": load_census_profile(config, logger),
        "stops": load_bus_stops(config, logger),
        "route_stops": load_route_stops(config, logger),
        "stations": load_train_stations(config, logger),
        "lines": load_train_lines(config, logger),
        "graph": load_walk_graph(config, logger),
        "services": load_services(config, logger),
    }
    layers["residences"] = load_residences(config, residential, logger)
    layers["water"] = load_water(config, study_zone, logger)
    layers["commercial"] = load_commercial(config, study_zone, logger)
    layers["development"] = load_development(config, study_zone, logger)
    for key in ("commercial", "development"):
        if layers[key] is not None:
            layers[key], _ = fix_invalid_geometries(layers[key], key, logger)

    # Les arrets hors de la zone d'etude sont ecartes.
    zone_union = study_zone.union_all()
    before = len(layers["stops"])
    layers["stops"] = layers["stops"][layers["stops"].within(zone_union)].copy()
    logger.info(
        "Arrets conserves dans la zone d'etude, %d sur %d",
        len(layers["stops"]),
        before,
    )

    layers["lines"] = gpd.clip(layers["lines"], study_zone)
    layers["lines"] = layers["lines"][~layers["lines"].geometry.is_empty].copy()
    return layers
