"""
Tests du module de dérive planning - Phase 3

Six tests couvrant les garanties fondamentales :

1. test_un_rapport_retourne_insuffisant
   — 1 seul rapport en base → risque='donnees_insuffisantes', pas de fausse tendance

2. test_zero_rapport_retourne_insuffisant
   — aucun rapport en base → même résultat

3. test_avancement_en_regression_retourne_eleve
   — avancement décroissant sur 20 jours (slope ≈ -0.3 %/j) → risque='eleve'

4. test_progression_rapide_retourne_faible
   — avancement 30 % → 60 % sur 30 jours (slope = 1.0 %/j) → risque='faible'

5. test_progression_lente_retourne_modere
   — avancement 30 % → 34 % sur 20 jours (slope = 0.2 %/j, peu de retards) → risque='modere'

6. test_projet_non_autorise_leve_permission_error
   — project_id absent de allowed_project_ids → PermissionError

Lancement : pytest tests/test_derive.py -v
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from derive_planning import calculer_derive, HISTORIQUE_MINIMUM
from security_context import RequestContext


# ---------- Helpers ----------

CONTEXT_KAN = RequestContext(
    authenticated_email="test@sofrecom.com",
    allowed_project_ids=["KAN"],
)


def _rapport(project_id: str, genere_le: str, avancement: float,
             en_retard: int = 0, total: int = 10) -> dict:
    """Construit un rapport minimal au format retourné par lister_rapports."""
    return {
        "_id": f"test-{project_id}-{genere_le}",
        "project": {"project_id": project_id, "nom_projet": f"Projet {project_id}"},
        "reporting_period": {"genere_le": genere_le},
        "kpis": [
            {"code": "avancement_pct",    "label": "Avancement", "valeur": avancement},
            {"code": "tickets_en_retard", "label": "En retard",  "valeur": float(en_retard)},
            {"code": "total_tickets",     "label": "Total",      "valeur": float(total)},
        ],
    }


# =========================================================
# Test 1 — Historique insuffisant : un seul rapport
# =========================================================

def test_un_rapport_retourne_insuffisant():
    """Un seul rapport en MongoDB → données_insuffisantes, jamais de tendance inventée."""
    rapports_mock = [
        _rapport("KAN", "2026-07-14", avancement=45.0),
    ]
    with patch("derive_planning.lister_rapports", return_value=rapports_mock), \
         patch("derive_planning.log_event"):
        resultat = calculer_derive("KAN", CONTEXT_KAN)

    assert resultat.risque == "donnees_insuffisantes"
    assert resultat.suffisant is False
    assert resultat.n_points == 1
    assert resultat.tendance_pct_par_jour is None
    assert resultat.jours_couverts is None
    assert str(HISTORIQUE_MINIMUM) in resultat.justification


# =========================================================
# Test 2 — Historique insuffisant : aucun rapport
# =========================================================

def test_zero_rapport_retourne_insuffisant():
    """Base MongoDB vide pour ce projet → données_insuffisantes sans planter."""
    with patch("derive_planning.lister_rapports", return_value=[]), \
         patch("derive_planning.log_event"):
        resultat = calculer_derive("KAN", CONTEXT_KAN)

    assert resultat.risque == "donnees_insuffisantes"
    assert resultat.suffisant is False
    assert resultat.n_points == 0
    assert resultat.avancement_actuel is None


# =========================================================
# Test 3 — Régression : avancement qui baisse → élevé
# =========================================================

def test_avancement_en_regression_retourne_eleve():
    """Avancement décroissant : 50 % → 47 % → 44 % sur 20 jours.
    slope ≈ -0.30 %/jour → risque élevé garanti."""
    # lister_rapports renvoie DESC (plus récent en premier)
    rapports_mock = [
        _rapport("KAN", "2026-07-14", avancement=44.0, en_retard=3, total=10),
        _rapport("KAN", "2026-07-04", avancement=47.0, en_retard=2, total=10),
        _rapport("KAN", "2026-06-24", avancement=50.0, en_retard=1, total=10),
    ]
    with patch("derive_planning.lister_rapports", return_value=rapports_mock), \
         patch("derive_planning.log_event"):
        resultat = calculer_derive("KAN", CONTEXT_KAN)

    assert resultat.risque == "eleve"
    assert resultat.suffisant is True
    assert resultat.tendance_pct_par_jour is not None
    assert resultat.tendance_pct_par_jour < 0, (
        f"La pente devrait être négative, obtenu : {resultat.tendance_pct_par_jour}"
    )


# =========================================================
# Test 4 — Progression rapide → faible
# =========================================================

def test_progression_rapide_retourne_faible():
    """Avancement 30 % → 45 % → 60 % sur 30 jours.
    slope = 1.0 %/jour → risque faible."""
    rapports_mock = [
        _rapport("KAN", "2026-07-01", avancement=60.0, en_retard=0, total=10),
        _rapport("KAN", "2026-06-16", avancement=45.0, en_retard=0, total=10),
        _rapport("KAN", "2026-06-01", avancement=30.0, en_retard=0, total=10),
    ]
    with patch("derive_planning.lister_rapports", return_value=rapports_mock), \
         patch("derive_planning.log_event"):
        resultat = calculer_derive("KAN", CONTEXT_KAN)

    assert resultat.risque == "faible"
    assert resultat.tendance_pct_par_jour is not None
    assert resultat.tendance_pct_par_jour >= 0.5, (
        f"La pente devrait être ≥ 0.5 %/j, obtenu : {resultat.tendance_pct_par_jour}"
    )
    # La justification doit citer la complétion estimée
    assert "jour" in resultat.justification.lower()


# =========================================================
# Test 5 — Progression lente → modéré
# =========================================================

def test_progression_lente_retourne_modere():
    """Avancement 30 % → 32 % → 34 % sur 20 jours.
    slope = 0.2 %/jour, peu de tickets en retard → risque modéré."""
    rapports_mock = [
        _rapport("KAN", "2026-07-10", avancement=34.0, en_retard=1, total=10),
        _rapport("KAN", "2026-06-30", avancement=32.0, en_retard=1, total=10),
        _rapport("KAN", "2026-06-20", avancement=30.0, en_retard=0, total=10),
    ]
    with patch("derive_planning.lister_rapports", return_value=rapports_mock), \
         patch("derive_planning.log_event"):
        resultat = calculer_derive("KAN", CONTEXT_KAN)

    assert resultat.risque == "modere"
    assert resultat.tendance_pct_par_jour is not None
    assert 0.1 <= resultat.tendance_pct_par_jour < 0.5, (
        f"Pente attendue entre 0.1 et 0.5, obtenu : {resultat.tendance_pct_par_jour}"
    )


# =========================================================
# Test 6 — Accès refusé → PermissionError
# =========================================================

def test_projet_non_autorise_leve_permission_error():
    """Un utilisateur n'ayant accès qu'à KAN ne peut pas obtenir la dérive
    d'un projet SECRET — PermissionError levée avant tout accès MongoDB."""
    context_kan_seulement = RequestContext(
        authenticated_email="test@sofrecom.com",
        allowed_project_ids=["KAN"],
    )
    with patch("derive_planning.lister_rapports") as mock_db, \
         patch("derive_planning.log_event"):
        with pytest.raises(PermissionError, match="SECRET"):
            calculer_derive("SECRET", context_kan_seulement)

    # MongoDB ne doit jamais avoir été consulté
    mock_db.assert_not_called()
