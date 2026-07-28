"""Point d'entree unique du projet, il orchestre le pipeline sans traiter.

main.py enchaine les etapes dans l'ordre du schema du README et delegue tout le
traitement aux modules de src. Le pipeline suit trois volets, le diagnostic d'equite, la
validation des pistes ecartees et le levier qui recommande les meilleures adresses et les
sites a implanter. Un rapport PDF rassemble ensuite les figures et les tableaux. Chaque
etape est une fonction nommee d'un module de responsabilite, extraction, traitement,
validation, resultats et visualisation. Lancement, python main.py, apres avoir regenere
les couches OSM avec download_data.py.
"""

from __future__ import annotations

import os

import geopandas as gpd

from config_loader import load_config
from src import _gdal_fix  # noqa: F401  (corrige le chargement de GDAL, comme au TD2)
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
from src.extraction.transit import load_bus_stops, load_train_lines, load_train_stations
from src.logger import setup_logger
from src.processing.accessibility import compute_distances, scored_residences
from src.processing.coverage import coverage_summary
from src.processing.demand import prepare_demand
from src.processing.scenarios import score_development_sites, service_addition_check
from src.processing.sectors import best_sectors
from src.processing.study_area import build_zone
from src.processing.transit_access import transit_distances_by_type
from src.results.metrics import (
    export_table,
    population_comparison_table,
    sector_table,
    service_addition_effect_table,
)
from src.results.report import build_report
from src.validation.audit import fix_invalid_geometries, run_audit
from src.validation.bridges import barrier_analysis
from src.visualization.charts import coverage_chart, gain_curve_chart
from src.visualization.maps import lever_map, ordered_service_types


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


def walk_edges_for_display(graph, config):
    """Reseau pietonnier simplifie pour l'affichage des cartes."""
    import osmnx as ox

    edges = ox.graph_to_gdfs(graph, nodes=False).reset_index()
    if {"u", "v"}.issubset(edges.columns):
        edges = edges[edges["u"] < edges["v"]]
    edges = edges[["geometry"]].copy()
    tolerance = config["visualization"]["map_network_simplify_m"]
    edges["geometry"] = edges.geometry.simplify(tolerance)
    return edges


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


