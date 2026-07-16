"""
Tests du module teams_webhook — Volet 1 (notifications Power Automate / Teams)

Huit tests couvrant les quatre garanties fondamentales :

SILENCE EN CAS D'ÉCHEC
1. test_notification_ignoree_si_url_absente
   — TEAMS_WEBHOOK_URL absent → False, aucun appel HTTP
2. test_notification_silencieuse_si_erreur_reseau
   — requests.post lève ConnectionError → False, jamais d'exception
3. test_notification_silencieuse_si_http_400
   — Power Automate répond 400 → False, détail HTTP journalisé

ENVOI CORRECT
4. test_notification_envoyee_si_url_configuree
   — URL présente + HTTP 200 → True, requests.post appelé une fois
5. test_payload_contient_champ_text_et_kpis
   — le payload contient un champ "text" lisible + les champs KPI individuels
6. test_icone_rouge_si_tickets_critiques
   — tickets_critiques > 0 → l'icône 🔴 apparaît dans le texte
7. test_icone_logique
   — sans retards → 🟢 ; quelques retards → 🟡 ; critiques → 🔴

INTÉGRATION PIPELINE
8. test_pipeline_ne_plante_pas_si_webhook_echoue
   — si Teams est indisponible, executer_pipeline_complet ne plante pas
     et retourne ses fichiers normalement

Lancement : pytest tests/test_teams_webhook.py -v
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from security_context import RequestContext
from teams_webhook import (
    _construire_payload,
    _extraire_kpis,
    _icone_risque,
    envoyer_notification_rapport,
)

# ---------- Fixtures partagées ----------

CONTEXT_KAN = RequestContext(
    authenticated_email="testeur@sofrecom.com",
    allowed_project_ids=["KAN"],
)

PIVOT_TEST = {
    "project": {
        "project_id": "KAN",
        "nom_projet": "Projet KAN Demo",
    },
    "reporting_period": {
        "genere_le": "2026-07-15T10:00:00Z",
    },
    "kpis": [
        {"code": "avancement_pct",    "valeur": 42.0},
        {"code": "total_tickets",     "valeur": 10.0},
        {"code": "tickets_en_retard", "valeur": 2.0},
        {"code": "tickets_critiques", "valeur": 0.0},
    ],
    "tasks": [],
}

PIVOT_CRITIQUE = {
    **PIVOT_TEST,
    "kpis": [
        {"code": "avancement_pct",    "valeur": 20.0},
        {"code": "total_tickets",     "valeur": 10.0},
        {"code": "tickets_en_retard", "valeur": 4.0},
        {"code": "tickets_critiques", "valeur": 2.0},
    ],
}


def _mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "Accepted" if status_code in (200, 202) else "Bad Request"
    return resp


# =========================================================
# Test 1 — URL absente → pas d'appel HTTP
# =========================================================

def test_notification_ignoree_si_url_absente():
    """Si TEAMS_WEBHOOK_URL n'est pas défini, la fonction retourne False
    sans jamais appeler requests.post."""
    env_sans_url = {k: v for k, v in os.environ.items() if k != "TEAMS_WEBHOOK_URL"}
    with patch.dict(os.environ, env_sans_url, clear=True), \
         patch("teams_webhook.requests.post") as mock_post, \
         patch("teams_webhook.log_event"):

        resultat = envoyer_notification_rapport(PIVOT_TEST, CONTEXT_KAN)

    assert resultat is False
    mock_post.assert_not_called()


# =========================================================
# Test 2 — Erreur réseau → False, jamais d'exception
# =========================================================

def test_notification_silencieuse_si_erreur_reseau():
    """Un ConnectionError de requests ne doit jamais remonter :
    la fonction retourne False et journalise l'erreur."""
    import requests as req_mod

    with patch.dict(os.environ, {"TEAMS_WEBHOOK_URL": "https://logic.azure.com/hook"}), \
         patch("teams_webhook.requests.post",
               side_effect=req_mod.ConnectionError("hôte injoignable")), \
         patch("teams_webhook.log_event") as mock_log:

        resultat = envoyer_notification_rapport(PIVOT_TEST, CONTEXT_KAN)

    assert resultat is False
    mock_log.assert_called_once()
    call_kwargs = mock_log.call_args.kwargs
    assert call_kwargs.get("success") is False
    assert "réseau" in (call_kwargs.get("detail") or "").lower()


