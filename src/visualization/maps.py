"""Cartes interactives du projet avec folium.

Le projet produit les deux cartes du levier, a la marche et au transport. Chaque
residence est un point colore selon sa cote qualitative, regroupe en clusters, comme dans
GMQ210. Un cluster prend la couleur de la cote moyenne des points qu'il contient. Les
services essentiels existants sont des reperes en forme d'epingle. Les arrets d'autobus et
les gares sont des bulles rondes. Les meilleurs secteurs d'adresses et de sites ressortent
en polygones remplis colores par leur cote moyenne, avec un carre pictogramme au centroide.
Les limites sont tracees en noir. Toutes les couleurs, tailles, epaisseurs et noms de
couches viennent de la section visualization de config.yaml.
"""

from __future__ import annotations

import json
import os

import folium
from folium.plugins import MarkerCluster


def _to_display(gdf, geographic_crs):
    """Reprojette une couche vers le CRS d'affichage web."""
    return gdf.to_crs(geographic_crs)


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
    """Cree la carte de base centree sur la zone d'etude, avec Font Awesome charge."""
    zone = _to_display(zone_gdf, geographic_crs)
    center = zone.geometry.union_all().centroid
    web_map = folium.Map(
        location=[center.y, center.x],
        zoom_start=vc["map_zoom_start"],
        tiles=vc["map_tiles"],
    )
    web_map.get_root().header.add_child(
        folium.Element(f'<link rel="stylesheet" href="{vc["font_awesome_cdn"]}">')
    )
    return web_map


def _add_study_outline(web_map, zone_gdf, geographic_crs, group_name, color, weight):
    """Ajoute le trait noir qui delimite la zone d'etude."""
    folium.GeoJson(
        _to_display(zone_gdf[["geometry"]], geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": weight,
        },
    ).add_to(web_map)


def _add_municipal_limits(
    web_map, municipalities_gdf, geographic_crs, group_name, color, weight
):
    """Ajoute les limites municipales en trait noir fin, sans nom de municipalite."""
    if municipalities_gdf is None or len(municipalities_gdf) == 0:
        return
    folium.GeoJson(
        _to_display(municipalities_gdf[["geometry"]], geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": weight,
        },
    ).add_to(web_map)


def _add_river(
    web_map, water_gdf, geographic_crs, group_name, color, weight, fill_opacity
):
    """Ajoute la riviere au dessus du reseau mais sous les points."""
    if water_gdf is None or len(water_gdf) == 0:
        return
    folium.GeoJson(
        _to_display(water_gdf[["geometry"]], geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "fillColor": color,
            "color": color,
            "weight": weight,
            "fillOpacity": fill_opacity,
        },
    ).add_to(web_map)


def _add_walk_network(
    web_map,
    edges_gdf,
    geographic_crs,
    group_name,
    casing_color,
    fill_color,
    casing_weight,
    casing_opacity,
    fill_weight,
    fill_opacity,
):
    """Ajoute le reseau pietonnier, contour gris et remplissage blanc fin."""
    if edges_gdf is None or len(edges_gdf) == 0:
        return
    edges_json = _to_display(edges_gdf[["geometry"]], geographic_crs).to_json()
    group = folium.FeatureGroup(name=group_name)
    folium.GeoJson(
        edges_json,
        style_function=lambda feature: {
            "color": casing_color,
            "weight": casing_weight,
            "opacity": casing_opacity,
        },
    ).add_to(group)
    folium.GeoJson(
        edges_json,
        style_function=lambda feature: {
            "color": fill_color,
            "weight": fill_weight,
            "opacity": fill_opacity,
        },
    ).add_to(group)
    group.add_to(web_map)


def _add_train_lines(
    web_map,
    lines_gdf,
    geographic_crs,
    group_name,
    color,
    weight,
    dash_array,
    name_field,
):
    """Ajoute les lignes de train en pointille noir, contexte cartographique."""
    if lines_gdf is None or len(lines_gdf) == 0:
        return
    lines_display = lines_gdf[[name_field, "geometry"]]
    folium.GeoJson(
        _to_display(lines_display, geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "color": color,
            "weight": weight,
            "dashArray": dash_array,
        },
    ).add_to(web_map)


