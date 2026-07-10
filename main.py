"""Pipeline complet du projet, de l'extraction aux resultats S0 et S1.

Le traitement suit l'ordre du schema du README. Les couches sont chargees,
auditees puis analysees sur la zone d'etude, les quatre municipalites
riveraines. La couverture actuelle S0 est mesuree de deux facons, par la
marche seule puis en ajoutant l'acces par le reseau de transport fixe. Les
scenarios S1 portent sur la marche seule et construisent un panier de
services a ajouter, chaque etape retenant le type et le site qui rapportent
le plus une fois ponderes par l'importance du service pour les aines, dans
une zone differente a chaque ajout. Lancement, python main.py, apres avoir
regenere les donnees avec download_data.py.
"""

from __future__ import annotations

from src import _gdal_fix  # noqa: F401  (corrige le chargement de GDAL, comme au TD2)

import os

import geopandas as gpd
import pandas as pd

from config_loader import load_config
from src.extraction.buildings import load_residences
from src.extraction.census import load_census_profile
from src.extraction.network import load_walk_graph
from src.extraction.reference_layers import (
    load_dissemination_areas,
    load_land_use,
    load_municipalities,
    load_water,
)
from src.extraction.services import load_services
from src.extraction.transit import load_bus_stops, load_train_lines, load_train_stations
from src.logger import setup_logger
from src.processing.accessibility import accessibility_table, total_score
from src.processing.candidate_sites import build_candidate_sites
from src.processing.coverage import coverage_by_area, total_coverage_rate
from src.processing.demand import extract_population, weight_demand
from src.processing.graph import distances_from_sources, nearest_graph_nodes
from src.processing.optimization import distance_matrix, gain_curve, solve_mclp
from src.processing.study_area import build_zone
from src.results.metrics import barrier_effect_table, export_table, s0_summary_table
from src.validation.audit import fix_invalid_geometries, run_audit
from src.validation.bridges import (
    classify_banks,
    crossing_report,
    find_crossing_edges,
    remove_crossing_edges,
)
from src.visualization.charts import gain_curve_chart, s0_coverage_chart
from src.visualization.maps import s0_map, s1_map


def processed_path(config, key):
    """Chemin d'une couche intermediaire dans data_processed."""
    return os.path.join(
        config["chemins"]["data_processed"],
        config["chemins"]["fichiers_processed"][key],
    )


def save_processed(gdf, config, key, logger):
    """Ecrit une couche intermediaire verifiable dans QGIS."""
    path = processed_path(config, key)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    gdf.to_file(path, driver="GPKG")
    logger.info("Couche intermediaire ecrite, %s, %d entite(s)", path, len(gdf))


def walking_cutoff(config):
    """Portee maximale de marche utile a tous les calculs de distance."""
    finite_scores = [
        threshold for threshold, _ in config["seuils_cote_m"] if threshold < 100000
    ]
    candidates = finite_scores + list(config["seuils_couverture_m"])
    candidates.append(config["transport"]["distance_max_arret_m"])
    candidates.append(config["optimisation"]["seuil_couverture_m"])
    return float(max(candidates))


def walk_edges_for_display(graph):
    """Reseau pietonnier simplifie pour l'affichage des cartes.

    Les deux sens de chaque troncon sont dedoublonnes et la geometrie est
    legerement simplifiee, ce qui allege beaucoup les fichiers HTML.
    """
    import osmnx as ox

    edges = ox.graph_to_gdfs(graph, nodes=False).reset_index()
    if {"u", "v"}.issubset(edges.columns):
        edges = edges[edges["u"] < edges["v"]]
    edges = edges[["geometry"]].copy()
    edges["geometry"] = edges.geometry.simplify(2)
    return edges


