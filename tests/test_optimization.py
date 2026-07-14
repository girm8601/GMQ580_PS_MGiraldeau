# Objectif, verifier la couverture maximale sur une matrice minuscule dont la
# solution optimale se voit a l'oeil nu, et la matrice de distances.

import numpy as np
import pytest

spopt = pytest.importorskip("spopt")

from src.processing.optimization import solve_mclp  # noqa: E402

# Trois candidats, quatre points de demande, seuil de 800 m.
# Le candidat 0 couvre les demandes 0 et 1, le candidat 1 couvre la demande 2,
# le candidat 2 couvre la demande 3 qui pese le plus lourd.
COST = np.array(
    [
        [500.0, 9999.0, 9999.0],
        [700.0, 9999.0, 9999.0],
        [9999.0, 400.0, 9999.0],
        [9999.0, 9999.0, 300.0],
    ]
)
WEIGHTS = [10.0, 10.0, 5.0, 30.0]


def test_single_service_picks_best_site():
    """Avec un seul service, le site couvrant la plus grande demande gagne."""
    selected, covered = solve_mclp(COST, WEIGHTS, 800.0, 1)
    assert selected == [2]
    assert covered == 30.0


def test_two_services_complete_coverage():
    """Avec deux services, le duo optimal couvre 50 personnes."""
    selected, covered = solve_mclp(COST, WEIGHTS, 800.0, 2)
    assert set(selected) == {0, 2}
    assert covered == 50.0