def _bubble(icon_class, bg_color, size_px, icon_ratio):
    """Bulle ronde coloree avec un pictogramme blanc, pour les arrets et gares."""
    glyph_size = int(size_px * icon_ratio)
    html = (
        f'<div style="width:{size_px}px;height:{size_px}px;background:{bg_color};'
        f"border:1px solid #ffffff;border-radius:50%;display:flex;"
        f"align-items:center;justify-content:center;"
        f'box-shadow:0 0 2px rgba(0,0,0,0.4);">'
        f'<i class="fa-solid {icon_class}" '
        f'style="color:#ffffff;font-size:{glyph_size}px;"></i></div>'
    )
    return folium.DivIcon(
        html=html,
        icon_size=(size_px, size_px),
        icon_anchor=(size_px // 2, size_px // 2),
    )


def _pin(icon_class, color, size_px, icon_ratio):
    """Repere en forme d'epingle avec un pictogramme blanc, pour les services."""
    glyph_size = int(size_px * icon_ratio)
    html = (
        f'<div style="width:{size_px}px;height:{size_px}px;background:{color};'
        f"border:1px solid #ffffff;border-radius:50% 50% 50% 0;"
        f"transform:rotate(-45deg);box-shadow:0 0 2px rgba(0,0,0,0.4);"
        f'display:flex;align-items:center;justify-content:center;">'
        f'<i class="fa-solid {icon_class}" '
        f'style="color:#ffffff;font-size:{glyph_size}px;transform:rotate(45deg);"></i></div>'
    )
    return folium.DivIcon(
        html=html,
        icon_size=(size_px, size_px),
        icon_anchor=(size_px // 2, size_px),
    )


def _add_bubble_points(
    web_map,
    gdf,
    geographic_crs,
    group_name,
    icon_class,
    color,
    name_field,
    size_px,
    icon_ratio,
):
    """Ajoute les arrets ou les gares en bulle coloree avec infobulle."""
    if gdf is None or len(gdf) == 0:
        return
    group = folium.FeatureGroup(name=group_name)
    for _, row in _to_display(gdf, geographic_crs).iterrows():
        name = str(row.get(name_field, "") or "")
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=_bubble(icon_class, color, size_px, icon_ratio),
            tooltip=name or group_name,
        ).add_to(group)
    group.add_to(web_map)


def _add_service_markers(
    web_map,
    gdf,
    geographic_crs,
    group_name,
    icon_for_row,
    color,
    service_labels,
    size_px,
    icon_ratio,
    popup_width,
):
    """Ajoute les services essentiels en reperes colores avec infobulle.

    Un clic affiche le libelle du type de service et le nom de l'etablissement, comme dans
    GMQ210.
    """
    if gdf is None or len(gdf) == 0:
        return
    group = folium.FeatureGroup(name=group_name)
    for _, row in _to_display(gdf, geographic_crs).iterrows():
        service_type = row.get("service_type")
        label = service_labels.get(service_type, service_type)
        detail = str(row.get("name", "") or "")
        popup_html = f"<b>{label}</b><br>{detail}" if detail else f"<b>{label}</b>"
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=_pin(icon_for_row(row), color, size_px, icon_ratio),
            tooltip=label,
            popup=folium.Popup(popup_html, max_width=popup_width),
        ).add_to(group)
    group.add_to(web_map)


