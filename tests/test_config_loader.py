# Objectif, verifier que config.yaml se charge, contient toutes les sections
# obligatoires et definit le bon CRS cible.

import pytest

from config_loader import ConfigError, load_config


def test_config_loads_completely():
    """config.yaml doit se charger et definir le CRS cible EPSG:2950."""
    config = load_config("config.yaml")
    assert config["target_crs"] == "EPSG:2950"
    assert "Beloeil" in config["study_area"]["municipalities"]


def test_missing_file_raises():
    """Un chemin inexistant doit lever une erreur claire, pas un resultat vide."""
    with pytest.raises(ConfigError):
        load_config("chemin/inexistant.yaml")