def load_all_layers(config, logger):
    """Charge toutes les couches du projet et retourne un dictionnaire."""
    municipalities = load_municipalities(config)
    study_zone = build_zone(municipalities, config)
    land_use = load_land_use(config)
    land_use, _ = fix_invalid_geometries(land_use, "utilisation_sol", logger)
    areas = load_dissemination_areas(config, study_zone)
    areas, _ = fix_invalid_geometries(areas, "aires_diffusion", logger)
    layers = {
        "municipalities": municipalities,
        "study_zone": study_zone,
        "land_use": land_use,
        "areas": areas,
        "census": load_census_profile(config, logger),
        "stops": load_bus_stops(config, logger),
        "stations": load_train_stations(config, logger),
        "lines": load_train_lines(config, logger),
        "graph": load_walk_graph(config, logger),
        "services": load_services(config, logger),
    }
    layers["residences"] = load_residences(config, land_use, logger)
    layers["water"] = load_water(config, study_zone, logger)

    # Les arrets hors de la zone d'etude sont ecartes, autrement un arret
    # lointain s'accroche au noeud de graphe le plus proche de la limite et
    # cree un faux point d'acces au transport.
    zone_union = study_zone.union_all()
    before = len(layers["stops"])
    layers["stops"] = layers["stops"][layers["stops"].within(zone_union)].copy()
    logger.info(
        "Arrets conserves dans la zone d'etude, %d sur %d",
        len(layers["stops"]),
        before,
    )

    # Les lignes de train sont decoupees a la zone pour ne pas deborder des cartes.
    layers["lines"] = gpd.clip(layers["lines"], study_zone)
    layers["lines"] = layers["lines"][~layers["lines"].geometry.is_empty].copy()
    return layers


def audit_all_layers(layers, config, logger):
    """Audite toutes les couches spatiales avant le moindre traitement."""
    crs = config["crs_cible"]
    zone = layers["study_zone"]
    name_field = config["zone_etude"]["champ_nom_municipalite"]
    join_field = config["vulnerabilite"]["champ_jointure_ad"]
    code_field = config["utilisation_sol"]["champ_code"]
    entries = [
        {
            "gdf": layers["municipalities"],
            "nom": "limites_municipales",
            "crs": crs,
            "champs_requis": [name_field],
        },
        {
            "gdf": layers["areas"],
            "nom": "aires_diffusion",
            "crs": crs,
            "champs_requis": [join_field],
            "zone": zone,
        },
        {
            "gdf": layers["land_use"],
            "nom": "utilisation_sol",
            "crs": crs,
            "champs_requis": [code_field],
            "zone": zone,
        },
        {"gdf": layers["stops"], "nom": "arrets_bus", "crs": crs, "zone": zone},
        {
            "gdf": layers["stations"],
            "nom": "gares_train",
            "crs": crs,
            "champs_requis": ["nom_gare"],
        },
        {
            "gdf": layers["lines"],
            "nom": "lignes_train",
            "crs": crs,
            "champs_requis": ["nom_train"],
        },
        {
            "gdf": layers["services"],
            "nom": "services_essentiels",
            "crs": crs,
            "champs_requis": ["service_type"],
            "zone": zone,
        },
        {"gdf": layers["residences"], "nom": "residences", "crs": crs, "zone": zone},
    ]
    run_audit(entries, config["chemins"]["audit_report"], logger)


def prepare_demand(layers, config, logger):
    """Pondere la demande et rattache chaque residence a son aire de diffusion."""
    join_field = config["vulnerabilite"]["champ_jointure_ad"]
    population = extract_population(layers["census"], config["vulnerabilite"])
    areas, _ = weight_demand(layers["areas"], population, join_field, logger)

    zone_union = layers["study_zone"].union_all()
    residences = layers["residences"]
    residences = residences[residences.within(zone_union)].copy()
    logger.info("Residences dans la zone d'etude, %d", len(residences))

    joined = gpd.sjoin(
        residences, areas[[join_field, "geometry"]], how="left", predicate="within"
    ).drop(columns="index_right")
    joined = joined[joined[join_field].notna()].copy()
    return areas, joined