def _square(icon_class, color, size_px, icon_ratio, offset_px):
    """Repere carre colore avec un pictogramme blanc, pour les elements retenus.

    offset_px decale le carre a l'horizontale. Les secteurs d'adresses et de logement
    tombent parfois sur la meme aire de diffusion, un decalage oppose garde alors les deux
    pictogrammes visibles cote a cote.
    """
    glyph_size = int(size_px * icon_ratio)
    html = (
        f'<div style="width:{size_px}px;height:{size_px}px;background:{color};'
        f"border:2px solid #ffffff;border-radius:15%;display:flex;"
        f"align-items:center;justify-content:center;"
        f'box-shadow:0 0 3px rgba(0,0,0,0.5);">'
        f'<i class="fa-solid {icon_class}" '
        f'style="color:#ffffff;font-size:{glyph_size}px;"></i></div>'
    )
    return folium.DivIcon(
        html=html,
        icon_size=(size_px, size_px),
        icon_anchor=(size_px // 2 + offset_px, size_px // 2),
    )


def _add_sectors(
    web_map, sectors_gdf, geographic_crs, group_name, icon_class, offset_px, vc
):
    """Ajoute des secteurs, polygone rempli colore par cote moyenne plus un carre au centroide.

    Chaque secteur est la meilleure aire de diffusion d'une municipalite. Le polygone et le
    carre prennent la couleur de la cote qualitative moyenne du secteur. Un clic affiche la
    ville, l'aire, la cote moyenne sur 100, la cote qualitative et le nombre de points.
    """
    if sectors_gdf is None or len(sectors_gdf) == 0:
        return
    quality_colors = vc["quality_colors"]
    default_color = vc["color_residence_default"]
    group = folium.FeatureGroup(name=group_name)
    display = _to_display(sectors_gdf, geographic_crs)
    folium.GeoJson(
        display[["mean_quality", "geometry"]].to_json(),
        style_function=lambda feature: {
            "fillColor": quality_colors.get(
                feature["properties"]["mean_quality"], default_color
            ),
            "color": quality_colors.get(
                feature["properties"]["mean_quality"], default_color
            ),
            "weight": vc["style_sector_outline_weight"],
            "fillOpacity": vc["style_sector_fill_opacity"],
        },
    ).add_to(group)
    for _, row in display.iterrows():
        color = quality_colors.get(row["mean_quality"], default_color)
        centroid = row.geometry.centroid
        popup_html = (
            f"<b>{group_name}</b><br>{row['municipality']}<br>"
            f"Aire de diffusion, {row['ad_id']}<br>"
            f"Cote moyenne, {row['mean_score_percent']}/100<br>"
            f"Cote qualitative, {row['mean_quality']}<br>"
            f"Nombre de points, {row['n_points']}"
        )
        folium.Marker(
            location=[centroid.y, centroid.x],
            icon=_square(
                icon_class,
                color,
                vc["size_sector_marker"],
                vc["size_icon_ratio"],
                offset_px,
            ),
            tooltip=f"{group_name}, {row['municipality']}",
            popup=folium.Popup(popup_html, max_width=vc["size_popup_sector"]),
        ).add_to(group)
    group.add_to(web_map)


def _cluster_icon_script(vc):
    """Fonction JavaScript qui colore un cluster selon la cote moyenne de ses points.

    Chaque residence porte deja la couleur de sa cote qualitative. La fonction convertit
    ces couleurs en niveaux, du meilleur au moins bon, fait la moyenne des points du
    cluster et applique la couleur du niveau moyen. Le nombre de points reste affiche.
    """
    palette = list(vc["quality_colors"].values())
    levels = {color: index for index, color in enumerate(palette)}
    size_px = vc["size_cluster_marker"]
    return f"""
    function (cluster) {{
        var levels = {json.dumps(levels)};
        var palette = {json.dumps(palette)};
        var markers = cluster.getAllChildMarkers();
        var total = 0;
        var counted = 0;
        for (var i = 0; i < markers.length; i++) {{
            var level = levels[markers[i].options.fillColor];
            if (level !== undefined) {{
                total += level;
                counted += 1;
            }}
        }}
        var color = "{vc["color_residence_default"]}";
        if (counted > 0) {{
            color = palette[Math.round(total / counted)];
        }}
        var html = '<div style="width:{size_px}px;height:{size_px}px;background:' + color
            + ';border:2px solid #ffffff;border-radius:50%;display:flex;'
            + 'align-items:center;justify-content:center;color:#ffffff;font-weight:bold;'
            + 'text-shadow:0 0 3px rgba(0,0,0,0.9);box-shadow:0 0 3px rgba(0,0,0,0.5);">'
            + markers.length + '</div>';
        return new L.DivIcon({{
            html: html,
            className: "",
            iconSize: new L.Point({size_px}, {size_px})
        }});
    }}
    """


def _add_residence_points(web_map, residences_gdf, service_types, vc, geographic_crs):
    """Ajoute les residences en points colores selon leur cote qualitative.

    Un seul cluster regroupe les points pour alleger la carte. Sa couleur suit la cote
    moyenne des points qu'il contient. Un clic affiche l'adresse, la cote sur 100, la cote
    qualitative et la distance vers chaque service en kilometres, comme dans GMQ210.
    """
    quality_colors = vc["quality_colors"]
    service_labels = vc["service_labels"]
    default_color = vc["color_residence_default"]
    cluster = MarkerCluster(
        name=vc["layer_names"]["residences"],
        icon_create_function=_cluster_icon_script(vc),
    )
    for _, row in _to_display(residences_gdf, geographic_crs).iterrows():
        quality = row["quality_label"]
        lines = [
            f"<b>{row.get('address', '')}</b>",
            f"Cote, {row['score_percent']}/100",
            f"Cote qualitative, {quality}",
        ]
        for service_type in service_types:
            label = service_labels.get(service_type, service_type)
            distance = row.get(f"distance_{service_type}_km")
            shown = "hors de portée" if distance is None else f"{distance} km"
            lines.append(f"{label}, {shown}")
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=vc["style_residence_radius"],
            color=vc["color_residence_outline"],
            weight=vc["style_residence_weight"],
            fill=True,
            fill_color=quality_colors.get(quality, default_color),
            fill_opacity=vc["style_residence_fill_opacity"],
            popup=folium.Popup(
                "<br>".join(lines), max_width=vc["size_popup_residence"]
            ),
        ).add_to(cluster)
    cluster.add_to(web_map)