def audit_all_layers(layers, config, logger):
    """Audite toutes les couches spatiales avant le moindre traitement."""
    crs = config["target_crs"]
    zone = layers["study_zone"]
    name_field = config["study_area"]["municipality_name_field"]
    join_field = config["vulnerability"]["ad_join_field"]
    station_field = config["transit"]["station_name_field"]
    line_field = config["transit"]["line_name_field"]
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
        {"gdf": layers["stops"], "name": "bus_stops", "crs": crs, "zone": zone},
        {
            "gdf": layers["stations"],
            "name": "train_stations",
            "crs": crs,
            "required_fields": [station_field],
        },
        {
            "gdf": layers["lines"],
            "name": "train_lines",
            "crs": crs,
            "required_fields": [line_field],
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
    for key in ("commercial", "development", "residential"):
        if layers.get(key) is not None:
            entries.append({"gdf": layers[key], "name": key, "crs": crs, "zone": zone})
    run_audit(entries, config["paths"]["audit_report"], logger)


def render_diagnostic(
    residences,
    distances_by_type,
    transit_seniors,
    transit_rest,
    config,
    logger,
    figures,
    tables,
):
    """Volet diagnostic, figure de couverture des deux groupes et tableaux d'equite."""
    paths = config["paths"]
    summary = coverage_summary(
        residences, distances_by_type, transit_seniors, transit_rest, config
    )
    export_table(
        summary,
        os.path.join(paths["outputs_tables"], paths["table_files"]["coverage"]),
        logger,
    )
    coverage_path = os.path.join(
        paths["outputs_figures"], paths["figure_files"]["coverage"]
    )
    coverage_chart(summary, config, coverage_path, logger)
    figures["coverage"] = coverage_path

    comparison = population_comparison_table(summary, config)
    export_table(
        comparison,
        os.path.join(paths["outputs_tables"], paths["table_files"]["comparison"]),
        logger,
    )
    tables["comparison"] = comparison


def render_validation(layers, residences, gains, config, logger, figures, tables):
    """Volet validation, figure de gain, effet de chaque ajout et tableau de barriere."""
    paths = config["paths"]
    if gains is not None:
        gain_path = os.path.join(
            paths["outputs_figures"], paths["figure_files"]["gain"]
        )
        gain_curve_chart(gains, config, gain_path, logger)
        figures["gain"] = gain_path

        effect = service_addition_effect_table(gains)
        export_table(
            effect,
            os.path.join(
                paths["outputs_tables"], paths["table_files"]["service_addition"]
            ),
            logger,
        )
        tables["service_addition"] = effect

    barrier = barrier_analysis(layers, residences, layers["services"], config, logger)
    export_table(
        barrier,
        os.path.join(paths["outputs_tables"], paths["table_files"]["barrier"]),
        logger,
    )
    tables["barrier"] = barrier


def _render_lever_map(
    layers,
    scored,
    ordered,
    network_edges,
    address_sectors,
    site_sectors,
    config,
    map_file,
    with_transit,
    logger,
):
    """Trace une carte du levier, residences en clusters plus les meilleurs secteurs."""
    lever_map(
        layers["study_zone"],
        layers["municipalities"],
        scored,
        ordered,
        network_edges,
        layers["services"],
        layers["stops"] if with_transit else None,
        layers["stations"] if with_transit else None,
        layers["lines"] if with_transit else None,
        layers["water"],
        address_sectors,
        site_sectors,
        config["visualization"],
        config["geographic_crs"],
        os.path.join(config["paths"]["outputs_maps"], map_file),
        station_field=config["transit"]["station_name_field"],
        line_field=config["transit"]["line_name_field"],
        logger=logger,
    )


def render_lever(
    layers,
    residences,
    areas,
    distances_by_type,
    transit_seniors,
    dev_scored,
    config,
    logger,
    tables,
):
    """Volet levier, un tableau de secteurs et une carte par mode de deplacement."""
    paths = config["paths"]
    municipalities = layers["municipalities"]
    precision = config["export"]["coordinate_precision"]
    geographic_crs = config["geographic_crs"]
    importance = config["importance_seniors"]
    bands = config["quality_bands"]["seniors"]
    service_types = list(config["essential_services"].keys())
    ordered = ordered_service_types(service_types, importance)
    network_edges = walk_edges_for_display(layers["graph"], config)

    modes = [
        (distances_by_type, "recommendation_walk", "lever_walk", False),
        (transit_seniors, "recommendation_transit", "lever_transit", True),
    ]
    for distances, table_key, map_key, with_transit in modes:
        mode = "transit" if with_transit else "walk"
        scored = scored_residences(residences, distances, importance, bands, config)
        address_sectors = best_sectors(scored, areas, municipalities, config, logger)
        site_sectors = (
            best_sectors(dev_scored[mode], areas, municipalities, config, logger)
            if dev_scored is not None
            else None
        )
        table = sector_table(address_sectors, site_sectors, geographic_crs, precision)
        export_table(
            table,
            os.path.join(paths["outputs_tables"], paths["table_files"][table_key]),
            logger,
        )
        tables[table_key] = table

        _render_lever_map(
            layers,
            scored,
            ordered,
            network_edges,
            address_sectors,
            site_sectors,
            config,
            paths["map_files"][map_key],
            with_transit,
            logger,
        )


def run_pipeline():
    """Enchaine les etapes du pipeline, diagnostic, validation, levier puis rapport."""
    config = load_config()
    logger = setup_logger(config["paths"]["log_file"], config["logging"]["level"])
    logger.info("Demarrage du pipeline")

    layers = load_all_layers(config, logger)
    audit_all_layers(layers, config, logger)

    areas, residences = prepare_demand(layers, config, logger)
    (
        residences,
        services,
        distances_by_type,
        home_to_stop,
        stop_to_service,
        transit_reached,
    ) = compute_distances(layers, residences, config, logger)
    layers["services"] = services

    transit_seniors = transit_distances_by_type(
        distances_by_type,
        home_to_stop,
        stop_to_service,
        config["transit"]["max_stop_distance_seniors_m"],
    )
    transit_rest = transit_distances_by_type(
        distances_by_type,
        home_to_stop,
        stop_to_service,
        config["transit"]["max_stop_distance_rest_m"],
    )

    figures = {}
    tables = {}
    gains = service_addition_check(
        layers, residences, distances_by_type, config, logger
    )
    render_diagnostic(
        residences,
        distances_by_type,
        transit_seniors,
        transit_rest,
        config,
        logger,
        figures,
        tables,
    )
    render_validation(layers, residences, gains, config, logger, figures, tables)

    dev_scored = score_development_sites(
        layers, services, transit_reached, config, logger
    )
    render_lever(
        layers,
        residences,
        areas,
        distances_by_type,
        transit_seniors,
        dev_scored,
        config,
        logger,
        tables,
    )

    build_report(config, figures, tables, logger)

    save_processed(residences, config, "residences", logger)
    save_processed(layers["stops"], config, "bus_stops", logger)
    save_processed(layers["stations"], config, "stations", logger)
    save_processed(areas, config, "dissemination_areas", logger)
    if dev_scored is not None:
        save_processed(dev_scored["walk"], config, "development_sites", logger)

    logger.info("Pipeline termine, sorties disponibles dans outputs")


if __name__ == "__main__":
    run_pipeline()
