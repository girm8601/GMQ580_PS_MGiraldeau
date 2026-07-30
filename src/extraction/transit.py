"""Reseau de transport fixe exo, arrets d'autobus, gares et lignes de train.

Les arrets viennent du GTFS de la CITVR. Seules les lignes fixes sont retenues,
le service a la demande est exclu comme documente au README. Les espaces de tete
dans les coordonnees, releves a l'audit, sont nettoyes avant conversion. Toutes
les couches sortent dans le CRS cible.

Ce module lit aussi la composition des lignes, quels arrets chaque ligne dessert.
L'acces par le transport se mesure en effet sur une seule ligne, sans transfert, il
faut donc savoir quels arrets se joignent entre eux.
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd

from src.io import reproject


def _gtfs_path(config, file_name):
    """Chemin d'un fichier du dossier GTFS declare dans la configuration."""
    return os.path.join(
        config["paths"]["data_raw"], config["paths"]["manual_files"]["gtfs"], file_name
    )


def stops_by_fixed_route(routes, trips, stop_times, fixed_route_types, fields):
    """Retourne les arrets desservis par chaque ligne fixe.

    Le lien se fait de la ligne au voyage puis du voyage aux arrets, ce qui ecarte
    naturellement les arrets servis uniquement a la demande. Retourne un dictionnaire
    identifiant de ligne vers liste d'identifiants d'arrets, sans doublon.
    """
    route_field = fields["route_id"]
    trip_field = fields["trip_id"]
    stop_field = fields["stop_id"]

    routes = routes.copy()
    routes[fields["route_type"]] = pd.to_numeric(
        routes[fields["route_type"]], errors="coerce"
    )
    fixed_routes = routes[routes[fields["route_type"]].isin(fixed_route_types)]
    fixed_trips = trips[trips[route_field].isin(fixed_routes[route_field])]
    served = stop_times.merge(
        fixed_trips[[trip_field, route_field]], on=trip_field, how="inner"
    )
    return {
        route_id: list(dict.fromkeys(group[stop_field]))
        for route_id, group in served.groupby(route_field)
    }


def fixed_route_stop_ids(route_stops):
    """Retourne l'ensemble des identifiants d'arrets desservis par les lignes fixes."""
    return {stop_id for stop_ids in route_stops.values() for stop_id in stop_ids}


def _read_gtfs_tables(config):
    """Lit les quatre tables GTFS utiles, tout en texte pour garder les zeros de tete."""
    fields = config["transit"]["gtfs_fields"]
    return (
        pd.read_csv(_gtfs_path(config, "routes.txt"), dtype=str),
        pd.read_csv(_gtfs_path(config, "trips.txt"), dtype=str),
        pd.read_csv(
            _gtfs_path(config, "stop_times.txt"),
            dtype=str,
            usecols=[fields["trip_id"], fields["stop_id"]],
        ),
        pd.read_csv(_gtfs_path(config, "stops.txt"), dtype=str),
    )


def load_route_stops(config, logger=None):
    """Charge la composition des lignes fixes, quels arrets chaque ligne dessert."""
    transit = config["transit"]
    routes, trips, stop_times, _ = _read_gtfs_tables(config)
    route_stops = stops_by_fixed_route(
        routes,
        trips,
        stop_times,
        transit["fixed_route_types"],
        transit["gtfs_fields"],
    )
    if logger is not None:
        logger.info("Lignes fixes lues dans le GTFS, %d ligne(s)", len(route_stops))
    return route_stops


def load_bus_stops(config, logger=None):
    """Charge les arrets d'autobus du reseau fixe en points projetes."""
    transit = config["transit"]
    fields = transit["gtfs_fields"]
    routes, trips, stop_times, stops = _read_gtfs_tables(config)

    route_stops = stops_by_fixed_route(
        routes, trips, stop_times, transit["fixed_route_types"], fields
    )
    wanted_ids = fixed_route_stop_ids(route_stops)
    stops = stops[stops[fields["stop_id"]].isin(wanted_ids)].copy()

    # Nettoyage des espaces de tete releves a l'audit avant conversion.
    latitude = pd.to_numeric(stops[fields["stop_lat"]].str.strip(), errors="coerce")
    longitude = pd.to_numeric(stops[fields["stop_lon"]].str.strip(), errors="coerce")
    stops = stops[latitude.notna() & longitude.notna()].copy()

    stops_gdf = gpd.GeoDataFrame(
        stops[[fields["stop_id"], fields["stop_name"]]],
        geometry=gpd.points_from_xy(longitude[stops.index], latitude[stops.index]),
        crs=config["source_crs"]["transit_exo"],
    )
    if logger is not None:
        logger.info("Arrets du reseau fixe charges, %d arrets", len(stops_gdf))
    return reproject(stops_gdf, config["target_crs"])


def load_train_stations(config, logger=None):
    """Charge les gares pertinentes de la zone, une par rive."""
    path = os.path.join(
        config["paths"]["data_raw"], config["paths"]["manual_files"]["train_stations"]
    )
    stations = gpd.read_file(path)
    station_field = config["transit"]["station_name_field"]
    stations = stations[
        stations[station_field].isin(config["transit"]["relevant_stations"])
    ].copy()
    if logger is not None:
        logger.info("Gares retenues, %d gares", len(stations))
    return reproject(stations, config["target_crs"])


def load_train_lines(config, logger=None):
    """Charge les lignes de train sans doublon, pour le contexte cartographique."""
    path = os.path.join(
        config["paths"]["data_raw"], config["paths"]["manual_files"]["train_lines"]
    )
    lines = gpd.read_file(path)
    before = len(lines)
    dedup_fields = [
        config["transit"]["line_id_field"],
        config["transit"]["line_name_field"],
    ]
    lines = lines.drop_duplicates(subset=dedup_fields).copy()
    if logger is not None and len(lines) < before:
        logger.info("Doublon de ligne retire, %d lignes conservees", len(lines))
    return reproject(lines, config["target_crs"])
