"""Resultats chiffres du projet, tableaux exportes en CSV.

Ce module ne calcule rien de spatial, il met en forme et exporte les resultats
produits par les modules d'analyse, pour le rapport et la presentation orale.
"""

from __future__ import annotations

import os

import pandas as pd


def export_table(df, path, logger=None):
    """Ecrit un tableau CSV en creant le dossier au besoin."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    if logger is not None:
        logger.info("Tableau exporte, %s, %d ligne(s)", path, len(df))


def s0_summary_table(coverage_rows):
    """Met en forme la couverture S0 par type de service, par mode et par seuil.

    coverage_rows est une liste de dictionnaires avec le mode, le type de service,
    le seuil en metres, la demande couverte et le taux.
    """
    table = pd.DataFrame(coverage_rows)
    return table.sort_values(["mode", "threshold_m", "service_type"]).reset_index(
        drop=True
    )


def barrier_effect_table(with_bridges, without_bridges):
    """Compare la couverture des aines avec et sans franchissement de la riviere.

    Les deux entrees associent chaque type de service a sa demande couverte.
    L'ecart chiffre l'effet de barriere de la riviere Richelieu, qui reste faible.
    """
    rows = []
    for service_type, covered in with_bridges.items():
        covered_cut = without_bridges.get(service_type, 0.0)
        rows.append(
            {
                "service_type": service_type,
                "covered_with_bridges": covered,
                "covered_without_bridges": covered_cut,
                "barrier_effect": covered - covered_cut,
            }
        )
    return pd.DataFrame(rows).sort_values("barrier_effect", ascending=False)
