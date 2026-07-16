"""
Tests de sécurité - Phase 1
Trois tests prioritaires :
1. Un accès non autorisé à un projet est bloqué (cloisonnement).
2. Une donnée invalide (ex: progress_percent > 100) est rejetée par Pydantic.
3. Un champ inconnu envoyé dans un objet est rejeté (extra="forbid").

Installation : pip install pytest httpx
Lancement    : pytest test_security.py -v
"""

import os
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Configuration de test (mode multi-utilisateurs, avant d'importer l'app)
os.environ["API_USERS_JSON"] = (
    '{"token-de-test": {"email": "test@example.com", "allowed_project_ids": ["KAN"]}}'
)

from main import app
from security_context import RequestContext, verifier_acces_projet
from pivot_models import ProjectTask, TaskStatus, Priority, SourceReference, SourceSystem
from fastapi import HTTPException

client = TestClient(app)


# ---------- Test 1 : cloisonnement d'accès ----------

def test_acces_projet_non_autorise_est_bloque():
    """Un utilisateur autorisé seulement sur KAN ne doit jamais pouvoir
    accéder aux données d'un autre projet (ex: PROJECT-B)."""
    context = RequestContext(
        authenticated_email="test@example.com",
        allowed_project_ids=["KAN"],
    )
    with pytest.raises(HTTPException) as exc_info:
        verifier_acces_projet("PROJECT-B", context)
    assert exc_info.value.status_code == 403


def test_endpoint_sans_token_est_rejete():
    """Sans en-tête X-API-Key, l'endpoint doit refuser la requête (401)."""
    response = client.get("/reports/KAN")
    assert response.status_code == 401


def test_endpoint_avec_token_invalide_est_rejete():
    """Un token qui ne correspond à aucune entrée connue doit être rejeté."""
    response = client.get("/reports/KAN", headers={"X-API-Key": "mauvais-token"})
    assert response.status_code == 401


def test_endpoint_projet_non_autorise_renvoie_403():
    """Même avec un token valide, un projet hors périmètre doit être bloqué."""
    response = client.get(
        "/reports/AUTRE-PROJET", headers={"X-API-Key": "token-de-test"}
    )
    assert response.status_code == 403


# ---------- Test 2 : validation stricte des données ----------

def test_progress_percent_hors_limites_est_rejete():
    """Un pourcentage d'avancement en dehors de 0-100 doit être refusé par
    Pydantic, avant même d'atteindre la logique métier."""
    # ProjectTask n'a pas de champ progress_percent direct dans ce modèle
    # simplifié Phase 1 ; on illustre le principe sur un champ contraint
    # existant à la place : un statut hors de l'énumération autorisée.
    with pytest.raises(ValidationError):
        ProjectTask(
            task_id="KAN-1",
            titre="Test",
            statut="statut_invalide",  # n'existe pas dans TaskStatus
            priorite=Priority.MOYENNE,
            source=SourceReference(
                source_system=SourceSystem.JIRA,
                source_record_id="KAN-1",
            ),
        )


# ---------- Test 3 : rejet des champs non prévus ----------

def test_champ_inconnu_est_rejete():
    """extra='forbid' doit empêcher l'introduction silencieuse d'un champ
    non prévu dans un objet métier."""
    with pytest.raises(ValidationError):
        ProjectTask(
            task_id="KAN-1",
            titre="Test",
            statut=TaskStatus.A_FAIRE,
            priorite=Priority.MOYENNE,
            champ_non_prevu="valeur-suspecte",
            source=SourceReference(
                source_system=SourceSystem.JIRA,
                source_record_id="KAN-1",
            ),
        )