"""Graphiques statiques du projet avec matplotlib.

Chaque fonction ecrit une figure PNG dans le dossier de sorties. Les textes
des figures sont en francais comme tout le contenu du projet.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _save(figure, path, logger=None):
    """Ecrit la figure et cree le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    if logger is not None:
        logger.info("Figure exportee, %s", path)


def gain_curve_chart(gains_df, path, logger=None):
    """Courbe de gain, demande couverte selon le nombre de services ajoutes.

    gains_df contient les colonnes n_services, demande_couverte et
    type_service, une courbe par type.
    """
    figure, axis = plt.subplots(figsize=(8, 5))
    for service_type, group in gains_df.groupby("type_service"):
        group = group.sort_values("n_services")
        axis.plot(
            group["n_services"],
            group["demande_couverte"],
            marker="o",
            label=service_type,
        )
    axis.set_xlabel("Nombre de services ajoutes")
    axis.set_ylabel("Aines couverts apres ajout")
    axis.set_title("Gain de couverture selon le nombre de services ajoutes")
    axis.legend(title="Type de service")
    axis.grid(True, alpha=0.3)
    _save(figure, path, logger)


def s0_coverage_chart(summary_df, threshold_m, path, logger=None):
    """Diagramme en barres de la couverture S0 par type de service."""
    subset = summary_df[summary_df["seuil_m"] == threshold_m].sort_values("taux")
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.barh(subset["type_service"], 100.0 * subset["taux"])
    axis.set_xlabel(f"Aines couverts a {threshold_m} m de marche (%)")
    axis.set_title("Couverture actuelle S0 par type de service")
    axis.grid(True, axis="x", alpha=0.3)
    _save(figure, path, logger)
