"""Habillage cartographique des cartes, titre, legende et barre d'echelle.

Une carte thematique porte un titre, une legende, une echelle et une note de source, ce
sont les elements attendus par le cours. Ce module les dessine, la carte elle meme et ses
couches sont dans maps.py et map_layers.py.

La legende ne decrit que ce qui est reellement trace. Les reperes du transport n'y figurent
donc que sur la carte du transport, exactement comme sur la carte. Elle se place en bas a
gauche et l'echelle en bas a droite, les deux ne peuvent pas se couvrir. La fleche du nord
est inutile ici, le nord d'une carte web est toujours en haut.
"""

from __future__ import annotations

import folium
from branca.element import MacroElement
from jinja2 import Template


def add_title(web_map, title, subtitle, vc):
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


def add_legend(web_map, vc, source_note, with_transit, with_network, with_river):
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


def add_scale(web_map, vc):
    """Ajoute la barre d'echelle metrique du cote oppose a la legende."""
    web_map.add_child(MetricScale(vc["scale_position"], vc["scale_max_width"]))