def compute_distances(layers, residences, config, logger):
    """Calcule les distances de marche par type de service et vers le transport."""
    graph = layers["graph"]
    cutoff = walking_cutoff(config)
    residences = residences.copy()
    residences["node"] = nearest_graph_nodes(graph, residences)

    services = layers["services"].copy()
    services["node"] = nearest_graph_nodes(graph, services)

    access_points = pd.concat(
        [layers["stops"].geometry, layers["stations"].geometry], ignore_index=True
    )
    access_gdf = gpd.GeoDataFrame(geometry=access_points, crs=services.crs)
    access_nodes = list(nearest_graph_nodes(graph, access_gdf))

    distances_by_type = {}
    for service_type in config["services_essentiels"]:
        type_nodes = services.loc[services["service_type"] == service_type, "node"]
        reached = distances_from_sources(graph, list(type_nodes), cutoff=cutoff)
        distances_by_type[service_type] = {
            row.residence_id: reached.get(row.node) for row in residences.itertuples()
        }
        logger.info(
            "Distances calculees, %s, %d service(s)", service_type, len(type_nodes)
        )

    transit_reached = distances_from_sources(graph, access_nodes, cutoff=cutoff)
    transit_distances = {
        row.residence_id: transit_reached.get(row.node)
        for row in residences.itertuples()
    }
    return residences, services, distances_by_type, transit_distances, access_nodes


def transit_reachable_types(graph, services, access_nodes, config, logger):
    """Types de services atteignables en descendant a un point d'acces.

    Un type est accessible par le transport si au moins un arret ou une gare
    se trouve a distance de marche d'un service de ce type. Le reseau fixe
    local est traite comme un tout connecte, sans horaires ni correspondances,
    hypothese documentee au README.
    """
    max_walk = config["transport"]["distance_max_arret_m"]
    access_set = set(access_nodes)
    reachable = set()
    for service_type in config["services_essentiels"]:
        type_nodes = services.loc[services["service_type"] == service_type, "node"]
        reached = distances_from_sources(graph, list(type_nodes), cutoff=max_walk)
        if access_set & set(reached):
            reachable.add(service_type)
            logger.info("Type atteignable par le transport, %s", service_type)
    return reachable


def coverage_analysis(
    residences,
    areas,
    distances_by_type,
    transit_distances,
    reachable_types,
    config,
    logger,
):
    """Couverture S0 par type, par seuil et par mode, marche seule ou avec transport.

    Retourne le tableau de synthese, la part couverte par aire au seuil de
    l'optimisation pour chaque mode, et les drapeaux residentiels par mode
    qui servent de point de depart aux scenarios S1.
    """
    join_field = config["vulnerabilite"]["champ_jointure_ad"]
    thresholds = sorted(
        set(config["seuils_couverture_m"])
        | {config["optimisation"]["seuil_couverture_m"]}
    )
    optim_threshold = config["optimisation"]["seuil_couverture_m"]
    max_walk = config["transport"]["distance_max_arret_m"]

    residence_ids = list(residences["residence_id"])
    transit_ok = {
        rid: transit_distances.get(rid) is not None
        and transit_distances.get(rid) <= max_walk
        for rid in residence_ids
    }

    rates = []
    shares = {"marche": {}, "marche_transport": {}}
    flags = {"marche": {}, "marche_transport": {}}
    residence_table = residences[["residence_id", join_field]].copy()
    for service_type, distances in distances_by_type.items():
        type_by_transit = service_type in reachable_types
        for threshold in thresholds:
            walk_flags = [
                distances.get(rid) is not None and distances.get(rid) <= threshold
                for rid in residence_ids
            ]
            for mode in ("marche", "marche_transport"):
                if mode == "marche":
                    mode_flags = walk_flags
                else:
                    mode_flags = [
                        walked or (type_by_transit and transit_ok[rid])
                        for walked, rid in zip(walk_flags, residence_ids)
                    ]
                residence_table["couvert"] = mode_flags
                coverage = coverage_by_area(
                    residence_table, join_field, "couvert", areas, "aines"
                )
                rate = total_coverage_rate(coverage, "aines")
                rates.append(
                    {
                        "mode": mode,
                        "type_service": service_type,
                        "seuil_m": threshold,
                        "aines_couverts": round(
                            float(coverage["demande_couverte"].sum()), 1
                        ),
                        "aines_totaux": round(float(coverage["aines"].sum()), 1),
                        "taux": round(rate, 4),
                    }
                )
                if threshold == optim_threshold:
                    shares[mode][service_type] = coverage.set_index(join_field)[
                        "part_couverte"
                    ]
                    flags[mode][service_type] = list(mode_flags)
    logger.info("Couverture S0 calculee pour %d combinaisons", len(rates))
    return s0_summary_table(rates), shares, flags


