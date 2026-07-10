"""Chargement et validation du fichier de configuration YAML.

Ce module lit config.yaml, verifie la presence des sections essentielles,
puis retourne un dictionnaire pret a l'emploi pour le reste du pipeline.
Toute erreur de configuration est signalee tot et clairement, avant le
moindre acces aux donnees. Aucun parametre n'est ainsi code en dur dans
les scripts.
"""

from __future__ import annotations

import os

import yaml


class ConfigError(Exception):
    """Erreur levee lorsqu'un parametre de configuration est absent ou invalide."""


# Sections de premier niveau obligatoires dans config.yaml.
REQUIRED_KEYS = [
    "crs_cible",
    "crs_sources",
    "zone_etude",
    "seuils_couverture_m",
    "seuils_cote_m",
    "transport",
    "vulnerabilite",
    "services_essentiels",
    "utilisation_sol",
    "optimisation",
    "chemins",
]


def load_config(path: str = "config.yaml") -> dict:
    """Charge, valide et retourne la configuration du pipeline.

    Parametres
    ----------
    path : chemin vers le fichier YAML de configuration.

    Retour : dictionnaire de configuration valide.

    Leve : ConfigError si le fichier est introuvable, illisible ou incomplet.
    """
    # --- Lecture du fichier YAML ---------------------------------------
    if not os.path.exists(path):
        raise ConfigError(f"Fichier de configuration introuvable : {path}")
    try:
        with open(path, encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except yaml.YAMLError as err:
        raise ConfigError(f"YAML invalide dans {path} : {err}") from err

    if not isinstance(config, dict):
        raise ConfigError("Le fichier de configuration est vide ou mal forme.")

    # --- Validations successives ---------------------------------------
    _check_required_keys(config)
    _check_crs(config)
    _check_study_area(config)

    return config


def _check_required_keys(config: dict) -> None:
    """Verifie que toutes les sections obligatoires sont presentes."""
    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        raise ConfigError(
            "Sections manquantes dans config.yaml : " + ", ".join(missing)
        )


def _check_crs(config: dict) -> None:
    """Verifie que le CRS cible est une chaine de la forme EPSG:XXXX."""
    crs = config["crs_cible"]
    if not isinstance(crs, str) or not crs.startswith("EPSG:"):
        raise ConfigError(
            f"crs_cible doit etre une chaine de la forme 'EPSG:XXXX', recu : {crs}"
        )


def _check_study_area(config: dict) -> None:
    """Verifie que la zone d'etude contient au moins une municipalite."""
    study_area = config["zone_etude"]
    municipalities = study_area.get("municipalites")
    if not isinstance(municipalities, list) or not municipalities:
        raise ConfigError(
            "zone_etude.municipalites doit contenir au moins une municipalite."
        )
