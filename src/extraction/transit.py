"""Reseau de transport fixe exo, arrets d'autobus, gares et lignes de train.

Les arrets viennent du GTFS de la CITVR. Seules les lignes fixes sont retenues,
le service a la demande est exclu comme documente au README. Les espaces de tete
dans les coordonnees, releves a l'audit, sont nettoyes avant conversion. Toutes
les couches sortent dans le CRS cible.
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


def fixed_route_stop_ids(routes, trips, stop_times, fixed_route_types):
    """Retourne les identifiants d'arrets desservis par les lignes fixes.

    Le lien se fait de la ligne au voyage puis du voyage aux arrets, ce qui
    ecarte naturellement les arrets servis uniquement a la demande.
    """
    routes = routes.copy()
    routes["route_type"] = pd.to_numeric(routes["route_type"], errors="coerce")
    fixed_routes = routes[routes["route_type"].isin(fixed_route_types)]
    fixed_trips = trips[trips["route_id"].isin(fixed_routes["route_id"])]
    fixed_stop_times = stop_times[stop_times["trip_id"].isin(fixed_trips["trip_id"])]
    return set(fixed_stop_times["stop_id"].unique())


def load_bus_stops(config, logger=None):
    """Charge les arrets d'autobus du reseau fixe en points projetes."""
    transit = config["transit"]
    routes = pd.read_csv(_gtfs_path(config, "routes.txt"), dtype=str)
    trips = pd.read_csv(_gtfs_path(config, "trips.txt"), dtype=str)
    stop_times = pd.read_csv(
        _gtfs_path(config, "stop_times.txt"), dtype=str, usecols=["trip_id", "stop_id"]
    )
    stops = pd.read_csv(_gtfs_path(config, "stops.txt"), dtype=str)

    wanted_ids = fixed_route_stop_ids(
        routes, trips, stop_times, transit["fixed_route_types"]
    )
    stops = stops[stops["stop_id"].isin(wanted_ids)].copy()

    # Nettoyage des espaces de tete releves a l'audit avant conversion.
    latitude = pd.to_numeric(stops[transit["lat_field"]].str.strip(), errors="coerce")
    longitude = pd.to_numeric(stops[transit["lon_field"]].str.strip(), errors="coerce")
    stops = stops[latitude.notna() & longitude.notna()].copy()

    stops_gdf = gpd.GeoDataFrame(
        stops[["stop_id", "stop_name"]],
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
