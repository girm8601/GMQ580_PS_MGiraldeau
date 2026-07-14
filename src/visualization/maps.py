"""Cartes interactives du projet avec folium.

Chaque residence est un point colore selon sa cote qualitative, comme dans GMQ210.
Un clic sur une residence affiche son adresse, sa cote sur 100, sa cote qualitative
et sa distance vers chaque service. Les services essentiels existants sont des bulles
mauve pale, les nouveaux services recommandes sont des bulles mauve fonce un peu plus
grandes. Les arrets d'autobus et les gares gardent leur pictogramme. Les limites
municipales et la limite de la zone d'etude sont tracees en noir.
"""

from __future__ import annotations

import os

import folium

DISPLAY_CRS = "EPSG:4326"


def _to_display(gdf):
    """Reprojette une couche vers le CRS d'affichage web."""
    return gdf.to_crs(DISPLAY_CRS)


def _save(web_map, path, logger=None):
    """Ecrit la carte HTML et cree le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    web_map.save(path)
    if logger is not None:
        logger.info("Carte exportee, %s", path)


def _base_map(zone_gdf):
    """Cree la carte de base centree sur la zone d'etude."""
    zone = _to_display(zone_gdf)
    center = zone.geometry.union_all().centroid
    return folium.Map(
        location=[center.y, center.x], zoom_start=13, tiles="cartodbpositron"
    )


def _add_study_outline(web_map, zone_gdf, color):
    """Ajoute le trait noir qui delimite la zone d'etude."""
    folium.GeoJson(
        _to_display(zone_gdf[["geometry"]]).to_json(),
        name="Limite de la zone d'etude",
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": 2.5,
        },
    ).add_to(web_map)


def _add_municipal_limits(web_map, municipalities_gdf, color):
    """Ajoute les limites municipales en trait noir fin, sans nom de municipalite."""
    if municipalities_gdf is None or len(municipalities_gdf) == 0:
        return
    folium.GeoJson(
        _to_display(municipalities_gdf[["geometry"]]).to_json(),
        name="Limites municipales",
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": 1,
        },
    ).add_to(web_map)


def _add_river(web_map, water_gdf, color):
    """Ajoute la riviere au dessus du reseau mais sous les points."""
    if water_gdf is None or len(water_gdf) == 0:
        return
    folium.GeoJson(
        _to_display(water_gdf[["geometry"]]).to_json(),
        name="Riviere Richelieu",
        style_function=lambda feature: {
            "fillColor": color,
            "color": color,
            "weight": 1,
            "fillOpacity": 0.9,
        },
    ).add_to(web_map)


def _add_walk_network(web_map, edges_gdf, casing_color, fill_color):
    """Ajoute le reseau pietonnier, contour gris et remplissage blanc fin."""
    if edges_gdf is None or len(edges_gdf) == 0:
        return
    edges_json = _to_display(edges_gdf[["geometry"]]).to_json()
    group = folium.FeatureGroup(name="Reseau pietonnier")
    folium.GeoJson(
        edges_json,
        style_function=lambda feature: {
            "color": casing_color,
            "weight": 2,
            "opacity": 0.7,
        },
    ).add_to(group)
    folium.GeoJson(
        edges_json,
        style_function=lambda feature: {
            "color": fill_color,
            "weight": 0.8,
            "opacity": 1.0,
        },
    ).add_to(group)
    group.add_to(web_map)


def _add_train_lines(web_map, lines_gdf, color):
    """Ajoute les lignes de train en pointille noir, contexte cartographique."""
    if lines_gdf is None or len(lines_gdf) == 0:
        return
    lines_display = lines_gdf[["nom_train", "geometry"]]
    folium.GeoJson(
        _to_display(lines_display).to_json(),
        name="Lignes de train",
        style_function=lambda feature: {
            "color": color,
            "weight": 2,
            "dashArray": "6",
        },
    ).add_to(web_map)


