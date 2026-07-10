"""Resultats chiffres du projet, tableaux exportes en CSV.

Ce module ne calcule rien de spatial, il met en forme et exporte les
resultats produits par les modules d'analyse, pour le rapport et la
presentation orale.
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


def s0_summary_table(coverage_rates):
    """Met en forme la couverture S0 par type de service et par seuil.

    coverage_rates est une liste de dictionnaires avec type de service,
    seuil en metres, demande couverte, demande totale et taux.
    """
    table = pd.DataFrame(coverage_rates)
    return table.sort_values(["seuil_m", "type_service"]).reset_index(drop=True)


def barrier_effect_table(with_bridges, without_bridges):
    """Compare la couverture avec et sans franchissement de la riviere.

    Les deux entrees associent chaque type de service a sa demande couverte.
    L'ecart chiffre l'effet de barriere de la riviere Richelieu.
    """
    rows = []
    for service_type, covered in with_bridges.items():
        covered_cut = without_bridges.get(service_type, 0.0)
        rows.append(
            {
                "type_service": service_type,
                "demande_couverte_avec_ponts": covered,
                "demande_couverte_sans_ponts": covered_cut,
                "effet_barriere": covered - covered_cut,
            }
        )
    return pd.DataFrame(rows).sort_values("effet_barriere", ascending=False)
