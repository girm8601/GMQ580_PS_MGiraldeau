"""Point d'entree unique du projet, il orchestre le pipeline sans traiter.

main.py enchaine les etapes dans l'ordre du schema du README et delegue tout le
traitement aux modules de src. Le pipeline suit trois volets, le diagnostic d'equite, la
validation des pistes ecartees et le levier qui recommande les meilleurs secteurs
d'adresses et de terrains. Un rapport PDF rassemble ensuite les figures et les tableaux.
Chaque etape est une fonction nommee d'un module de responsabilite, extraction,
traitement, validation, resultats et visualisation. Lancement, python main.py, apres
avoir regenere les couches OSM avec download_data.py.
"""

from __future__ import annotations

import os
import sys

from config_loader import ConfigError, load_config
from src import _gdal_fix  # noqa: F401  (corrige le chargement de GDAL, comme au TD2)
from src.extraction.layers import load_all_layers
from src.io import save_layer
from src.logger import setup_logger
from src.processing.accessibility import compute_distances, scored_residences
from src.processing.coverage import coverage_summary
from src.processing.demand import prepare_demand
from src.processing.sectors import best_sectors
from src.processing.service_addition import service_addition_check
from src.processing.site_scoring import score_development_sites
from src.processing.transit_access import transit_distances_by_type
from src.processing.transit_routes import prepare_route_access
from src.results.metrics import (
    export_table,
    population_comparison_table,
    sector_table,
    service_addition_effect_table,
)
from src.results.report import build_report
from src.validation.audit import AuditError, audit_all_layers
from src.validation.bridges import barrier_analysis
from src.visualization.charts import coverage_chart, gain_curve_chart
from src.visualization.maps import (
    lever_map,
    ordered_service_types,
    walk_edges_for_display,
)


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
    # Le sommaire n'est pas imprime tel quel, il porte la comparaison a seuil commun que la
    # conclusion du diagnostic cite.
    tables["coverage"] = summary

    comparison = population_comparison_table(summary, config)
    export_table(
        comparison,
        os.path.join(paths["outputs_tables"], paths["table_files"]["comparison"]),
        logger,
    )
    tables["comparison"] = comparison


def render_validation(
    layers, residences, snapped_by_type, addition, config, logger, figures, tables
):
    """Volet validation, gain de l'assortiment, borne du meilleur ajout et effet de barriere."""
    paths = config["paths"]
    if addition is not None:
        gains, bound = addition
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

        export_table(
            bound,
            os.path.join(
                paths["outputs_tables"], paths["table_files"]["addition_bound"]
            ),
            logger,
        )
        tables["addition_bound"] = bound

    barrier, crossings = barrier_analysis(
        layers, residences, snapped_by_type, config, logger
    )
    export_table(
        crossings,
        os.path.join(paths["outputs_tables"], paths["table_files"]["crossing_bridges"]),
        logger,
    )
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
        config["target_crs"],
        os.path.join(config["paths"]["outputs_maps"], map_file),
        stop_field=config["transit"]["gtfs_fields"]["stop_name"],
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


def compute_transit_access(
    layers, residences, distances_by_type, snapped_by_type, config, logger
):
    """Distances effectives des deux groupes avec le transport, un trajet sans transfert."""
    route_access = prepare_route_access(layers, snapped_by_type, config, logger)
    snapped_residences = dict(
        zip(residences["residence_id"], zip(residences["node"], residences["snap_m"]))
    )
    transit = config["transit"]
    seniors = transit_distances_by_type(
        distances_by_type,
        snapped_residences,
        *route_access,
        transit["max_total_walk_seniors_m"],
    )
    rest = transit_distances_by_type(
        distances_by_type,
        snapped_residences,
        *route_access,
        transit["max_total_walk_rest_m"],
    )
    return route_access, seniors, rest


def run_pipeline():
    """Enchaine les etapes du pipeline, diagnostic, validation, levier puis rapport."""
    config = load_config()
    logger = setup_logger(config["paths"]["log_file"], config["logging"]["level"])
    logger.info("Demarrage du pipeline")

    layers = load_all_layers(config, logger)
    audit_all_layers(layers, config, logger)

    areas, residences = prepare_demand(layers, config, logger)
    residences, services, distances_by_type, snapped_by_type = compute_distances(
        layers, residences, config, logger
    )
    layers["services"] = services

    route_access, transit_seniors, transit_rest = compute_transit_access(
        layers, residences, distances_by_type, snapped_by_type, config, logger
    )

    figures = {}
    tables = {}
    addition = service_addition_check(
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
    render_validation(
        layers, residences, snapped_by_type, addition, config, logger, figures, tables
    )

    dev_scored = score_development_sites(layers, services, route_access, config, logger)
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

    save_layer(residences, config, "residences", logger)
    save_layer(layers["stops"], config, "bus_stops", logger)
    save_layer(layers["stations"], config, "stations", logger)
    save_layer(areas, config, "dissemination_areas", logger)
    if dev_scored is not None:
        save_layer(dev_scored["walk"], config, "development_sites", logger)

    logger.info("Pipeline termine, sorties disponibles dans outputs")


def main():
    """Lance le pipeline et transforme toute erreur en message clair.

    Une source absente, une configuration incomplete ou une regle d'audit en echec sont
    des situations previsibles. Elles doivent donner une consigne utile et un code de
    sortie non nul, jamais une trace Python brute. Le dernier filet attrape tout le reste
    pour la meme raison, le journal du pipeline garde de son cote le detail.
    """
    try:
        run_pipeline()
    except ConfigError as error:
        print(f"Configuration invalide, {error}", file=sys.stderr)
        return 1
    except AuditError as error:
        print(f"Audit des donnees en echec, {error}", file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(
            f"Donnee source introuvable, {error}. Lancer d'abord python download_data.py",
            file=sys.stderr,
        )
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"Echec inattendu du pipeline, {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
