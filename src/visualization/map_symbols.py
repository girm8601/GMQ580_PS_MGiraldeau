"""Symboles ponctuels des cartes, construits en HTML.

Folium accepte un pictogramme HTML libre comme icone d'un repere. Ce module fabrique les
quatre formes du projet, la bulle ronde d'un arret ou d'une gare, l'epingle d'un service,
le carre d'un secteur retenu et la bulle numerotee d'un groupe de residences. Chaque forme
recoit sa couleur et sa taille de la section visualization de config.yaml, aucune valeur
n'est fixee ici.
"""

from __future__ import annotations

import json

import folium


def bubble(icon_class, bg_color, size_px, icon_ratio):
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


def pin(icon_class, color, size_px, icon_ratio):
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


def square(icon_class, color, size_px, icon_ratio, offset_px):
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


def cluster_icon_script(vc):
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
