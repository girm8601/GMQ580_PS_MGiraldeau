# Objectif : verifier que config.yaml se charge, contient toutes les sections
# obligatoires et definit le bon CRS cible.

import pytest

from config_loader import ConfigError, load_config


def test_chargement_config_complete():
    """config.yaml doit se charger et definir le CRS cible EPSG:2950."""
    config = load_config("config.yaml")
    assert config["crs_cible"] == "EPSG:2950"
    assert "Beloeil" in config["zone_etude"]["municipalites"]


def test_fichier_introuvable():
    """Un chemin inexistant doit lever une erreur claire, pas un resultat vide."""
    with pytest.raises(ConfigError):
        load_config("chemin/inexistant.yaml")
