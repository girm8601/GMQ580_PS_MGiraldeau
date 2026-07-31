"""Couches de donnees tracees sur les cartes.

Chaque fonction ajoute une couche a une carte folium deja creee, la riviere, le reseau
pietonnier, les limites, les lignes de train, les arrets et les gares, les services
essentiels, les secteurs retenus et les residences en groupes. L'assemblage de la carte est
dans maps.py, son habillage dans map_layout.py et ses symboles dans map_symbols.py.

Toutes les couleurs, tailles, epaisseurs et noms de couches viennent de la section
visualization de config.yaml.
"""

from __future__ import annotations

import folium
from folium.plugins import MarkerCluster

from src.visualization.map_symbols import bubble, cluster_icon_script, pin, square


def to_display(gdf, geographic_crs):
    """Reprojette une couche vers le CRS d'affichage web."""
    return gdf.to_crs(geographic_crs)


def add_study_outline(web_map, zone_gdf, geographic_crs, group_name, color, weight):
    """Ajoute le trait noir qui delimite la zone d'etude."""
    folium.GeoJson(
        to_display(zone_gdf[["geometry"]], geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": weight,
        },
    ).add_to(web_map)


def add_municipal_limits(
    web_map, municipalities_gdf, geographic_crs, group_name, color, weight
):
    """Ajoute les limites municipales en trait noir fin, sans nom de municipalite."""
    if municipalities_gdf is None or len(municipalities_gdf) == 0:
        return
    folium.GeoJson(
        to_display(municipalities_gdf[["geometry"]], geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": weight,
        },
    ).add_to(web_map)


def add_river(
    web_map, water_gdf, geographic_crs, group_name, color, weight, fill_opacity
):
    """Ajoute la riviere au dessus du reseau mais sous les points."""
    if water_gdf is None or len(water_gdf) == 0:
        return
    folium.GeoJson(
        to_display(water_gdf[["geometry"]], geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "fillColor": color,
            "color": color,
            "weight": weight,
            "fillOpacity": fill_opacity,
        },
    ).add_to(web_map)


def add_walk_network(
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
    edges_json = to_display(edges_gdf[["geometry"]], geographic_crs).to_json()
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


def add_train_lines(
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
        to_display(lines_display, geographic_crs).to_json(),
        name=group_name,
        style_function=lambda feature: {
            "color": color,
            "weight": weight,
            "dashArray": dash_array,
        },
    ).add_to(web_map)


def add_bubble_points(
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
    for _, row in to_display(gdf, geographic_crs).iterrows():
        name = str(row.get(name_field, "") or "")
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=bubble(icon_class, color, size_px, icon_ratio),
            tooltip=name or group_name,
        ).add_to(group)
    group.add_to(web_map)


def add_service_markers(
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
    for _, row in to_display(gdf, geographic_crs).iterrows():
        service_type = row.get("service_type")
        label = service_labels.get(service_type, service_type)
        detail = str(row.get("name", "") or "")
        popup_html = f"<b>{label}</b><br>{detail}" if detail else f"<b>{label}</b>"
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=pin(icon_for_row(row), color, size_px, icon_ratio),
            tooltip=label,
            popup=folium.Popup(popup_html, max_width=popup_width),
        ).add_to(group)
    group.add_to(web_map)


def add_sectors(
    web_map, sectors_gdf, geographic_crs, group_name, icon_class, offset_px, vc
):
    """Ajoute des secteurs, polygone rempli colore par cote moyenne plus un carre au centroide.

    Chaque secteur est la meilleure aire de diffusion d'une municipalite. Le polygone et le
    carre prennent la couleur de la cote qualitative moyenne du secteur. Un clic affiche la
    ville, l'aire, la cote moyenne sur 100, la cote qualitative et le nombre de points. Le
    centroide est calcule dans le CRS projete puis ramene en degres, comme dans le tableau
    exporte, pour que le carre et la ligne du tableau tombent au meme endroit.
    """
    if sectors_gdf is None or len(sectors_gdf) == 0:
        return
    quality_colors = vc["quality_colors"]
    default_color = vc["color_residence_default"]
    group = folium.FeatureGroup(name=group_name)
    display = to_display(sectors_gdf, geographic_crs)
    display["centroid"] = to_display(
        sectors_gdf.geometry.centroid, geographic_crs
    ).to_numpy()
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
        centroid = row["centroid"]
        popup_html = (
            f"<b>{group_name}</b><br>{row['municipality']}<br>"
            f"Aire de diffusion, {row['ad_id']}<br>"
            f"Cote moyenne, {row['mean_score_percent']}/100<br>"
            f"Cote qualitative, {row['mean_quality']}<br>"
            f"Nombre de points, {row['n_points']}"
        )
        folium.Marker(
            location=[centroid.y, centroid.x],
            icon=square(
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


def add_residence_points(web_map, residences_gdf, service_types, vc, geographic_crs):
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
        icon_create_function=cluster_icon_script(vc),
    )
    for _, row in to_display(residences_gdf, geographic_crs).iterrows():
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
