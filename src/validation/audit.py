"""Regles d'audit des donnees, le garde-fou du pipeline.

Chaque couche est verifiee avant tout traitement. Si une regle echoue, le
pipeline s'arrete avec une erreur claire plutot que de produire un resultat
spatialement faux. Chaque verification est journalisee puis ecrite dans un
rapport CSV, ce qui permet de retracer ce que la donnee a subi.
"""

from __future__ import annotations

import os

import pandas as pd


class AuditError(Exception):
    """Erreur levee quand au moins une couche ne respecte pas une regle d'audit."""


def check_crs(gdf, expected_crs):
    """Verifie que le CRS declare de la couche correspond au CRS attendu."""
    if gdf.crs is None:
        return False, "aucun CRS declare"
    declared = gdf.crs.to_string()
    if declared != expected_crs:
        return False, f"CRS declare {declared} au lieu de {expected_crs}"
    return True, f"CRS conforme ({expected_crs})"


def check_not_empty(gdf):
    """Verifie que la couche contient au moins une entite."""
    count = len(gdf)
    return count > 0, f"{count} entite(s)"


def check_valid_geometries(gdf):
    """Verifie que toutes les geometries non vides sont valides."""
    present = gdf.geometry.notna() & ~gdf.geometry.is_empty
    invalid_count = int((~gdf.geometry[present].is_valid).sum())
    return invalid_count == 0, f"{invalid_count} geometrie(s) invalide(s)"


def check_empty_geometries(gdf):
    """Verifie qu'aucune geometrie n'est vide ou absente."""
    empty_count = int((gdf.geometry.isna() | gdf.geometry.is_empty).sum())
    return empty_count == 0, f"{empty_count} geometrie(s) vide(s)"


def check_duplicates(gdf):
    """Verifie qu'aucune entite n'est dupliquee sur l'ensemble de ses colonnes."""
    duplicate_count = int(gdf.duplicated().sum())
    return duplicate_count == 0, f"{duplicate_count} doublon(s)"


def check_required_fields(gdf, required_fields):
    """Verifie que tous les champs necessaires a l'analyse sont presents."""
    missing = [field for field in required_fields if field not in gdf.columns]
    if missing:
        return False, "champs manquants " + ", ".join(missing)
    return True, "champs requis presents"


def check_zone_overlap(gdf, zone_gdf):
    """Verifie que la couche recouvre bien la zone d'etude."""
    zone_union = zone_gdf.union_all()
    overlap_count = int(gdf.intersects(zone_union).sum())
    return overlap_count > 0, f"{overlap_count} entite(s) dans la zone d'etude"


def check_bounds(gdf, zone_gdf):
    """Verifie que l'emprise de la couche recoupe celle de la zone d'etude.

    Cette regle attrape les coordonnees inversees et les valeurs aberrantes, qui donnent
    une emprise sans rapport avec le territoire etudie. Une couche peut avoir le bon CRS
    declare et se trouver quand meme a l'autre bout du monde.
    """
    minx, miny, maxx, maxy = gdf.total_bounds
    zminx, zminy, zmaxx, zmaxy = zone_gdf.total_bounds
    disjoint = maxx < zminx or minx > zmaxx or maxy < zminy or miny > zmaxy
    detail = (
        f"emprise {round(minx)} {round(miny)} {round(maxx)} {round(maxy)}, "
        f"zone {round(zminx)} {round(zminy)} {round(zmaxx)} {round(zmaxy)}"
    )
    return not disjoint, detail


def fix_invalid_geometries(gdf, layer_name, logger):
    """Corrige les geometries invalides avec buffer(0) et journalise la correction."""
    present = gdf.geometry.notna() & ~gdf.geometry.is_empty
    invalid_mask = present & ~gdf.geometry.is_valid
    fixed_count = int(invalid_mask.sum())
    if fixed_count > 0:
        gdf = gdf.copy()
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].buffer(0)
        logger.warning(
            "%s, correction buffer(0) appliquee a %d geometrie(s) invalide(s)",
            layer_name,
            fixed_count,
        )
    return gdf, fixed_count