def weighted_mean_shares(shares_by_type, importance):
    """Part couverte par aire, moyenne des types ponderee par leur importance."""
    total_weight = sum(importance.get(t, 1.0) for t in shares_by_type)
    combined = None
    for service_type, series in shares_by_type.items():
        term = series * importance.get(service_type, 1.0)
        combined = term if combined is None else combined.add(term, fill_value=0.0)
    return combined / total_weight


def barrier_analysis(layers, residences, services, config, logger):
    """Chiffre l'effet de barriere en coupant les liens qui traversent la riviere."""
    import osmnx as ox

    graph = layers["graph"]
    threshold = config["optimisation"]["seuil_couverture_m"]

    nodes_gdf = ox.graph_to_gdfs(graph, edges=False)
    banks = classify_banks(
        nodes_gdf,
        layers["municipalities"],
        config["zone_etude"]["rive_ouest"],
        config["zone_etude"]["rive_est"],
        config["zone_etude"]["champ_nom_municipalite"],
    )
    crossings = find_crossing_edges(graph, banks)
    report = crossing_report(graph, crossings)
    export_table(
        report,
        os.path.join(config["chemins"]["outputs_tables"], "ponts_traversants.csv"),
        logger,
    )
    logger.info("Liens traversant la riviere, %d", len(crossings))

    cut_graph = remove_crossing_edges(graph, crossings)
    node_by_residence = dict(zip(residences["residence_id"], residences["node"]))
    seniors_by_residence = dict(
        zip(residences["residence_id"], residences["aines_par_residence"])
    )
    with_bridges = {}
    without_bridges = {}
    for scenario, active_graph, target in (
        ("avec", graph, with_bridges),
        ("sans", cut_graph, without_bridges),
    ):
        for service_type in config["services_essentiels"]:
            type_nodes = services.loc[services["service_type"] == service_type, "node"]
            reached = distances_from_sources(
                active_graph, list(type_nodes), cutoff=threshold
            )
            covered_seniors = sum(
                seniors_by_residence[rid]
                for rid, node in node_by_residence.items()
                if reached.get(node) is not None
            )
            target[service_type] = round(float(covered_seniors), 1)
        logger.info("Scenario %s ponts evalue", scenario)
    return barrier_effect_table(with_bridges, without_bridges)


def optimization_analysis(layers, areas, coverage_shares, config, logger):
    """Optimisation S1 par type, courbes de gain sur la demande non couverte a pied.

    Le scenario S1 porte sur l'acces a pied seulement, la demande non
    couverte part donc du mode marche. Retourne aussi la matrice de
    distances et les points de demande pour la construction du panier mixte.
    """
    graph = layers["graph"]
    join_field = config["vulnerabilite"]["champ_jointure_ad"]
    threshold = float(config["optimisation"]["seuil_couverture_m"])

    candidates = build_candidate_sites(
        layers["land_use"], config, layers["study_zone"], None, logger
    )
    candidates["node"] = nearest_graph_nodes(graph, candidates)
    candidates = candidates.drop_duplicates(subset=["node"]).reset_index(drop=True)
    logger.info("Sites candidats apres regroupement par noeud, %d", len(candidates))

    demand_points = areas.copy()
    demand_points["geometry"] = demand_points.geometry.representative_point()
    demand_points["node"] = nearest_graph_nodes(graph, demand_points)

    matrix = distance_matrix(
        graph, list(candidates["node"]), list(demand_points["node"]), threshold
    )
    logger.info("Matrice de distances calculee, %d aires par %d sites", *matrix.shape)

    weight_columns = {"aines": "aines", "population_totale": "population_totale"}
    gains_frames = []
    for weighting in config["optimisation"]["ponderations"]:
        weight_column = weight_columns[weighting]
        for service_type, covered_share in coverage_shares.items():
            shares = demand_points[join_field].map(covered_share).fillna(0.0)
            uncovered_weights = demand_points[weight_column].values * (
                1.0 - shares.values
            )
            curve = gain_curve(
                matrix,
                uncovered_weights,
                threshold,
                config["optimisation"]["n_services_min"],
                config["optimisation"]["n_services_max"],
            )
            curve["type_service"] = service_type
            curve["ponderation"] = weighting
            gains_frames.append(curve)
            logger.info(
                "Optimisation resolue, %s, ponderation %s", service_type, weighting
            )
    gains = pd.concat(gains_frames, ignore_index=True)
    gains["demande_couverte"] = gains["demande_couverte"].round(1)
    return candidates, gains, matrix, demand_points


