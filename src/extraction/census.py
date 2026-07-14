"""Lecture du profil du recensement 2021 par aire de diffusion.

Le fichier provincial fait plusieurs gigaoctets, il est donc lu par morceaux et
filtre au vol sur les deux caracteristiques utiles, la population totale et les
65 ans et plus. Le resultat filtre est mis en cache dans data_processed pour que
les executions suivantes soient rapides. L'encodage latin-1 vient de la
configuration, comme documente dans la fiche d'audit.
"""

from __future__ import annotations

import os

import pandas as pd


def _cache_path(config):
    """Chemin du profil filtre mis en cache dans data_processed."""
    return os.path.join(
        config["paths"]["data_processed"],
        config["paths"]["processed_files"]["census_profile"],
    )


def load_census_profile(config, logger=None):
    """Charge les lignes utiles du profil, depuis le cache s'il existe.

    Seules les colonnes necessaires sont conservees, la cle de jointure,
    l'identifiant de caracteristique et la valeur totale. Supprimer le fichier
    cache force une relecture complete du fichier source.
    """
    vulnerability = config["vulnerability"]
    join_field = vulnerability["ad_join_field"]
    id_field = vulnerability["characteristic_column"]
    value_field = vulnerability["value_column"]

    cache = _cache_path(config)
    if os.path.exists(cache):
        profile = pd.read_csv(cache, dtype={join_field: str})
        if logger is not None:
            logger.info("Profil charge depuis le cache, %d lignes", len(profile))
        return profile

    path = os.path.join(
        config["paths"]["data_raw"],
        config["paths"]["manual_files"]["census_profile"],
    )
    wanted_ids = [
        vulnerability["total_population_id"],
        vulnerability["characteristic_id"],
    ]
    chunks = []
    reader = pd.read_csv(
        path,
        encoding=vulnerability["csv_encoding"],
        usecols=[join_field, id_field, value_field],
        dtype={join_field: str},
        chunksize=500_000,
        low_memory=False,
    )
    for chunk in reader:
        chunks.append(chunk[chunk[id_field].isin(wanted_ids)])
    profile = pd.concat(chunks, ignore_index=True)

    folder = os.path.dirname(cache)
    if folder:
        os.makedirs(folder, exist_ok=True)
    profile.to_csv(cache, index=False, encoding="utf-8")
    if logger is not None:
        logger.info(
            "Profil du recensement filtre, %d lignes utiles, cache ecrit dans %s",
            len(profile),
            cache,
        )
    return profile
