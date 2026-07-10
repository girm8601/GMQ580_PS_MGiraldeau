"""Cartes interactives du projet avec folium.

Les couches sont ramenees en coordonnees geographiques pour l'affichage web.
Chaque famille d'entites a son pictogramme et sa couleur definis dans la
configuration. Seules les aires de diffusion a l'etude sont colorees, la
zone tampon est marquee d'un trait noir, la riviere Richelieu et le reseau
pietonnier s'affichent au dessus des aires mais sous les entites ponctuelles.
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


def _add_coverage_layer(web_map, ad_gdf, value_field, layer_name):
    """Ajoute la couverture des aires de diffusion a l'etude en aplats."""
    ad_display = _to_display(ad_gdf[["geometry", value_field]].reset_index(drop=True))
    ad_display["ad_index"] = ad_display.index.astype(str)
    folium.Choropleth(
        geo_data=ad_display.to_json(),
        data=ad_display,
        columns=["ad_index", value_field],
        key_on="feature.id",
        fill_color="RdYlGn",
        fill_opacity=0.6,
        line_opacity=0.3,
        bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        legend_name=layer_name,
        name=layer_name,
    ).add_to(web_map)


def _add_zone_outline(web_map, zone_gdf, color):
    """Ajoute le trait noir qui delimite la zone d'etude."""
    folium.GeoJson(
        _to_display(zone_gdf[["geometry"]]).to_json(),
        name="Limite de la zone d'étude",
        style_function=lambda feature: {
            "fillOpacity": 0.0,
            "color": color,
            "weight": 2,
        },
    ).add_to(web_map)


def _add_river(web_map, water_gdf, color):
    """Ajoute la riviere au dessus des aires mais sous les points."""
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
    """Ajoute le reseau pietonnier, contour gris et remplissage blanc."""
    if edges_gdf is None or len(edges_gdf) == 0:
        return
    edges_json = _to_display(edges_gdf[["geometry"]]).to_json()
    group = folium.FeatureGroup(name="Réseau piétonnier")
    folium.GeoJson(
        edges_json,
        style_function=lambda feature: {
            "color": casing_color,
            "weight": 3,
            "opacity": 0.9,
        },
    ).add_to(group)
    folium.GeoJson(
        edges_json,
        style_function=lambda feature: {
            "color": fill_color,
            "weight": 1.4,
            "opacity": 1.0,
        },
    ).add_to(group)
    group.add_to(web_map)


def _add_train_lines(web_map, lines_gdf, color):
    """Ajoute les lignes de train en pointille noir, au meme titre que les routes."""
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
    """Construit le pictogramme FontAwesome d'un point."""
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


def _add_glyph_points(
    web_map, gdf, group_name, icon_for_row, color, tooltip_field=None, size_px=14
):
    """Ajoute une couche de points avec pictogrammes et infobulles.

    icon_for_row recoit la ligne et retourne la classe FontAwesome a utiliser,
    ce qui permet un pictogramme distinct par type de service. Une couche
    absente ou vide est simplement sautee.
    """
    if gdf is None or len(gdf) == 0:
        return
    group = folium.FeatureGroup(name=group_name)
    for _, row in _to_display(gdf).iterrows():
        tooltip = (
            str(row.get(tooltip_field, group_name)) if tooltip_field else group_name
        )
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            icon=_glyph(icon_for_row(row), color, size_px),
            tooltip=tooltip,
        ).add_to(group)
    group.add_to(web_map)


def s0_map(
    outline_zone_gdf,
    ad_gdf,
    value_field,
    layer_name,
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
    """Carte de la couverture actuelle S0 avec les couches de contexte.

    Seules les aires de diffusion a l'etude sont colorees. Le reseau
    pietonnier, la riviere et le transport donnent le contexte de lecture.
    """
    web_map = _base_map(outline_zone_gdf)
    _add_coverage_layer(web_map, ad_gdf, value_field, layer_name)
    _add_river(web_map, water_gdf, visual_config["couleur_riviere"])
    _add_walk_network(
        web_map,
        network_edges,
        visual_config["couleur_reseau_contour"],
        visual_config["couleur_reseau"],
    )
    _add_train_lines(web_map, lines_gdf, visual_config["couleur_gares"])
    _add_zone_outline(web_map, outline_zone_gdf, visual_config["couleur_zone"])

    icons = visual_config["icones_services"]
    _add_glyph_points(
        web_map,
        services_gdf,
        "Services essentiels",
        lambda row: icons.get(row["service_type"], "fa-circle"),
        visual_config["couleur_services"],
        tooltip_field="service_type",
    )
    _add_glyph_points(
        web_map,
        stops_gdf,
        "Arrêts d'autobus",
        lambda row: visual_config["icone_arret"],
        visual_config["couleur_arrets"],
        tooltip_field="stop_name",
        size_px=12,
    )
    _add_glyph_points(
        web_map,
        stations_gdf,
        "Gares de train",
        lambda row: visual_config["icone_gare"],
        visual_config["couleur_gares"],
        tooltip_field="nom_gare",
        size_px=18,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    _save(web_map, path, logger)


def s1_map(
    outline_zone_gdf,
    ad_gdf,
    value_field,
    layer_name,
    sites_gdf,
    network_edges,
    water_gdf,
    visual_config,
    path,
    logger=None,
):
    """Carte d'un scenario S1, couverture recalculee et sites recommandes.

    Le scenario S1 porte sur l'acces a pied seulement, aucune couche de
    transport n'apparait donc ici. Chaque site recommande porte le
    pictogramme du type de service a y implanter (colonne icone de
    sites_gdf), en rouge pour ressortir. La couverture affichee est
    recalculee apres l'ajout, le gain est donc visible aire par aire.
    """
    web_map = _base_map(outline_zone_gdf)
    _add_coverage_layer(web_map, ad_gdf, value_field, layer_name)
    _add_river(web_map, water_gdf, visual_config["couleur_riviere"])
    _add_walk_network(
        web_map,
        network_edges,
        visual_config["couleur_reseau_contour"],
        visual_config["couleur_reseau"],
    )
    _add_zone_outline(web_map, outline_zone_gdf, visual_config["couleur_zone"])
    _add_glyph_points(
        web_map,
        sites_gdf,
        "Sites et services recommandés",
        lambda row: row["icone"],
        visual_config["couleur_sites"],
        tooltip_field="recommandation",
        size_px=20,
    )
    folium.LayerControl(collapsed=False).add_to(web_map)
    _save(web_map, path, logger)
