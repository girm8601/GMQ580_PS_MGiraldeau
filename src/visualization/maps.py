"""Cartes interactives du projet avec folium.

Chaque residence est un point colore selon sa cote qualitative, comme dans GMQ210.
Un clic sur une residence affiche son adresse, sa cote sur 100, sa cote qualitative
et sa distance vers chaque service. Les services essentiels existants et les
nouveaux services ajoutes sont des reperes en forme d'epingle. Les arrets d'autobus
et les gares sont des bulles rondes avec leur pictogramme blanc. Les limites
municipales et la limite de la zone d'etude sont tracees en noir. Toutes les
couleurs, tailles et epaisseurs viennent de la section visualization de config.yaml.
"""

from __future__ import annotations

import os

import folium


def _to_display(gdf, display_crs):
    """Reprojette une couche vers le CRS d'affichage web."""
    return gdf.to_crs(display_crs)


def ordered_service_types(service_types, importance):
    """Types de service tries du plus important au moins important pour l'affichage.

    Utilise pour lister les distances dans l'infobulle d'une residence dans le
    meme ordre que l'importance qui a servi a calculer sa cote, aines ou
    population generale selon la carte.
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


def _base_map(zone_gdf, vc):
    """Cree la carte de base centree sur la zone d'etude, avec Font Awesome charge."""
    zone = _to_display(zone_gdf, vc["display_crs"])
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


def _add_study_outline(web_map, zone_gdf, display_crs, color, weight):
    """Ajoute le trait noir qui delimite la zone d'etude."""
    folium.GeoJson(
        _to_display(zone_gdf[["geometry"]], display_crs).to_json(),
        name="Limite de la zone d'etude",
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": weight,
        },
    ).add_to(web_map)


def _add_municipal_limits(web_map, municipalities_gdf, display_crs, color, weight):
    """Ajoute les limites municipales en trait noir fin, sans nom de municipalite."""
    if municipalities_gdf is None or len(municipalities_gdf) == 0:
        return
    folium.GeoJson(
        _to_display(municipalities_gdf[["geometry"]], display_crs).to_json(),
        name="Limites municipales",
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": weight,
        },
    ).add_to(web_map)


def _add_river(web_map, water_gdf, display_crs, color, weight, fill_opacity):
    """Ajoute la riviere au dessus du reseau mais sous les points."""
    if water_gdf is None or len(water_gdf) == 0:
        return
    folium.GeoJson(
        _to_display(water_gdf[["geometry"]], display_crs).to_json(),
        name="Riviere Richelieu",
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
    display_crs,
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
    edges_json = _to_display(edges_gdf[["geometry"]], display_crs).to_json()
    group = folium.FeatureGroup(name="Reseau pietonnier")
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
    web_map, lines_gdf, display_crs, color, weight, dash_array, name_field
):
    """Ajoute les lignes de train en pointille noir, contexte cartographique."""
    if lines_gdf is None or len(lines_gdf) == 0:
        return
    lines_display = lines_gdf[[name_field, "geometry"]]
    folium.GeoJson(
        _to_display(lines_display, display_crs).to_json(),
        name="Lignes de train",
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
    display_crs,
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
    for _, row in _to_display(gdf, display_crs).iterrows():
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
    display_crs,
    group_name,
    icon_for_row,
    color,
    service_labels,
    size_px,
    icon_ratio,
    added=False,
):
    """Ajoute les services essentiels en reperes colores avec infobulle.

    Un clic affiche le libelle du type de service et le nom de l'etablissement,
    comme dans GMQ210. added distingue les services ajoutes des services existants.
    """
    if gdf is None or len(gdf) == 0:
        return
    group = folium.FeatureGroup(name=group_name)
    for _, row in _to_display(gdf, display_crs).iterrows():
        service_type = row.get("service_type")
        label = service_labels.get(service_type, service_type)
        if added:
            title = f"Ajout, {label}"
            detail = str(row.get("recommendation", "") or "")
        else:
            title = label
            detail = str(row.get("name", "") or "")
        popup_html = f"<b>{title}</b><br>{detail}" if detail else f"<b>{title}</b>"
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=_pin(icon_for_row(row), color, size_px, icon_ratio),
            tooltip=title,
            popup=folium.Popup(popup_html, max_width=220),
        ).add_to(group)
    group.add_to(web_map)