# =========================================================
# Test 3 — Réponse HTTP 400 → False, détail journalisé
# =========================================================

def test_notification_silencieuse_si_http_400():
    """Power Automate qui répond 400 (mauvais format JSON) → False,
    le code HTTP et la réponse sont journalisés."""
    with patch.dict(os.environ, {"TEAMS_WEBHOOK_URL": "https://logic.azure.com/hook"}), \
         patch("teams_webhook.requests.post",
               return_value=_mock_response(400)), \
         patch("teams_webhook.log_event") as mock_log:

        resultat = envoyer_notification_rapport(PIVOT_TEST, CONTEXT_KAN)

    assert resultat is False
    mock_log.assert_called_once()
    detail = mock_log.call_args.kwargs.get("detail", "") or ""
    assert "400" in detail


# =========================================================
# Test 4 — URL présente + HTTP 200 → True
# =========================================================

def test_notification_envoyee_si_url_configuree():
    """Quand TEAMS_WEBHOOK_URL est défini et que Power Automate répond 200,
    la fonction retourne True et appelle requests.post une seule fois."""
    with patch.dict(os.environ, {"TEAMS_WEBHOOK_URL": "https://logic.azure.com/hook"}), \
         patch("teams_webhook.requests.post",
               return_value=_mock_response(200)) as mock_post, \
         patch("teams_webhook.log_event") as mock_log:

        resultat = envoyer_notification_rapport(PIVOT_TEST, CONTEXT_KAN)

    assert resultat is True
    mock_post.assert_called_once()

    url_appelee = mock_post.call_args.args[0] if mock_post.call_args.args \
                  else mock_post.call_args.kwargs.get("url", "")
    assert "logic.azure.com" in url_appelee

    assert mock_log.call_args.kwargs.get("success") is True


# =========================================================
# Test 5 — Le payload contient "text" et les champs KPI
# =========================================================

def test_payload_contient_champ_text_et_kpis():
    """Le JSON envoyé à Power Automate doit contenir un champ 'text'
    prêt à l'emploi ET les champs KPI individuels pour un usage avancé."""
    payload_envoye: dict = {}

    def capturer_post(url, data, **kwargs):
        payload_envoye.update(json.loads(data))
        return _mock_response(200)

    with patch.dict(os.environ, {"TEAMS_WEBHOOK_URL": "https://logic.azure.com/hook"}), \
         patch("teams_webhook.requests.post", side_effect=capturer_post), \
         patch("teams_webhook.log_event"):

        envoyer_notification_rapport(PIVOT_TEST, CONTEXT_KAN)

    assert payload_envoye, "Aucun payload capturé"

    # Champ text lisible
    assert "text" in payload_envoye, "Le champ 'text' est obligatoire pour Power Automate"
    texte = payload_envoye["text"]
    assert "Projet KAN Demo" in texte, "Le nom du projet doit être dans le texte"
    assert "42.0" in texte,            "L'avancement doit être dans le texte"
    assert "2026-07-15" in texte,      "La date doit être dans le texte"

    # Champs individuels
    assert payload_envoye.get("project_id")  == "KAN"
    assert payload_envoye.get("avancement_pct") == 42.0
    assert payload_envoye.get("tickets_en_retard") == 2
    assert payload_envoye.get("tickets_critiques") == 0


# =========================================================
# Test 6 — Icône rouge si tickets critiques
# =========================================================