def s1_scenarios(
    layers,
    areas,
    residences,
    walk_flags,
    coverage_shares,
    candidates,
    matrix,
    demand_points,
    network_edges,
    config,
    logger,
):
    """Scenarios S1 en panier de services, un ajout optimal par etape, a pied.

    A chaque etape, chaque type de service est optimise separement, couverture
    maximale a un site sur la demande encore non couverte a pied, puis l'ajout
    retenu est celui qui rapporte le plus une fois pondere par l'importance du
    service pour les aines. Les sites deja choisis et leurs environs immediats
    (moins de la distance d'espacement configurée) sont ecartes des etapes suivantes, chaque ajout
    dessert donc une zone differente avec le service le plus pertinent pour
    cette zone. Chaque etape produit sa carte avec la couverture recalculee.
    """
    join_field = config["vulnerabilite"]["champ_jointure_ad"]
    threshold = float(config["optimisation"]["seuil_couverture_m"])
    spacing = float(config["optimisation"]["espacement_sites_m"])
    graph = layers["graph"]
    maps_folder = config["chemins"]["outputs_maps"]
    importance = config["importance_services"]
    icons = config["visualisation"]["icones_services"]
    types = list(config["services_essentiels"].keys())
    n_max = config["optimisation"]["n_services_max"]

    total_seniors = float(areas["aines"].sum())
    total_weight = sum(importance.get(t, 1.0) for t in types)
    residence_nodes = list(residences["node"])
    residence_table = residences[["residence_id", join_field]].copy()

    # Demande AD encore non couverte a pied par type, point de depart du panier.
    uncovered = {}
    for service_type in types:
        shares = (
            demand_points[join_field].map(coverage_shares[service_type]).fillna(0.0)
        )
        uncovered[service_type] = demand_points["aines"].values * (1.0 - shares.values)

    flags_now = {t: list(walk_flags[t]) for t in types}

    # Matrice de travail, les colonnes des zones deja servies seront fermees.
    out_of_reach = threshold * 10.0
    matrix_work = matrix.copy()

    def area_shares(service_type):
        """Part couverte par aire pour un type selon les drapeaux courants."""
        residence_table["couvert"] = flags_now[service_type]
        coverage = coverage_by_area(
            residence_table, join_field, "couvert", areas, "aines"
        )
        return coverage.set_index(join_field)["part_couverte"], float(
            coverage["demande_couverte"].sum()
        )

    def weighted_state():
        """Part ponderee par aire et taux global pondere de l'etat courant."""
        shares_by_type = {}
        weighted_covered = 0.0
        for service_type in types:
            shares, covered = area_shares(service_type)
            shares_by_type[service_type] = shares
            weighted_covered += importance.get(service_type, 1.0) * covered
        mean_shares = weighted_mean_shares(shares_by_type, importance)
        rate = weighted_covered / (total_weight * total_seniors)
        return mean_shares, rate

    _, initial_rate = weighted_state()
    summary_rows = [
        {
            "n_services": 0,
            "type_ajoute": "",
            "site_id": "",
            "aines_gagnes": 0.0,
            "taux_pondere": round(initial_rate, 4),
        }
    ]

    selected_rows = []
    for step in range(1, n_max + 1):
        best = None
        for service_type in types:
            if uncovered[service_type].sum() <= 0:
                continue
            sites_idx, covered = solve_mclp(
                matrix_work, uncovered[service_type], threshold, 1
            )
            score = importance.get(service_type, 1.0) * covered
            if best is None or score > best[0]:
                best = (score, service_type, sites_idx[0], covered)
        if best is None:
            logger.info("Plus aucune demande non couverte, arret a l'etape %d", step)
            break
        score, best_type, site_index, covered_raw = best
        site = candidates.iloc[site_index]
        selected_rows.append(
            {
                "ordre": step,
                "type_service": best_type,
                "site_id": int(site["site_id"]),
                "provenance": site["provenance"],
                "icone": icons.get(best_type, "fa-circle"),
                "recommandation": f"{best_type}, ajout numero {step}",
                "geometry": site.geometry,
            }
        )
        logger.info(
            "Etape %d, ajout retenu, %s au site %d, gain pondere %.1f",
            step,
            best_type,
            int(site["site_id"]),
            score,
        )

        # La demande couverte par ce site ne compte plus pour ce type.
        uncovered[best_type][matrix[:, site_index] <= threshold] = 0.0

        # Le site choisi et ses environs immediats sont fermes pour les
        # etapes suivantes, chaque ajout dessert une zone differente.
        nearby = candidates.geometry.distance(site.geometry) <= spacing
        matrix_work[:, nearby.values] = out_of_reach

        # Mise a jour des drapeaux residentiels du type ajoute.
        reached = distances_from_sources(graph, [site["node"]], cutoff=threshold)
        flags_now[best_type] = [
            flag or (reached.get(node) is not None)
            for flag, node in zip(flags_now[best_type], residence_nodes)
        ]

        mean_shares, rate = weighted_state()
        summary_rows.append(
            {
                "n_services": step,
                "type_ajoute": best_type,
                "site_id": int(site["site_id"]),
                "aines_gagnes": round(covered_raw, 1),
                "taux_pondere": round(rate, 4),
            }
        )

        if step in config["optimisation"]["cartes_aux_etapes"]:
            sites_gdf = gpd.GeoDataFrame(selected_rows, crs=candidates.crs)
            ad_scenario = areas.merge(
                mean_shares.rename("part_couverte_ponderee"),
                left_on=join_field,
                right_index=True,
                how="left",
            )
            ad_scenario["part_couverte_ponderee"] = ad_scenario[
                "part_couverte_ponderee"
            ].fillna(0.0)
            s1_map(
                layers["study_zone"],
                ad_scenario,
                "part_couverte_ponderee",
                f"Aînés couverts à pied (pondéré), {step} service(s) ajouté(s)",
                sites_gdf,
                network_edges,
                layers["water"],
                config["visualisation"],
                os.path.join(maps_folder, f"carte_s1_n{step}.html"),
                logger,
            )

    export_table(
        pd.DataFrame(summary_rows),
        os.path.join(config["chemins"]["outputs_tables"], "s1_couverture.csv"),
        logger,
    )
    sites_gdf = gpd.GeoDataFrame(selected_rows, crs=candidates.crs)
    return sites_gdf


