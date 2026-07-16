"""Point d'entree unique du projet, il orchestre le pipeline sans traiter.

main.py enchaine les etapes dans l'ordre du schema du README et delegue tout le
traitement aux modules de src. Chaque etape est une fonction nommee d'un module de
responsabilite, extraction, traitement, validation, resultats et visualisation.
Lancement, python main.py, apres avoir regenere les couches OSM avec download_data.py.
"""

from __future__ import annotations

from src import _gdal_fix  # noqa: F401  (corrige le chargement de GDAL, comme au TD2)

import os

import geopandas as gpd
import pandas as pd

from config_loader import load_config
from src.extraction.buildings import load_residences
from src.extraction.census import load_census_profile
from src.extraction.network import load_walk_graph
from src.extraction.reference_layers import (
    load_commercial,
    load_dissemination_areas,
    load_land_use,
    load_municipalities,
    load_water,
)
from src.extraction.services import load_services
from src.extraction.transit import load_bus_stops, load_train_lines, load_train_stations
from src.logger import setup_logger
from src.processing.accessibility import compute_distances, scored_residences
from src.processing.coverage import coverage_summary
from src.processing.demand import prepare_demand
from src.processing.scenarios import optimization_s1
from src.processing.study_area import build_zone
from src.processing.transit_access import transit_distances_by_type
from src.results.metrics import export_table
from src.validation.audit import fix_invalid_geometries, run_audit
from src.validation.bridges import barrier_analysis
from src.visualization.charts import gain_curve_chart, s0_coverage_chart
from src.visualization.maps import s0_map


def save_processed(gdf, config, key, logger):
    """Ecrit une couche intermediaire verifiable dans QGIS."""
    path = os.path.join(
        config["paths"]["data_processed"],
        config["paths"]["processed_files"][key],
    )
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    gdf.to_file(path, driver="GPKG")
    logger.info("Couche intermediaire ecrite, %s, %d entite(s)", path, len(gdf))


def walk_edges_for_display(graph):
    """Reseau pietonnier simplifie pour l'affichage des cartes."""
    import osmnx as ox

    edges = ox.graph_to_gdfs(graph, nodes=False).reset_index()
    if {"u", "v"}.issubset(edges.columns):
        edges = edges[edges["u"] < edges["v"]]
    edges = edges[["geometry"]].copy()
    edges["geometry"] = edges.geometry.simplify(2)
    return edges


def load_all_layers(config, logger):
    """Charge toutes les couches du projet et retourne un dictionnaire."""
    municipalities = load_municipalities(config)
    study_zone = build_zone(municipalities, config)
    land_use = load_land_use(config)
    land_use, _ = fix_invalid_geometries(land_use, "land_use", logger)
    areas = load_dissemination_areas(config, study_zone)
    areas, _ = fix_invalid_geometries(areas, "dissemination_areas", logger)
    layers = {
        "municipalities": municipalities,
        "study_zone": study_zone,
        "land_use": land_use,
        "areas": areas,
        "census": load_census_profile(config, logger),
        "stops": load_bus_stops(config, logger),
        "stations": load_train_stations(config, logger),
        "lines": load_train_lines(config, logger),
        "graph": load_walk_graph(config, logger),
        "services": load_services(config, logger),
    }
    layers["residences"] = load_residences(config, land_use, logger)
    layers["water"] = load_water(config, study_zone, logger)
    layers["commercial"] = load_commercial(config, study_zone, logger)

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


def audit_all_layers(layers, config, logger):
    """Audite toutes les couches spatiales avant le moindre traitement."""
    crs = config["target_crs"]
    zone = layers["study_zone"]
    name_field = config["study_area"]["municipality_name_field"]
    join_field = config["vulnerability"]["ad_join_field"]
    code_field = config["land_use"]["code_field"]
    entries = [
        {
            "gdf": layers["municipalities"],
            "name": "municipal_limits",
            "crs": crs,
            "required_fields": [name_field],
        },
        {
            "gdf": layers["areas"],
            "name": "dissemination_areas",
            "crs": crs,
            "required_fields": [join_field],
            "zone": zone,
        },
        {
            "gdf": layers["land_use"],
            "name": "land_use",
            "crs": crs,
            "required_fields": [code_field],
            "zone": zone,
        },
        {"gdf": layers["stops"], "name": "bus_stops", "crs": crs, "zone": zone},
        {
            "gdf": layers["stations"],
            "name": "train_stations",
            "crs": crs,
            "required_fields": ["nom_gare"],
        },
        {
            "gdf": layers["lines"],
            "name": "train_lines",
            "crs": crs,
            "required_fields": ["nom_train"],
        },
        {
            "gdf": layers["services"],
            "name": "essential_services",
            "crs": crs,
            "required_fields": ["service_type"],
            "zone": zone,
        },
        {"gdf": layers["residences"], "name": "residences", "crs": crs, "zone": zone},
    ]
    if layers.get("water") is not None:
        entries.append({"gdf": layers["water"], "name": "water", "crs": crs})
    if layers.get("commercial") is not None:
        entries.append(
            {
                "gdf": layers["commercial"],
                "name": "commercial",
                "crs": crs,
                "zone": zone,
            }
        )
    run_audit(entries, config["paths"]["audit_report"], logger)


