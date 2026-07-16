"""
Tests du module de recommandations - Phase 3

Six tests couvrant les quatre garanties fondamentales :

ACCÈS
1. test_projet_non_autorise_leve_permission_error
   — PermissionError levée avant tout appel Ollama

ISOLATION DU LLM
2. test_prompt_ne_contient_aucun_email
   — le prompt envoyé à Ollama ne contient aucune adresse email,
     même si un label KPI en contenait une
3. test_prompt_contient_kpis_precalcules
   — les valeurs KPI calculées par Pandas figurent explicitement dans le prompt
4. test_prompt_contient_niveau_risque_derive
   — le niveau de risque calculé par derive_planning est transmis au LLM

VALIDATION HUMAINE
5. test_recommandation_generee_a_approuvee_false
   — approuvee=False par défaut — elle n'est jamais affichée sans validation
6. test_valider_cli_operateur_approuve
   — opérateur répond "o" → approuvee=True
7. test_valider_cli_operateur_rejete
   — opérateur répond "n" → approuvee=False (ne sera jamais affichée)

Lancement : pytest tests/test_recommandations.py -v
"""

import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from derive_planning import PrevisionDerive, PointHistorique
from recommandations_service import (
    Recommandation,
    _construire_prompt,
    generer_recommandation,
    valider_recommandation_cli,
)
from security_context import RequestContext

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# ---------- Fixtures partagées ----------

CONTEXT_KAN = RequestContext(
    authenticated_email="testeur@sofrecom.com",
    allowed_project_ids=["KAN"],
)

KPIS_TEST = [
    {"code": "avancement_pct",    "label": "Avancement global",          "valeur": 34.0, "unite": "%"},
    {"code": "total_tickets",     "label": "Nombre total de tickets",    "valeur": 10.0},
    {"code": "tickets_en_retard", "label": "Tickets en retard",          "valeur": 1.0},
    {"code": "tickets_en_cours",  "label": "Tickets en cours",           "valeur": 3.0},
    {"code": "tickets_critiques", "label": "Tickets priorité critique",  "valeur": 0.0},
]

PREVISION_MODERE = PrevisionDerive(
    project_id="KAN",
    suffisant=True,
    n_points=3,
    risque="modere",
    tendance_pct_par_jour=0.2,
    avancement_actuel=34.0,
    avancement_initial=30.0,
    jours_couverts=20,
    justification=(
        "Progression moderee : 0.200%/jour sur 20 jour(s) "
        "(30.0% -> 34.0%). Completion estimee dans ~330 jour(s). "
        "1/10 ticket(s) en retard."
    ),
    points=[],
)

PREVISION_ELEVE = PrevisionDerive(
    project_id="KAN",
    suffisant=True,
    n_points=3,
    risque="eleve",
    tendance_pct_par_jour=-0.3,
    avancement_actuel=44.0,
    avancement_initial=50.0,
    jours_couverts=20,
    justification=(
        "Regression detectee : l'avancement a baisse de 6.0 pt(s) "
        "sur 20 jour(s) (tendance : -0.300%/jour). 3/10 ticket(s) en retard."
    ),
    points=[],
)


def _mock_ollama(texte: str = "1. Prioriser les tickets critiques.\n2. Organiser un point d'étape.") -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.message.content = texte
    return mock_resp


# =========================================================
# Test 1 — Accès refusé → PermissionError
# =========================================================

def test_projet_non_autorise_leve_permission_error():
    """Un utilisateur limité à KAN ne peut pas obtenir de recommandation
    pour un projet SECRET — Ollama n'est jamais appelé."""
    context_kan = RequestContext(
        authenticated_email="testeur@sofrecom.com",
        allowed_project_ids=["KAN"],
    )
    with patch("recommandations_service.ollama.chat") as mock_chat, \
         patch("recommandations_service.log_event"):

        with pytest.raises(PermissionError, match="SECRET"):
            generer_recommandation(
                project_id="SECRET",
                nom_projet="Projet Confidentiel",
                kpis=KPIS_TEST,
                prevision=PREVISION_MODERE,
                context=context_kan,
            )

    mock_chat.assert_not_called()


# =========================================================
# Test 2 — Le prompt ne contient aucun email
# =========================================================

def test_prompt_ne_contient_aucun_email():
    """Même si un label KPI contenait un email (injection accidentelle),
    le prompt construit ne doit jamais transmettre d'adresse email au LLM."""
    kpis_avec_email_dans_label = [
        {"code": "avancement_pct", "label": "Avancement (ref:admin@sofrecom.com)", "valeur": 34.0},
        {"code": "total_tickets",  "label": "Total",                               "valeur": 10.0},
    ]

    prompt = _construire_prompt(
        nom_projet="Projet KAN",
        project_id="KAN",
        kpis=kpis_avec_email_dans_label,
        prevision=PREVISION_MODERE,
    )

    emails_trouves = EMAIL_RE.findall(prompt)
    assert emails_trouves == [], (
        f"Le prompt contient des emails qui ne doivent pas être transmis au LLM : "
        f"{emails_trouves}"
    )