def run_pipeline():
    """Enchaine toutes les etapes du pipeline et ecrit les sorties."""
    config = load_config()
    logger = setup_logger(config["chemins"]["log_file"])
    logger.info("Demarrage du pipeline")

    layers = load_all_layers(config, logger)
    audit_all_layers(layers, config, logger)

    areas, residences = prepare_demand(layers, config, logger)
    residences, services, distances_by_type, transit_distances, access_nodes = (
        compute_distances(layers, residences, config, logger)
    )

    # Aines repartis egalement entre les residences de chaque aire de diffusion.
    join_field = config["vulnerabilite"]["champ_jointure_ad"]
    counts = residences.groupby(join_field)["residence_id"].transform("count")
    seniors_by_area = residences[join_field].map(areas.set_index(join_field)["aines"])
    residences["aines_par_residence"] = (seniors_by_area / counts).fillna(0.0)

    # Cotes d'accessibilite par type et acces au transport.
    scores = accessibility_table(distances_by_type, config["seuils_cote_m"])
    scores = total_score(scores, list(config["services_essentiels"].keys()))
    scores["distance_transport"] = scores["place_id"].map(transit_distances)
    scores["acces_transport"] = scores["distance_transport"].le(
        config["transport"]["distance_max_arret_m"]
    )
    export_table(
        scores,
        os.path.join(config["chemins"]["outputs_tables"], "cotes_s0.csv"),
        logger,
    )

    # Couverture S0 selon les deux modes, marche seule et marche avec transport.
    reachable = transit_reachable_types(
        layers["graph"], services, access_nodes, config, logger
    )
    summary, shares, flags = coverage_analysis(
        residences,
        areas,
        distances_by_type,
        transit_distances,
        reachable,
        config,
        logger,
    )
    export_table(
        summary,
        os.path.join(config["chemins"]["outputs_tables"], "s0_couverture.csv"),
        logger,
    )
    s0_coverage_chart(
        summary[summary["mode"] == "marche"],
        config["optimisation"]["seuil_couverture_m"],
        os.path.join(config["chemins"]["outputs_figures"], "s0_couverture.png"),
        logger,
    )

    # Cartes S0 ponderees par l'importance. La carte marche seule ne montre
    # aucune couche de transport, la carte transport les montre toutes.
    importance = config["importance_services"]
    network_edges = walk_edges_for_display(layers["graph"])
    for mode, file_name, title, with_transit in (
        (
            "marche",
            "carte_s0_marche.html",
            "Aînés couverts (pondéré), marche seule",
            False,
        ),
        (
            "marche_transport",
            "carte_s0_transport.html",
            "Aînés couverts (pondéré), marche et transport collectif",
            True,
        ),
    ):
        mean_shares = weighted_mean_shares(shares[mode], importance)
        ad_mode = areas.merge(
            mean_shares.rename("part_couverte_ponderee"),
            left_on=join_field,
            right_index=True,
            how="left",
        )
        ad_mode["part_couverte_ponderee"] = ad_mode["part_couverte_ponderee"].fillna(
            0.0
        )
        s0_map(
            layers["study_zone"],
            ad_mode,
            "part_couverte_ponderee",
            title,
            network_edges,
            services,
            layers["stops"] if with_transit else None,
            layers["stations"] if with_transit else None,
            layers["lines"] if with_transit else None,
            layers["water"],
            config["visualisation"],
            os.path.join(config["chemins"]["outputs_maps"], file_name),
            logger,
        )

    # Effet de barriere de la riviere.
    barrier = barrier_analysis(layers, residences, services, config, logger)
    export_table(
        barrier,
        os.path.join(config["chemins"]["outputs_tables"], "effet_barriere.csv"),
        logger,
    )

    # Optimisation S1 a pied, courbes de gain par type puis panier mixte.
    candidates, gains, matrix, demand_points = optimization_analysis(
        layers, areas, shares["marche"], config, logger
    )
    export_table(
        gains.drop(columns="sites_choisis"),
        os.path.join(config["chemins"]["outputs_tables"], "gains_s1.csv"),
        logger,
    )
    gain_curve_chart(
        gains[gains["ponderation"] == "aines"],
        os.path.join(config["chemins"]["outputs_figures"], "courbe_gain.png"),
        logger,
    )
    recommended = s1_scenarios(
        layers,
        areas,
        residences,
        flags["marche"],
        shares["marche"],
        candidates,
        matrix,
        demand_points,
        network_edges,
        config,
        logger,
    )
    recommended_export = recommended.copy()
    recommended_export["x"] = recommended_export.geometry.x.round(1)
    recommended_export["y"] = recommended_export.geometry.y.round(1)
    export_table(
        pd.DataFrame(recommended_export.drop(columns=["geometry", "icone"])),
        os.path.join(config["chemins"]["outputs_tables"], "sites_recommandes.csv"),
        logger,
    )

    # Couches intermediaires verifiables dans QGIS.
    save_processed(residences, config, "residences", logger)
    save_processed(services, config, "services", logger)
    save_processed(layers["stops"], config, "arrets_bus", logger)
    save_processed(layers["stations"], config, "gares", logger)
    save_processed(areas, config, "aires_diffusion", logger)
    save_processed(candidates, config, "sites_candidats", logger)

    logger.info("Pipeline termine, sorties disponibles dans outputs")


if __name__ == "__main__":
    run_pipeline()