def run_pipeline():
    """Enchaine toutes les etapes du pipeline et ecrit les sorties."""
    config = load_config()
    logger = setup_logger(config["paths"]["log_file"])
    logger.info("Demarrage du pipeline")

    layers = load_all_layers(config, logger)
    audit_all_layers(layers, config, logger)

    areas, residences = prepare_demand(layers, config, logger)
    residences, services, distances_by_type, home_to_stop, stop_to_service = (
        compute_distances(layers, residences, config, logger)
    )
    layers["services"] = services

    service_types = list(config["essential_services"].keys())
    network_edges = walk_edges_for_display(layers["graph"])
    transit_by_type = transit_distances_by_type(
        distances_by_type, home_to_stop, stop_to_service, config
    )

    bands_seniors = config["quality_bands"]["seniors"]
    bands_population = config["quality_bands"]["population_total"]
    importance_seniors = config["importance_seniors"]
    importance_population = config["importance_population_total"]

    # Trois cartes S0, residences colorees par cote.
    s0_maps = [
        (
            distances_by_type,
            importance_seniors,
            bands_seniors,
            "carte_s0_marche_aines.html",
            False,
        ),
        (
            distances_by_type,
            importance_population,
            bands_population,
            "carte_s0_marche_population.html",
            False,
        ),
        (
            transit_by_type,
            importance_seniors,
            bands_seniors,
            "carte_s0_marche_transport_aines.html",
            True,
        ),
    ]
    for distances_all, importance, bands, file_name, with_transit in s0_maps:
        scored = scored_residences(residences, distances_all, importance, bands, config)
        s0_map(
            layers["study_zone"],
            layers["municipalities"],
            scored,
            service_types,
            network_edges,
            services,
            layers["stops"] if with_transit else None,
            layers["stations"] if with_transit else None,
            layers["lines"] if with_transit else None,
            layers["water"],
            config["visualization"],
            os.path.join(config["paths"]["outputs_maps"], file_name),
            logger,
        )

    # Couverture S0 par type et par population.
    summary = coverage_summary(residences, distances_by_type, transit_by_type, config)
    export_table(
        summary,
        os.path.join(config["paths"]["outputs_tables"], "s0_couverture.csv"),
        logger,
    )
    labels = config["visualization"]["service_labels"]
    thr_seniors = config["optimization"]["coverage_threshold_seniors_m"]
    thr_population = config["optimization"]["coverage_threshold_population_m"]
    seniors_walk = summary[
        (summary["population"] == "seniors")
        & (summary["mode"] == "marche")
        & (summary["threshold_m"] == thr_seniors)
    ]
    population_walk = summary[
        (summary["population"] == "population_total")
        & (summary["mode"] == "marche")
        & (summary["threshold_m"] == thr_population)
    ]
    s0_coverage_chart(
        seniors_walk,
        labels,
        "Couverture S0 des aines par type de service",
        os.path.join(config["paths"]["outputs_figures"], "s0_couverture_aines.png"),
        logger,
    )
    s0_coverage_chart(
        population_walk,
        labels,
        "Couverture S0 de la population generale par type de service",
        os.path.join(
            config["paths"]["outputs_figures"], "s0_couverture_population.png"
        ),
        logger,
    )

    # Effet de barriere de la riviere, faible et documente.
    barrier = barrier_analysis(layers, residences, services, config, logger)
    export_table(
        barrier,
        os.path.join(config["paths"]["outputs_tables"], "effet_barriere.csv"),
        logger,
    )

    # Optimisation S1 a pied, paniers mixtes, cartes et courbes de gain.
    candidates, gains, recommended = optimization_s1(
        layers, residences, distances_by_type, network_edges, config, logger
    )
    export_table(
        gains,
        os.path.join(config["paths"]["outputs_tables"], "gains_s1.csv"),
        logger,
    )
    gain_curve_chart(
        gains,
        os.path.join(config["paths"]["outputs_figures"], "courbe_gain.png"),
        logger,
    )
    if recommended is not None and len(recommended) > 0:
        recommended_export = recommended.copy()
        recommended_export["x"] = recommended_export.geometry.x.round(1)
        recommended_export["y"] = recommended_export.geometry.y.round(1)
        export_table(
            pd.DataFrame(recommended_export.drop(columns=["geometry", "icon"])),
            os.path.join(config["paths"]["outputs_tables"], "sites_recommandes.csv"),
            logger,
        )

    # Couches intermediaires verifiables dans QGIS.
    save_processed(residences, config, "residences", logger)
    save_processed(layers["stops"], config, "bus_stops", logger)
    save_processed(layers["stations"], config, "stations", logger)
    save_processed(areas, config, "dissemination_areas", logger)
    save_processed(candidates, config, "candidate_sites", logger)

    logger.info("Pipeline termine, sorties disponibles dans outputs")


if __name__ == "__main__":
    run_pipeline()
