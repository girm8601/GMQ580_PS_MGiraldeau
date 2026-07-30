"""Cartes interactives du projet avec folium.

Le projet produit les deux cartes du levier, a la marche et au transport. Chaque
residence est un point colore selon sa cote qualitative, regroupe en clusters, comme dans
GMQ210. Un cluster prend la couleur de la cote moyenne des points qu'il contient. Les
services essentiels existants sont des reperes en forme d'epingle. Les arrets d'autobus et
les gares sont des bulles rondes. Les meilleurs secteurs d'adresses et de sites ressortent
en polygones remplis colores par leur cote moyenne, avec un carre pictogramme au centroide.
Les limites sont tracees en noir. Toutes les couleurs, tailles, epaisseurs et noms de
couches viennent de la section visualization de config.yaml.

Chaque carte porte aussi les elements d'une carte thematique, un titre, une legende, une
barre d'echelle et une note de source et de projection. La legende decrit tout ce qui est
trace et rien d'autre, les reperes du transport n'y figurent donc que sur la carte du
transport. Elle est en bas a gauche et l'echelle en bas a droite, les deux ne peuvent pas
se couvrir. La fleche du nord est inutile ici, le nord d'une carte web est toujours en haut.
"""

from __future__ import annotations

import json
import os

import folium
import geopandas as gpd
from branca.element import MacroElement
from folium.plugins import MarkerCluster
from jinja2 import Template