def test_icone_rouge_si_tickets_critiques():
    """Quand le pivot contient des tickets critiques, le texte du message
    doit commencer par l'icône 🔴 pour signaler le risque élevé."""
    payload_envoye: dict = {}

    def capturer_post(url, data, **kwargs):
        payload_envoye.update(json.loads(data))
        return _mock_response(200)

    with patch.dict(os.environ, {"TEAMS_WEBHOOK_URL": "https://logic.azure.com/hook"}), \
         patch("teams_webhook.requests.post", side_effect=capturer_post), \
         patch("teams_webhook.log_event"):

        envoyer_notification_rapport(PIVOT_CRITIQUE, CONTEXT_KAN)

    texte = payload_envoye.get("text", "")
    assert texte.startswith("🔴"), (
        f"L'icône rouge doit être en tête du message, obtenu : '{texte[:30]}'"
    )


# =========================================================
# Test 7 — Logique des icônes de risque
# =========================================================

def test_icone_logique():
    """Vérifie la logique de sélection d'icône sans appel réseau."""
    # Aucun retard → vert
    assert _icone_risque({"total_tickets": 10, "tickets_en_retard": 0,
                          "tickets_critiques": 0}) == "🟢"

    # Quelques retards (≤30 %) → orange
    assert _icone_risque({"total_tickets": 10, "tickets_en_retard": 2,
                          "tickets_critiques": 0}) == "🟡"

    # Taux de retard > 30 % → rouge
    assert _icone_risque({"total_tickets": 10, "tickets_en_retard": 4,
                          "tickets_critiques": 0}) == "🔴"

    # Tickets critiques → rouge (même si peu de retards)
    assert _icone_risque({"total_tickets": 10, "tickets_en_retard": 1,
                          "tickets_critiques": 1}) == "🔴"


# =========================================================
# Test 8 — Le pipeline ne plante pas si Teams échoue
# =========================================================

def test_pipeline_ne_plante_pas_si_webhook_echoue():
    """Si Power Automate est totalement indisponible, executer_pipeline_complet
    ne doit pas lever d'exception et doit retourner ses fichiers normalement."""
    import requests as req_mod

    pivot_bidon = MagicMock()
    pivot_bidon.model_dump_json.return_value = '{"project":{},"kpis":[],"tasks":[]}'
    pivot_bidon.model_dump.return_value = {
        "project": {"project_id": "KAN", "nom_projet": "KAN"},
        "reporting_period": {"genere_le": "2026-07-15"},
        "kpis": [],
        "tasks": [],
    }
    pivot_bidon.kpis = []

    with patch("main.agent_jira.JIRA_PROJECT_KEY", "KAN"), \
         patch("main.agent_jira.recuperer_nom_projet", return_value="KAN"), \
         patch("main.recuperer_tickets_jira", return_value=[]), \
         patch("main.mapper_ticket_vers_pivot", return_value=MagicMock()), \
         patch("main.calculer_kpis", return_value=[]), \
         patch("main.construire_objet_pivot", return_value=pivot_bidon), \
         patch("main.sauvegarder_pivot", return_value="fake-mongo-id"), \
         patch("main.generer_pptx"), \
         patch("main.generer_pdf"), \
         patch("main.log_event"), \
         patch("builtins.open", MagicMock()), \
         patch("teams_webhook.requests.post",
               side_effect=req_mod.ConnectionError("Power Automate indisponible")), \
         patch.dict(os.environ, {"TEAMS_WEBHOOK_URL": "https://logic.azure.com/hook"}):

        from main import executer_pipeline_complet
        ctx = RequestContext(
            authenticated_email="test@sofrecom.com",
            allowed_project_ids=["KAN"],
        )
        result = executer_pipeline_complet("KAN", context=ctx)

    assert "fichiers_generes" in result, (
        "Le pipeline doit retourner ses fichiers même si Power Automate échoue"
    )