def _add_base_layers(
    web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc, geographic_crs
):
    """Ajoute la riviere, le reseau, les limites municipales et la zone d'etude."""
    names = vc["layer_names"]
    _add_river(
        web_map,
        water_gdf,
        geographic_crs,
        names["river"],
        vc["color_river"],
        vc["style_river_weight"],
        vc["style_river_fill_opacity"],
    )
    _add_walk_network(
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
    _add_municipal_limits(
        web_map,
        municipalities_gdf,
        geographic_crs,
        names["municipal_limits"],
        vc["color_municipal_limits"],
        vc["style_municipal_limits_weight"],
    )
    _add_study_outline(
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
    path,
    station_field="nom_gare",
    line_field="nom_train",
    logger=None,
):
    """Carte du levier, residences en clusters plus les meilleurs secteurs mis en evidence.

    Elle reprend tous les elements de la carte d'accessibilite, residences colorees par cote
    et regroupees en clusters, reseau, services, riviere et limites. La carte transport
    ajoute les arrets, les gares et les lignes, l'appelant passe alors ces couches, sinon
    None. La meilleure aire de diffusion d'adresses existantes et la meilleure aire ou
    implanter des logements de chaque municipalite ressortent en polygones remplis colores
    par leur cote moyenne, avec un carre pictogramme au centroide.
    """
    vc = visual_config
    names = vc["layer_names"]
    icons = vc["service_icons"]
    icon_ratio = vc["size_icon_ratio"]
    offset = vc["size_sector_marker_offset"]
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
    _add_train_lines(
        web_map,
        lines_gdf,
        geographic_crs,
        names["train_lines"],
        vc["color_stations"],
        vc["style_train_line_weight"],
        vc["style_train_line_dash"],
        line_field,
    )

    _add_residence_points(web_map, residences_gdf, service_types, vc, geographic_crs)

    _add_service_markers(
        web_map,
        services_gdf,
        geographic_crs,
        names["services"],
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_services"],
        vc["service_labels"],
        vc["size_service_marker"],
        icon_ratio,
        vc["size_popup_service"],
    )
    _add_bubble_points(
        web_map,
        stops_gdf,
        geographic_crs,
        names["stops"],
        vc["icon_stop"],
        vc["color_stops"],
        "stop_name",
        vc["size_stop_bubble"],
        icon_ratio,
    )
    _add_bubble_points(
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
    _add_sectors(
        web_map,
        address_sectors,
        geographic_crs,
        names["address_sectors"],
        vc["icon_best_address"],
        offset,
        vc,
    )
    _add_sectors(
        web_map,
        site_sectors,
        geographic_crs,
        names["site_sectors"],
        vc["icon_new_residence"],
        -offset,
        vc,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    _save(web_map, path, logger)