def _to_display(gdf, geographic_crs):
    """Reprojette une couche vers le CRS d'affichage web."""
    return gdf.to_crs(geographic_crs)


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
    pieds, elle est donc ajoutee separement par _add_scale.
    """
    center = _to_display(
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


def _add_title(web_map, title, subtitle, vc):
    """Ajoute le titre et le sous titre de la carte, en haut et centres."""
    html = (
        f'<div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);'
        f"z-index:9999;background:rgba(255,255,255,0.92);padding:6px 14px;"
        f"border:1px solid #999;border-radius:4px;text-align:center;"
        f'font-family:system-ui,Arial,sans-serif;max-width:{vc["size_title_box"]}px;">'
        f'<div style="font-size:{vc["size_title_font"]}px;font-weight:bold;">{title}</div>'
        f'<div style="font-size:{vc["size_subtitle_font"]}px;">{subtitle}</div>'
        f"</div>"
    )
    web_map.get_root().html.add_child(folium.Element(html))


def _legend_row(symbol, label):
    """Une ligne de legende, un symbole suivi de son libelle."""
    return (
        f'<div style="margin:3px 0;line-height:1.25;display:flex;'
        f'align-items:center;gap:6px;">'
        f'<span style="flex:0 0 18px;text-align:center;">{symbol}</span>'
        f"<span>{label}</span></div>"
    )


def _legend_patch(color, size_px):
    """Carre plein de couleur, pour une classe de cote ou une surface."""
    return (
        f'<span style="display:inline-block;width:{size_px}px;height:{size_px}px;'
        f'background:{color};border:1px solid #333;vertical-align:middle;"></span>'
    )


def _legend_line(color, weight, dashed=False):
    """Segment de trait, pour une limite ou un reseau."""
    style = "dashed" if dashed else "solid"
    return (
        f'<span style="display:inline-block;width:18px;'
        f'border-top:{max(weight, 1)}px {style} {color};vertical-align:middle;"></span>'
    )


def _legend_bubble(icon_class, color, size_px):
    """Bulle ronde coloree avec son pictogramme, pour un arret ou une gare."""
    return (
        f'<span style="display:inline-flex;align-items:center;'
        f"justify-content:center;width:{size_px}px;height:{size_px}px;"
        f'background:{color};border-radius:50%;">'
        f'<i class="fa-solid {icon_class}" style="color:#fff;'
        f'font-size:{int(size_px * 0.6)}px;"></i></span>'
    )


def _legend_pin(color, size_px):
    """Epingle coloree, pour un service essentiel."""
    return (
        f'<span style="display:inline-block;width:{size_px}px;height:{size_px}px;'
        f"background:{color};border-radius:50% 50% 50% 0;"
        f'transform:rotate(-45deg);vertical-align:middle;"></span>'
    )


def _legend_cluster(color, size_px, sample):
    """Bulle ronde portant un nombre, pour un groupe de residences.

    sample est le nombre montre en exemple, il vient de la configuration.
    """
    return (
        f'<span style="display:inline-flex;align-items:center;'
        f"justify-content:center;width:{size_px}px;height:{size_px}px;"
        f"background:{color};border:1px solid #fff;border-radius:50%;color:#fff;"
        f'font-size:{int(size_px * 0.5)}px;font-weight:bold;">{sample}</span>'
    )


def _quality_rows(vc, size_px):
    """Les classes de cote, la couleur qui vaut partout sur la carte."""
    return [
        _legend_row(_legend_patch(color, size_px), label)
        for label, color in vc["quality_colors"].items()
    ]


def _sector_rows(vc):
    """Les deux types de secteurs recommandes, avec leur carre pictogramme."""
    rows = []
    for icon_key, name_key in (
        ("icon_best_address", "address_sectors"),
        ("icon_new_residence", "site_sectors"),
    ):
        symbol = f'<i class="fa-solid {vc[icon_key]}" style="color:#333;"></i>'
        rows.append(_legend_row(symbol, vc["layer_names"][name_key]))
    return rows


def _marker_rows(vc, size_px, with_transit):
    """Les reperes ponctuels reellement traces sur la carte."""
    names = vc["layer_names"]
    rows = [
        _legend_row(
            _legend_cluster(
                vc["color_residence_default"],
                size_px + 6,
                vc["legend_cluster_sample"],
            ),
            vc["legend_cluster_label"],
        ),
        _legend_row(
            _legend_pin(vc["color_services"], size_px),
            vc["legend_service_label"],
        ),
    ]
    if with_transit:
        rows.append(
            _legend_row(
                _legend_bubble(vc["icon_stop"], vc["color_stops"], size_px + 3),
                names["stops"],
            )
        )
        rows.append(
            _legend_row(
                _legend_bubble(vc["icon_station"], vc["color_stations"], size_px + 3),
                names["stations"],
            )
        )
    return rows


def _line_rows(vc, size_px, with_transit, with_network, with_river):
    """Les limites, les reseaux et la riviere reellement traces sur la carte."""
    names = vc["layer_names"]
    rows = [
        _legend_row(
            _legend_line(vc["color_study_outline"], vc["style_study_outline_weight"]),
            names["study_outline"],
        ),
        _legend_row(
            _legend_line(
                vc["color_municipal_limits"], vc["style_municipal_limits_weight"]
            ),
            names["municipal_limits"],
        ),
    ]
    if with_network:
        rows.append(
            _legend_row(
                _legend_line(
                    vc["color_network_casing"], vc["style_network_casing_weight"]
                ),
                names["walk_network"],
            )
        )
    if with_transit:
        rows.append(
            _legend_row(
                _legend_line(
                    vc["color_stations"], vc["style_train_line_weight"], dashed=True
                ),
                names["train_lines"],
            )
        )
    if with_river:
        rows.append(
            _legend_row(_legend_patch(vc["color_river"], size_px), names["river"])
        )
    return rows


def _add_legend(web_map, vc, source_note, with_transit, with_network, with_river):
    """Ajoute la legende complete de la carte, tout ce qui y est trace et rien d'autre.

    La couleur de la cote vaut au meme titre pour une residence, pour un groupe de
    residences et pour un secteur, la legende le dit une seule fois. Les reperes du
    transport n'apparaissent que sur la carte du transport, comme sur la carte elle meme.
    La legende est placee du cote oppose a la barre d'echelle pour ne pas la couvrir.
    """
    size_px = vc["size_legend_swatch"]
    sections = [
        (vc["legend_title"], _quality_rows(vc, size_px), vc["legend_quality_note"]),
        (vc["legend_sector_title"], _sector_rows(vc), ""),
        (
            vc["legend_marker_title"],
            _marker_rows(vc, size_px, with_transit),
            "",
        ),
        (
            vc["legend_line_title"],
            _line_rows(vc, size_px, with_transit, with_network, with_river),
            "",
        ),
    ]
    blocks = []
    for title, rows, note in sections:
        blocks.append(f'<div style="font-weight:bold;margin:6px 0 3px;">{title}</div>')
        blocks.extend(rows)
        if note:
            blocks.append(
                f'<div style="color:#444;font-size:'
                f'{vc["size_legend_note_font"]}px;margin:1px 0 0;">{note}</div>'
            )
    html = (
        f'<div style="position:fixed;bottom:12px;left:12px;z-index:9999;'
        f"background:rgba(255,255,255,0.93);padding:8px 12px;border:1px solid #999;"
        f"border-radius:4px;font-family:system-ui,Arial,sans-serif;"
        f'font-size:{vc["size_legend_font"]}px;width:{vc["size_legend_box"]}px;'
        f'max-height:{vc["size_legend_max_height"]}px;overflow-y:auto;">'
        + "".join(blocks)
        + f'<div style="margin-top:8px;padding-top:6px;border-top:1px solid #ccc;'
        f'color:#444;font-size:{vc["size_legend_note_font"]}px;">{source_note}</div>'
        f"</div>"
    )
    web_map.get_root().html.add_child(folium.Element(html))


class MetricScale(MacroElement):
    """Barre d'echelle en metres seulement, ajoutee apres la creation de la carte.

    L'echelle de folium affiche les pieds en plus des metres et se place en bas a gauche,
    la ou se trouve la legende du projet. Celle ci est donc metrique seulement, le projet
    mesure tout en metres, et elle est placee du cote oppose a la legende. Le passage par un
    MacroElement garantit que le script s'execute apres la creation de la carte.
    """

    _template = Template("""
        {% macro script(this, kwargs) %}
        L.control.scale({
            metric: true,
            imperial: false,
            position: "{{ this.position }}",
            maxWidth: {{ this.max_width }}
        }).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """)

    def __init__(self, position, max_width):
        super().__init__()
        self._name = "MetricScale"
        self.position = position
        self.max_width = max_width


def _add_scale(web_map, vc):
    """Ajoute la barre d'echelle metrique du cote oppose a la legende."""
    web_map.add_child(MetricScale(vc["scale_position"], vc["scale_max_width"]))


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
    ville, l'aire, la cote moyenne sur 100, la cote qualitative et le nombre de points. Le
    centroide est calcule dans le CRS projete puis ramene en degres, comme dans le tableau
    exporte, pour que le carre et la ligne du tableau tombent au meme endroit.
    """
    if sectors_gdf is None or len(sectors_gdf) == 0:
        return
    quality_colors = vc["quality_colors"]
    default_color = vc["color_residence_default"]
    group = folium.FeatureGroup(name=group_name)
    display = _to_display(sectors_gdf, geographic_crs)
    display["centroid"] = _to_display(
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
        lambda row: icons.get(row["service_type"], vc["icon_service_default"]),
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
        stop_field,
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
    mode_key = "map_subtitle_transit" if with_transit else "map_subtitle_walk"
    _add_title(web_map, vc["map_title"], vc[mode_key], vc)
    _add_legend(
        web_map,
        vc,
        vc["map_source_note"].format(crs=target_crs),
        with_transit,
        network_edges is not None and len(network_edges) > 0,
        water_gdf is not None and len(water_gdf) > 0,
    )
    _add_scale(web_map, vc)
    _save(web_map, path, logger)
