"""Graphiques statiques du projet avec matplotlib.

Chaque fonction ecrit une figure PNG dans le dossier de sorties. Les figures comparent
les aines et le reste de la population, cote a cote, chacun avec son propre ordre de
preference. Les textes des figures sont en francais comme tout le contenu affiche du
projet. Toutes les couleurs, tailles et textes viennent de la section visualization de
config.yaml.
"""

from __future__ import annotations

import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _save(figure, path, dpi, logger=None):
    """Ecrit la figure et cree le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    figure.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)
    if logger is not None:
        logger.info("Figure exportee, %s", path)


def coverage_chart(summary, config, path, logger=None):
    """Deux panneaux de couverture a pied, aines et reste, chacun par son importance.

    Chaque panneau range les services du plus important au moins important pour le groupe,
    comme l'ordre des infobulles des cartes. Les deux panneaux partagent la meme echelle
    horizontale, sinon l'ecart entre les deux groupes deviendrait invisible. Le seuil de
    chaque groupe figure dans le titre de son panneau, les deux ne sont pas les memes.
    summary vient de coverage_summary.
    """
    vc = config["visualization"]
    labels = vc["service_labels"]
    weighting_labels = vc["weighting_labels"]
    groups = [
        (
            "seniors",
            config["importance_seniors"],
            config["optimization"]["coverage_threshold_seniors_m"],
        ),
        (
            "rest",
            config["importance_rest"],
            config["optimization"]["coverage_threshold_rest_m"],
        ),
    ]
    width, height = vc["chart_figsize_bar"]
    figure, axes = plt.subplots(
        1, 2, figsize=(width * 2, height), layout="constrained", sharex=True
    )
    highest = 0.0
    for axis, (population, importance, threshold) in zip(axes, groups):
        subset = summary[
            (summary["population"] == population)
            & (summary["mode"] == "marche")
            & (summary["threshold_m"] == threshold)
        ].sort_values(
            "service_type",
            key=lambda col, weights=importance: col.map(lambda t: weights.get(t, 0.0)),
            kind="stable",
        )
        names = subset["service_type"].map(lambda t: labels.get(t, t))
        axis.barh(names, subset["covered_percent"], color=vc["color_chart_bar"])
        axis.set_xlabel(vc["label_chart_bar_xaxis"])
        axis.set_title(
            vc["title_coverage_panel"].format(
                group=weighting_labels.get(population, population),
                threshold=threshold,
            )
        )
        axis.grid(True, axis="x", alpha=vc["chart_grid_alpha"])
        highest = max(highest, float(subset["covered_percent"].max()))
    axes[0].set_xlim(0, math.ceil(highest / 10.0) * 10.0)
    figure.suptitle(vc["title_coverage"])
    _save(figure, path, vc["chart_dpi"], logger)


def gain_curve_chart(gains_df, config, path, logger=None):
    """Deux panneaux de gain, aines et reste, part couverte selon le nombre d'ajouts.

    Les deux panneaux gardent l'echelle verticale complete de la configuration. Une echelle
    resserree ferait paraitre le gain important alors que la validation montre l'inverse, il
    reste faible peu importe le nombre d'ajouts. gains_df contient n_services, group et
    weighted_covered_percent.
    """
    vc = config["visualization"]
    weighting_labels = vc["weighting_labels"]
    present = [w for w in ("seniors", "rest") if (gains_df["group"] == w).any()]
    width, height = vc["chart_figsize_gain"]
    n_panels = max(len(present), 1)
    figure, axes = plt.subplots(
        1,
        n_panels,
        squeeze=False,
        figsize=(width * n_panels, height),
        layout="constrained",
    )
    for axis, weighting in zip(axes[0], present):
        group = gains_df[gains_df["group"] == weighting].sort_values("n_services")
        axis.plot(
            group["n_services"],
            group["weighted_covered_percent"],
            marker=vc["chart_marker"],
        )
        axis.set_ylim(*vc["chart_gain_y_limits"])
        axis.set_xlabel(vc["label_chart_gain_xaxis"])
        axis.set_ylabel(vc["label_chart_gain_yaxis"])
        axis.set_title(weighting_labels.get(weighting, weighting))
        axis.grid(True, alpha=vc["chart_grid_alpha"])
    figure.suptitle(vc["title_chart_gain"])
    _save(figure, path, vc["chart_dpi"], logger)
