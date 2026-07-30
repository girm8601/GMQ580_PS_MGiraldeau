# Objectif, verifier la couverture maximale sur une matrice minuscule dont la
# solution optimale se voit a l'oeil nu, et la matrice de distances.

import numpy as np
import pytest

from src.processing.optimization import solve_mclp

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
    pytest.importorskip("spopt")
    selected, covered = solve_mclp(COST, WEIGHTS, 800.0, 1)
    assert selected == [2]
    assert covered == 30.0


def test_two_services_complete_coverage():
    """Avec deux services, le duo optimal couvre 50 personnes."""
    pytest.importorskip("spopt")
    selected, covered = solve_mclp(COST, WEIGHTS, 800.0, 2)
    assert set(selected) == {0, 2}
    assert covered == 50.0


def test_simultaneous_choice_beats_the_greedy_one():
    """Placer deux sites d'un coup peut battre deux choix successifs.

    C'est la raison d'etre de la borne superieure du volet validation. Ici le site 0 est le
    plus payant tout seul, mais le duo optimal est 1 et 2. Un choix glouton qui garderait 0
    resterait donc sous l'optimum.
    """
    pytest.importorskip("spopt")
    cost = np.array(
        [
            [500.0, 400.0, 9999.0],
            [500.0, 9999.0, 400.0],
            [9999.0, 400.0, 9999.0],
            [9999.0, 9999.0, 400.0],
        ]
    )
    weights = [10.0, 10.0, 8.0, 8.0]
    first, _ = solve_mclp(cost, weights, 800.0, 1)
    assert first == [0]
    both, covered = solve_mclp(cost, weights, 800.0, 2)
    assert set(both) == {1, 2}
    assert covered == 36.0
