"""Configuration de la journalisation du pipeline.

Fournit un logger unique qui ecrit a la fois dans la console et dans un
fichier de journal (principe du cours : logger, ne pas afficher). La
journalisation permet de suivre l'avancement du pipeline et de retracer
toute correction automatique appliquee aux donnees.
"""

from __future__ import annotations

import logging
import os


def setup_logger(
    log_file: str = "logs/pipeline.log", level: str = "INFO"
) -> logging.Logger:
    """Cree et retourne le logger du pipeline.

    Parametres
    ----------
    log_file : chemin du fichier de journal (le dossier est cree au besoin).
    level : niveau de journalisation ("DEBUG", "INFO", "WARNING", ...).

    Retour : instance de logging.Logger configuree.
    """
    logger = logging.getLogger("gmq580_ps")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # On evite d'ajouter plusieurs fois les memes gestionnaires si la fonction
    # est appelee a nouveau.
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    # Sortie console.
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    # Sortie fichier (encodage UTF-8 pour les accents francais).
    folder = os.path.dirname(log_file)
    if folder:
        os.makedirs(folder, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
