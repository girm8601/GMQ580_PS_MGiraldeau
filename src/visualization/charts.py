"""Graphiques statiques du projet avec matplotlib.

Chaque fonction ecrit une figure PNG dans le dossier de sorties. Les textes des
figures sont en francais comme tout le contenu affiche du projet. Toutes les
couleurs, tailles et textes viennent de la section visualization de config.yaml.
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


def _zoom_limits(values, margin):
    """Bornes verticales resserrees sur les valeurs utilisees, bornees de 0 a 100."""
    low = max(0.0, math.floor(min(values) - margin))
    high = min(100.0, math.ceil(max(values) + margin))
    if high <= low:
        high = low + 1.0
    return low, high


def gain_curve_chart(gains_df, path, visual_config, logger=None):
    """Courbes de gain, part couverte selon le nombre de services ajoutes.

    gains_df contient les colonnes n_services, weighting et covered_percent. Une
    courbe est tracee par ponderation, aines et population generale. L'echelle
    verticale est resserree sur les valeurs utilisees pour rendre le gain visible.
    """
    vc = visual_config
    weighting_labels = vc["weighting_labels"]
    figure, axis = plt.subplots(figsize=tuple(vc["chart_figsize_gain"]))
    all_values = []
    for weighting, group in gains_df.groupby("weighting"):
        group = group.sort_values("n_services")
        all_values.extend(group["covered_percent"].tolist())
        axis.plot(
            group["n_services"],
            group["covered_percent"],
            marker=vc["chart_marker"],
            label=weighting_labels.get(weighting, weighting),
        )
    if all_values:
        axis.set_ylim(*_zoom_limits(all_values, vc["chart_zoom_margin"]))
    axis.set_xlabel(vc["label_chart_gain_xaxis"])
    axis.set_ylabel(vc["label_chart_gain_yaxis"])
    axis.set_title(vc["title_chart_gain"])
    axis.legend(title=vc["label_chart_gain_legend"])
    axis.grid(True, alpha=vc["chart_grid_alpha"])
    _save(figure, path, vc["chart_dpi"], logger)


def s0_coverage_chart(
    summary_df, service_labels, title, path, visual_config, logger=None
):
    """Diagramme en barres de la couverture S0 par type de service.

    summary_df contient les colonnes service_type et covered_percent. Les noms de
    services sont affiches en francais.
    """
    vc = visual_config
    subset = summary_df.sort_values("covered_percent").copy()
    subset["label"] = subset["service_type"].map(lambda t: service_labels.get(t, t))
    figure, axis = plt.subplots(figsize=tuple(vc["chart_figsize_bar"]))
    axis.barh(subset["label"], subset["covered_percent"], color=vc["color_chart_bar"])
    axis.set_xlabel(vc["label_chart_bar_xaxis"])
    axis.set_title(title)
    axis.grid(True, axis="x", alpha=vc["chart_grid_alpha"])
    _save(figure, path, vc["chart_dpi"], logger)
