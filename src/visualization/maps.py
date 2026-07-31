"""Cartes interactives du projet avec folium.

Le projet produit les deux cartes du levier, a la marche et au transport. Ce module assemble
la carte, il delegue les couches a map_layers.py, l'habillage a map_layout.py et les
symboles a map_symbols.py.

Chaque residence est un point colore selon sa cote qualitative, regroupe en clusters comme
dans GMQ210. Un cluster prend la couleur de la cote moyenne des points qu'il contient. Les
services essentiels sont des epingles, les arrets et les gares des bulles rondes. Les
meilleurs secteurs d'adresses et de terrains ressortent en polygones remplis colores par
leur cote moyenne, avec un carre pictogramme au centroide. La carte du transport ajoute les
arrets, les gares et les lignes, l'appelant passe alors ces couches, sinon None.
"""

from __future__ import annotations

import os

import folium
import geopandas as gpd

from src.visualization.map_layers import (
    add_bubble_points,
    add_municipal_limits,
    add_residence_points,
    add_river,
    add_sectors,
    add_service_markers,
    add_study_outline,
    add_train_lines,
    add_walk_network,
    to_display,
)
from src.visualization.map_layout import add_legend, add_scale, add_title


def walk_edges_for_display(graph, config):
    """Reseau pietonnier simplifie pour l'affichage des cartes.

    Le graphe est oriente, chaque rue porte donc deux liens opposes. Un seul des deux est
    garde pour ne pas dessiner chaque rue en double. La tolerance de simplification vient
    de la configuration.
    """
    import osmnx as ox

    edges = ox.graph_to_gdfs(graph, nodes=False).reset_index()
    if {"u", "v"}.issubset(edges.columns):
        edges = edges[edges["u"] < edges["v"]]
    edges = edges[["geometry"]].copy()
    tolerance = config["visualization"]["map_network_simplify_m"]
    edges["geometry"] = edges.geometry.simplify(tolerance)
    return edges


def ordered_service_types(service_types, importance):
    """Types de service tries du plus important au moins important pour l'affichage.

    Utilise pour lister les distances dans l'infobulle d'une residence dans le
    meme ordre que l'importance des aines qui a servi a calculer sa cote.
    """
    return sorted(service_types, key=lambda t: -importance.get(t, 0.0))


def _save(web_map, path, logger=None):
    """Ecrit la carte HTML et cree le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    web_map.save(path)
    if logger is not None:
        logger.info("Carte exportee, %s", path)


def _base_map(zone_gdf, vc, geographic_crs):
    """Cree la carte de base centree sur la zone d'etude, avec Font Awesome charge.

    Le centre est calcule dans le CRS projete du projet puis ramene en degres, une moyenne
    de degres ne donnerait pas le vrai centre. L'echelle de folium melangerait metres et
    pieds, elle est donc ajoutee separement par add_scale.
    """
    center = to_display(
        gpd.GeoSeries([zone_gdf.geometry.union_all()], crs=zone_gdf.crs).centroid,
        geographic_crs,
    ).iloc[0]
    web_map = folium.Map(
        location=[center.y, center.x],
        zoom_start=vc["map_zoom_start"],
        tiles=vc["map_tiles"],
        control_scale=False,
    )
    web_map.get_root().header.add_child(
        folium.Element(f'<link rel="stylesheet" href="{vc["font_awesome_cdn"]}">')
    )
    return web_map


def _add_base_layers(
    web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc, geographic_crs
):
    """Ajoute la riviere, le reseau, les limites municipales et la zone d'etude."""
    names = vc["layer_names"]
    add_river(
        web_map,
        water_gdf,
        geographic_crs,
        names["river"],
        vc["color_river"],
        vc["style_river_weight"],
        vc["style_river_fill_opacity"],
    )
    add_walk_network(
        web_map,
        network_edges,
        geographic_crs,
        names["walk_network"],
        vc["color_network_casing"],
        vc["color_network_fill"],
        vc["style_network_casing_weight"],
        vc["style_network_casing_opacity"],
        vc["style_network_fill_weight"],
        vc["style_network_fill_opacity"],
    )
    add_municipal_limits(
        web_map,
        municipalities_gdf,
        geographic_crs,
        names["municipal_limits"],
        vc["color_municipal_limits"],
        vc["style_municipal_limits_weight"],
    )
    add_study_outline(
        web_map,
        zone_gdf,
        geographic_crs,
        names["study_outline"],
        vc["color_study_outline"],
        vc["style_study_outline_weight"],
    )


