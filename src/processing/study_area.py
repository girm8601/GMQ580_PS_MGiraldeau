"""Delimitation de la zone d'etude.

La zone d'etude couvre les quatre municipalites riveraines contigues,
Beloeil, Mont-Saint-Hilaire, McMasterville et Otterburn Park. La demande,
les services, le reseau et le transport y sont tous mesures, sans zone
tampon, decision documentee au README.
"""

from __future__ import annotations


def select_municipalities(municipalities_gdf, names, name_field):
    """Retourne les municipalites demandees, avec une erreur claire si absentes."""
    selected = municipalities_gdf[municipalities_gdf[name_field].isin(names)]
    found = set(selected[name_field])
    missing = [name for name in names if name not in found]
    if missing:
        raise ValueError(
            "Municipalites introuvables dans les limites, " + ", ".join(missing)
        )
    return selected.copy()


def build_zone(municipalities_gdf, config):
    """Construit la zone d'etude, un GeoDataFrame a une seule entite."""
    name_field = config["zone_etude"]["champ_nom_municipalite"]
    names = config["zone_etude"]["municipalites"]
    selected = select_municipalities(municipalities_gdf, names, name_field)
    return selected.dissolve()[["geometry"]]