def _glyph(icon_class, color, size_px):
    """Pictogramme FontAwesome simple, pour les arrets et les gares."""
    html = (
        f'<i class="fa-solid {icon_class}" '
        f'style="color:{color};font-size:{size_px}px;'
        f'text-shadow:0 0 3px #ffffff, 0 0 3px #ffffff;"></i>'
    )
    return folium.DivIcon(
        html=html,
        icon_size=(size_px, size_px),
        icon_anchor=(size_px // 2, size_px // 2),
    )


def _bubble(icon_class, bg_color, size_px):
    """Bulle ronde coloree avec un pictogramme blanc, comme dans GMQ210."""
    glyph_size = int(size_px * 0.55)
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


def _add_glyph_points(web_map, gdf, group_name, icon_class, color, name_field, size_px):
    """Ajoute les arrets ou les gares en pictogramme simple avec infobulle."""
    if gdf is None or len(gdf) == 0:
        return
    group = folium.FeatureGroup(name=group_name)
    for _, row in _to_display(gdf).iterrows():
        name = str(row.get(name_field, "") or "")
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=_glyph(icon_class, color, size_px),
            tooltip=name or group_name,
        ).add_to(group)
    group.add_to(web_map)


def _add_service_bubbles(
    web_map,
    gdf,
    group_name,
    icon_for_row,
    bg_color,
    service_labels,
    size_px,
    added=False,
):
    """Ajoute les services essentiels en bulles colorees avec infobulle.

    Un clic affiche le libelle du type de service et le nom de l'etablissement,
    comme dans GMQ210. added distingue les services ajoutes des services existants.
    """
    if gdf is None or len(gdf) == 0:
        return
    group = folium.FeatureGroup(name=group_name)
    for _, row in _to_display(gdf).iterrows():
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
            icon=_bubble(icon_for_row(row), bg_color, size_px),
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
    groups = {
        label: folium.FeatureGroup(name=f"Cote, {label}") for label in quality_colors
    }
    residences_display = _to_display(residences_gdf)
    for _, row in residences_display.iterrows():
        quality = row["quality_label"]
        color = quality_colors.get(quality, "#808080")
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
            radius=4,
            color="#000000",
            weight=0.4,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(target)
    for group in groups.values():
        group.add_to(web_map)


def _add_base_layers(
    web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc
):
    """Ajoute la riviere, le reseau, les limites municipales et la zone d'etude."""
    _add_river(web_map, water_gdf, vc["color_river"])
    _add_walk_network(
        web_map, network_edges, vc["color_network_casing"], vc["color_network_fill"]
    )
    _add_municipal_limits(web_map, municipalities_gdf, vc["color_municipal_limits"])
    _add_study_outline(web_map, zone_gdf, vc["color_study_outline"])


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
    logger=None,
):
    """Carte de l'accessibilite actuelle S0, residences colorees par cote.

    Les couches de transport ne sont affichees que sur la carte de verification,
    l'appelant passe alors les arrets, gares et lignes, sinon None.
    """
    vc = visual_config
    web_map = _base_map(zone_gdf)
    _add_river(web_map, water_gdf, vc["color_river"])
    _add_walk_network(
        web_map, network_edges, vc["color_network_casing"], vc["color_network_fill"]
    )
    _add_train_lines(web_map, lines_gdf, vc["color_stations"])
    _add_municipal_limits(web_map, municipalities_gdf, vc["color_municipal_limits"])
    _add_study_outline(web_map, zone_gdf, vc["color_study_outline"])

    _add_residence_points(web_map, residences_gdf, service_types, vc)

    icons = vc["service_icons"]
    labels = vc["service_labels"]
    _add_service_bubbles(
        web_map,
        services_gdf,
        "Services essentiels",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_services"],
        labels,
        18,
    )
    _add_glyph_points(
        web_map,
        stops_gdf,
        "Arrets d'autobus",
        vc["icon_stop"],
        vc["color_stops"],
        "stop_name",
        14,
    )
    _add_glyph_points(
        web_map,
        stations_gdf,
        "Gares de train",
        vc["icon_station"],
        vc["color_stations"],
        "nom_gare",
        14,
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
    n'apparait donc ici. Les services existants restent en bulles mauve pale, les
    services ajoutes sont en bulles mauve fonce un peu plus grandes.
    """
    vc = visual_config
    web_map = _base_map(zone_gdf)
    _add_base_layers(
        web_map, zone_gdf, municipalities_gdf, network_edges, water_gdf, vc
    )

    _add_residence_points(web_map, residences_gdf, service_types, vc)

    icons = vc["service_icons"]
    labels = vc["service_labels"]
    _add_service_bubbles(
        web_map,
        services_gdf,
        "Services essentiels existants",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_services"],
        labels,
        18,
    )
    _add_service_bubbles(
        web_map,
        new_sites_gdf,
        "Services ajoutes (S1)",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        vc["color_new_sites"],
        labels,
        24,
        added=True,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    _save(web_map, path, logger)
