"""Graphiques statiques du projet avec matplotlib.

Chaque fonction ecrit une figure PNG dans le dossier de sorties. Les textes des
figures sont en francais comme tout le contenu affiche du projet.
"""

from __future__ import annotations

import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

WEIGHTING_LABELS = {
    "seniors": "Aines",
    "population_total": "Population generale",
}


def _save(figure, path, logger=None):
    """Ecrit la figure et cree le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    if logger is not None:
        logger.info("Figure exportee, %s", path)


def _zoom_limits(values, margin=2.0):
    """Bornes verticales resserrees sur les valeurs utilisees, bornees de 0 a 100."""
    low = max(0.0, math.floor(min(values) - margin))
    high = min(100.0, math.ceil(max(values) + margin))
    if high <= low:
        high = low + 1.0
    return low, high


def gain_curve_chart(gains_df, path, logger=None):
    """Courbes de gain, part couverte selon le nombre de services ajoutes.

    gains_df contient les colonnes n_services, weighting et covered_percent. Une
    courbe est tracee par ponderation, aines et population generale. L'echelle
    verticale est resserree sur les valeurs utilisees pour rendre le gain visible.
    """
    figure, axis = plt.subplots(figsize=(8, 5))
    all_values = []
    for weighting, group in gains_df.groupby("weighting"):
        group = group.sort_values("n_services")
        all_values.extend(group["covered_percent"].tolist())
        axis.plot(
            group["n_services"],
            group["covered_percent"],
            marker="o",
            label=WEIGHTING_LABELS.get(weighting, weighting),
        )
    if all_values:
        axis.set_ylim(*_zoom_limits(all_values))
    axis.set_xlabel("Nombre de services ajoutes")
    axis.set_ylabel("Demande couverte (%)")
    axis.set_title("Gain de couverture selon le nombre de services ajoutes")
    axis.legend(title="Population")
    axis.grid(True, alpha=0.3)
    _save(figure, path, logger)


def s0_coverage_chart(summary_df, service_labels, title, path, logger=None):
    """Diagramme en barres de la couverture S0 par type de service.

    summary_df contient les colonnes service_type et covered_percent. Les noms de
    services sont affiches en francais.
    """
    subset = summary_df.sort_values("covered_percent").copy()
    subset["label"] = subset["service_type"].map(lambda t: service_labels.get(t, t))
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.barh(subset["label"], subset["covered_percent"], color="#185FA5")
    axis.set_xlabel("Demande couverte a pied (%)")
    axis.set_title(title)
    axis.grid(True, axis="x", alpha=0.3)
    _save(figure, path, logger)