def lever_map(
    zone_gdf,
    municipalities_gdf,
    residences_gdf,
    service_types,
    network_edges,
    services_gdf,
    stops_gdf,
    stations_gdf,
    lines_gdf,
    water_gdf,
    address_sectors,
    site_sectors,
    visual_config,
    geographic_crs,
    target_crs,
    path,
    stop_field,
    station_field,
    line_field,
    logger=None,
):
    """Carte du levier, residences en clusters plus les meilleurs secteurs mis en evidence.

    Elle reprend tous les elements de la carte d'accessibilite, residences colorees par cote
    et regroupees en clusters, reseau, services, riviere et limites. La carte transport
    ajoute les arrets, les gares et les lignes, l'appelant passe alors ces couches, sinon
    None. La meilleure aire de diffusion d'adresses existantes et la meilleure aire ou
    implanter des logements de chaque municipalite ressortent en polygones remplis colores
    par leur cote moyenne, avec un carre pictogramme au centroide. Le titre, la legende, la
    barre d'echelle et la note de source completent la carte.
    """
    vc = visual_config
    names = vc["layer_names"]
    icons = vc["service_icons"]
    icon_ratio = vc["size_icon_ratio"]
    offset = vc["size_sector_marker_offset"]
    with_transit = stops_gdf is not None
    web_map = _base_map(zone_gdf, vc, geographic_crs)
    _add_base_layers(
        web_map,
        zone_gdf,
        municipalities_gdf,
        network_edges,
        water_gdf,
        vc,
        geographic_crs,
    )
    add_train_lines(
        web_map,
        lines_gdf,
        geographic_crs,
        names["train_lines"],
        vc["color_stations"],
        vc["style_train_line_weight"],
        vc["style_train_line_dash"],
        line_field,
    )

    add_residence_points(web_map, residences_gdf, service_types, vc, geographic_crs)

    add_service_markers(
        web_map,
        services_gdf,
        geographic_crs,
        names["services"],
        lambda row: icons.get(row["service_type"], vc["icon_service_default"]),
        vc["color_services"],
        vc["service_labels"],
        vc["size_service_marker"],
        icon_ratio,
        vc["size_popup_service"],
    )
    add_bubble_points(
        web_map,
        stops_gdf,
        geographic_crs,
        names["stops"],
        vc["icon_stop"],
        vc["color_stops"],
        stop_field,
        vc["size_stop_bubble"],
        icon_ratio,
    )
    add_bubble_points(
        web_map,
        stations_gdf,
        geographic_crs,
        names["stations"],
        vc["icon_station"],
        vc["color_stations"],
        station_field,
        vc["size_station_bubble"],
        icon_ratio,
    )
    add_sectors(
        web_map,
        address_sectors,
        geographic_crs,
        names["address_sectors"],
        vc["icon_best_address"],
        offset,
        vc,
    )
    add_sectors(
        web_map,
        site_sectors,
        geographic_crs,
        names["site_sectors"],
        vc["icon_new_residence"],
        -offset,
        vc,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    mode_key = "map_subtitle_transit" if with_transit else "map_subtitle_walk"
    add_title(web_map, vc["map_title"], vc[mode_key], vc)
    add_legend(
        web_map,
        vc,
        vc["map_source_note"].format(crs=target_crs),
        with_transit,
        network_edges is not None and len(network_edges) > 0,
        water_gdf is not None and len(water_gdf) > 0,
    )
    add_scale(web_map, vc)
    _save(web_map, path, logger)