def _add_residence_points(web_map, residences_gdf, service_types, visual_config):
    """Ajoute les residences en points colores selon leur cote qualitative.

    Un groupe de couche par cote qualitative permet d'activer ou de desactiver chaque
    classe. Un clic affiche l'adresse, la cote sur 100, la cote qualitative et la
    distance vers chaque service en kilometres, comme dans GMQ210.
    """
    quality_colors = visual_config["quality_colors"]
    service_labels = visual_config["service_labels"]
    default_color = visual_config["color_residence_default"]
    outline_color = visual_config["color_residence_outline"]
    radius = visual_config["style_residence_radius"]
    weight = visual_config["style_residence_weight"]
    fill_opacity = visual_config["style_residence_fill_opacity"]
    groups = {
        label: folium.FeatureGroup(name=f"Cote, {label}") for label in quality_colors
    }
    residences_display = _to_display(residences_gdf, visual_config["display_crs"])
    for _, row in residences_display.iterrows():
        quality = row["quality_label"]
        color = quality_colors.get(quality, default_color)
        lines = [
            f"<b>{row.get('address', '')}</b>",
            f"Cote, {row['score_percent']}/100",
            f"Cote qualitative, {quality}",
        ]
        for service_type in service_types:
            label = service_labels.get(service_type, service_type)
            distance = row.get(f"distance_{service_type}_km")
            shown = "hors de portee" if distance is None else f"{distance} km"
            lines.append(f"{label}, {shown}")
        popup_html = "<br>".join(lines)
        target = groups.get(quality)
        if target is None:
            continue
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=radius,
            color=outline_color,
            weight=weight,
            fill=True,
            fill_color=color,
            fill_opacity=fill_opacity,
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(target)
    for group in groups.values():
        group.add_to(web_map)


def _add_base_layers(
    web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc
):
    """Ajoute la riviere, le reseau, les limites municipales et la zone d'etude."""
    _add_river(
        web_map,
        water_gdf,
        vc["display_crs"],
        vc["color_river"],
        vc["style_river_weight"],
        vc["style_river_fill_opacity"],
    )
    _add_walk_network(
        web_map,
        network_edges,
        vc["display_crs"],
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
        vc["display_crs"],
        vc["color_municipal_limits"],
        vc["style_municipal_limits_weight"],
    )
    _add_study_outline(
        web_map,
        zone_gdf,
        vc["display_crs"],
        vc["color_study_outline"],
        vc["style_study_outline_weight"],
    )


def s0_map(
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
    visual_config,
    path,
    station_field="nom_gare",
    line_field="nom_train",
    logger=None,
):
    """Carte de l'accessibilite actuelle S0, residences colorees par cote.

    Les couches de transport ne sont affichees que sur la carte de verification,
    l'appelant passe alors les arrets, gares et lignes, sinon None. station_field et
    line_field viennent de config["transit"], nom des champs des couches exo.
    """
    vc = visual_config
    web_map = _base_map(zone_gdf, vc)
    _add_base_layers(
        web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc
    )
    _add_train_lines(
        web_map,
        lines_gdf,
        vc["display_crs"],
        vc["color_stations"],
        vc["style_train_line_weight"],
        vc["style_train_line_dash"],
        line_field,
    )

    _add_residence_points(web_map, residences_gdf, service_types, vc)

    icons = vc["service_icons"]
    labels = vc["service_labels"]
    icon_ratio = vc["size_icon_ratio"]
    _add_service_markers(
        web_map,
        services_gdf,
        vc["display_crs"],
        "Services essentiels",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_services"],
        labels,
        vc["size_service_marker"],
        icon_ratio,
    )
    _add_bubble_points(
        web_map,
        stops_gdf,
        vc["display_crs"],
        "Arrets d'autobus",
        vc["icon_stop"],
        vc["color_stops"],
        "stop_name",
        vc["size_stop_bubble"],
        icon_ratio,
    )
    _add_bubble_points(
        web_map,
        stations_gdf,
        vc["display_crs"],
        "Gares de train",
        vc["icon_station"],
        vc["color_stations"],
        station_field,
        vc["size_station_bubble"],
        icon_ratio,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    _save(web_map, path, logger)


def s1_map(
    zone_gdf,
    municipalities_gdf,
    residences_gdf,
    service_types,
    network_edges,
    services_gdf,
    new_sites_gdf,
    water_gdf,
    visual_config,
    path,
    logger=None,
):
    """Carte d'un scenario S1, residences recolorees et services ajoutes.

    Le scenario S1 porte sur l'acces a pied seulement, aucune couche de transport
    n'apparait donc ici. Les services existants restent en reperes mauve fonce, les
    services ajoutes sont en reperes bleu cadet un peu plus grands.
    """
    vc = visual_config
    web_map = _base_map(zone_gdf, vc)
    _add_base_layers(
        web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc
    )

    _add_residence_points(web_map, residences_gdf, service_types, vc)

    icons = vc["service_icons"]
    labels = vc["service_labels"]
    icon_ratio = vc["size_icon_ratio"]
    _add_service_markers(
        web_map,
        services_gdf,
        vc["display_crs"],
        "Services essentiels existants",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_services"],
        labels,
        vc["size_service_marker"],
        icon_ratio,
    )
    _add_service_markers(
        web_map,
        new_sites_gdf,
        vc["display_crs"],
        "Services ajoutes (S1)",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_new_sites"],
        labels,
        vc["size_new_site_marker"],
        icon_ratio,
        added=True,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    _save(web_map, path, logger)