# =========================================================
# Test 3 — Le prompt contient les KPIs pré-calculés
# =========================================================

def test_prompt_contient_kpis_precalcules():
    """Les valeurs calculées par Pandas doivent apparaître textuellement
    dans le prompt envoyé à Ollama — le LLM s'appuie sur ces chiffres."""
    prompt = _construire_prompt(
        nom_projet="Projet KAN",
        project_id="KAN",
        kpis=KPIS_TEST,
        prevision=PREVISION_MODERE,
    )

    assert "34.0%" in prompt, "L'avancement (34.0%) doit apparaître dans le prompt"
    assert "10.0"  in prompt, "Le total de tickets doit apparaître dans le prompt"
    assert "1.0"   in prompt, "Le nombre de tickets en retard doit apparaître dans le prompt"


# =========================================================
# Test 4 — Le niveau de risque dérive est transmis au LLM
# =========================================================

def test_prompt_contient_niveau_risque_derive():
    """Le niveau de risque calculé par derive_planning doit figurer
    dans le prompt — le LLM doit pouvoir baser ses recommandations dessus."""
    prompt_modere = _construire_prompt("KAN", "KAN", KPIS_TEST, PREVISION_MODERE)
    prompt_eleve  = _construire_prompt("KAN", "KAN", KPIS_TEST, PREVISION_ELEVE)

    assert "MODÉRÉ" in prompt_modere, "Le niveau MODÉRÉ doit apparaître dans le prompt"
    assert "ÉLEVÉ"  in prompt_eleve,  "Le niveau ÉLEVÉ doit apparaître dans le prompt"

    # La justification chiffrée doit être transmise intégralement
    assert PREVISION_MODERE.justification in prompt_modere
    assert PREVISION_ELEVE.justification  in prompt_eleve


# =========================================================
# Test 5 — Recommandation générée : approuvee=False par défaut
# =========================================================

def test_recommandation_generee_a_approuvee_false():
    """Une recommandation fraîchement générée doit avoir approuvee=False.
    Elle ne peut jamais être affichée sans validation humaine explicite."""
    with patch("recommandations_service.ollama.chat", return_value=_mock_ollama()), \
         patch("recommandations_service.log_event"):

        reco = generer_recommandation(
            project_id="KAN",
            nom_projet="Projet KAN",
            kpis=KPIS_TEST,
            prevision=PREVISION_MODERE,
            context=CONTEXT_KAN,
        )

    assert reco.approuvee is False, (
        "Une recommandation non validée doit avoir approuvee=False"
    )
    assert reco.project_id == "KAN"
    assert reco.risque_derive == "modere"
    assert len(reco.texte) > 0


# =========================================================
# Test 6 — Validation CLI : opérateur approuve → approuvee=True
# =========================================================

def test_valider_cli_operateur_approuve():
    """Quand l'opérateur répond 'o', approuvee passe à True."""
    reco = Recommandation(
        project_id="KAN",
        nom_projet="Projet KAN",
        texte="1. Prioriser les tickets en retard.\n2. Organiser une réunion.",
        risque_derive="modere",
        justification_derive="Progression modérée.",
    )
    assert reco.approuvee is False

    with patch("builtins.input", return_value="o"), \
         patch("builtins.print"):
        resultat = valider_recommandation_cli(reco)

    assert resultat.approuvee is True
    assert resultat is reco   # même objet, pas de copie


# =========================================================
# Test 7 — Validation CLI : opérateur rejette → approuvee=False
# =========================================================

def test_valider_cli_operateur_rejete():
    """Quand l'opérateur répond autre chose que 'o', approuvee reste False
    et la recommandation ne doit jamais être affichée."""
    reco = Recommandation(
        project_id="KAN",
        nom_projet="Projet KAN",
        texte="1. Prioriser les tickets en retard.",
        risque_derive="eleve",
        justification_derive="Régression détectée.",
    )

    for reponse_operateur in ["n", "N", "", "non", "no"]:
        reco.approuvee = False   # reset entre chaque itération
        with patch("builtins.input", return_value=reponse_operateur), \
             patch("builtins.print"):
            resultat = valider_recommandation_cli(reco)

        assert resultat.approuvee is False, (
            f"La réponse '{reponse_operateur}' ne devrait pas approuver la recommandation"
        )