def audit_layer(gdf, layer_name, expected_crs, required_fields=None, zone=None):
    """Applique toutes les regles d'audit a une couche et retourne les resultats."""
    rows = []

    def add(rule_name, passed, detail):
        rows.append(
            {
                "layer": layer_name,
                "rule": rule_name,
                "status": "ok" if passed else "echec",
                "detail": detail,
            }
        )

    add("expected_crs", *check_crs(gdf, expected_crs))
    add("not_empty", *check_not_empty(gdf))
    add("valid_geometries", *check_valid_geometries(gdf))
    add("no_empty_geometries", *check_empty_geometries(gdf))
    add("no_duplicates", *check_duplicates(gdf))
    if required_fields:
        add("required_fields", *check_required_fields(gdf, required_fields))
    if zone is not None:
        add("expected_bounds", *check_bounds(gdf, zone))
        add("zone_overlap", *check_zone_overlap(gdf, zone))
    return rows


def run_audit(entries, report_path, logger):
    """Audite toutes les couches, ecrit le rapport CSV et bloque en cas d'echec.

    Chaque entree est un dictionnaire avec les cles gdf, name, crs et, au besoin,
    required_fields et zone. Le rapport complet est toujours ecrit, meme en cas
    d'echec, pour que le probleme soit facile a retracer.
    """
    all_rows = []
    for entry in entries:
        all_rows.extend(
            audit_layer(
                entry["gdf"],
                entry["name"],
                entry["crs"],
                required_fields=entry.get("required_fields"),
                zone=entry.get("zone"),
            )
        )
    report = pd.DataFrame(all_rows)

    folder = os.path.dirname(report_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    report.to_csv(report_path, index=False, encoding="utf-8")

    for row in all_rows:
        if row["status"] == "echec":
            logger.error("Audit %s, %s, %s", row["layer"], row["rule"], row["detail"])
        else:
            logger.info("Audit %s, %s, %s", row["layer"], row["rule"], row["detail"])

    failure_count = int((report["status"] == "echec").sum())
    if failure_count > 0:
        raise AuditError(
            f"{failure_count} regle(s) d'audit en echec, voir le rapport {report_path}"
        )
    logger.info("Audit reussi, rapport ecrit dans %s", report_path)
    return report


def audit_all_layers(layers, config, logger):
    """Audite toutes les couches spatiales avant le moindre traitement."""
    crs = config["target_crs"]
    zone = layers["study_zone"]
    name_field = config["study_area"]["municipality_name_field"]
    join_field = config["vulnerability"]["ad_join_field"]
    station_field = config["transit"]["station_name_field"]
    line_field = config["transit"]["line_name_field"]
    entries = [
        {
            "gdf": layers["municipalities"],
            "name": "municipal_limits",
            "crs": crs,
            "required_fields": [name_field],
        },
        {
            "gdf": layers["areas"],
            "name": "dissemination_areas",
            "crs": crs,
            "required_fields": [join_field],
            "zone": zone,
        },
        {"gdf": layers["stops"], "name": "bus_stops", "crs": crs, "zone": zone},
        {
            "gdf": layers["stations"],
            "name": "train_stations",
            "crs": crs,
            "required_fields": [station_field],
        },
        {
            "gdf": layers["lines"],
            "name": "train_lines",
            "crs": crs,
            "required_fields": [line_field],
        },
        {
            "gdf": layers["services"],
            "name": "essential_services",
            "crs": crs,
            "required_fields": ["service_type"],
            "zone": zone,
        },
        {"gdf": layers["residences"], "name": "residences", "crs": crs, "zone": zone},
    ]
    if layers.get("water") is not None:
        entries.append({"gdf": layers["water"], "name": "water", "crs": crs})
    for key in ("commercial", "development", "residential"):
        if layers.get(key) is not None:
            entries.append({"gdf": layers[key], "name": key, "crs": crs, "zone": zone})
    run_audit(entries, config["paths"]["audit_report"], logger)
