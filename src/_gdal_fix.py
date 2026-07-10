"""Correctif de chargement de GDAL sous Windows.

Sur ce poste, un logiciel tiers (PCI Geomatics / CATALYST) place sa propre
version de GDAL sur le PATH et dans les variables d'environnement, ce qui
rend certains pilotes introuvables, dont GeoPackage. Ce module retire les
dossiers du logiciel tiers du PATH du processus puis redirige GDAL vers
l'environnement conda courant. Il doit etre importe AVANT toute
bibliotheque geospatiale, comme au TD2.
"""

from __future__ import annotations

import os

# Motifs des dossiers du logiciel tiers a ecarter du PATH du processus.
THIRD_PARTY_PATTERNS = ("PCI Geomatics", "CATALYST")

if os.name == "nt":
    entries = os.environ.get("PATH", "").split(os.pathsep)
    cleaned = [
        entry
        for entry in entries
        if not any(pattern.lower() in entry.lower() for pattern in THIRD_PARTY_PATTERNS)
    ]
    os.environ["PATH"] = os.pathsep.join(cleaned)

    # Les variables GDAL du logiciel tiers sont ecartees d'office.
    for variable in ("GDAL_DATA", "GDAL_DRIVER_PATH", "PROJ_LIB"):
        os.environ.pop(variable, None)

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        # Les DLL de l'environnement conda passent en tete de recherche.
        dll_folder = os.path.join(conda_prefix, "Library", "bin")
        if os.path.isdir(dll_folder):
            os.add_dll_directory(dll_folder)
            os.environ["PATH"] = dll_folder + os.pathsep + os.environ["PATH"]

        # Les donnees et pilotes GDAL de l'environnement conda prennent le relais.
        gdal_data = os.path.join(conda_prefix, "Library", "share", "gdal")
        if os.path.isdir(gdal_data):
            os.environ["GDAL_DATA"] = gdal_data
        proj_data = os.path.join(conda_prefix, "Library", "share", "proj")
        if os.path.isdir(proj_data):
            os.environ["PROJ_LIB"] = proj_data
        driver_folder = os.path.join(conda_prefix, "Library", "lib", "gdalplugins")
        if os.path.isdir(driver_folder):
            os.environ["GDAL_DRIVER_PATH"] = driver_folder
