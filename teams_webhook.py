"""
Volet 1 — Notifications Microsoft Teams via Power Automate

Envoie un message dans un chat personnel Teams (via le "Flow bot") à chaque
génération de rapport réussie. Le déclencheur est un flux Power Automate
configuré avec l'action "When a HTTP request is received".

Configuration (une seule variable dans .env) :
  TEAMS_WEBHOOK_URL = https://xxxxx.logic.azure.com:443/workflows/...
  (URL générée automatiquement par Power Automate dans le déclencheur HTTP)

Comportement si non configuré ou si l'envoi échoue :
  → Retourne False et journalise via audit_service — ne lève jamais
    d'exception, la génération du rapport n'est jamais bloquée.

Format du payload : JSON avec champ "text" (message lisible) + champs KPI
individuels. Power Automate peut utiliser soit @{triggerBody()?['text']}
pour un message brut, soit les champs individuels pour composer un message
personnalisé.
"""

import json
import os

import requests

from audit_service import log_event
from security_context import RequestContext

_TIMEOUT_SEC = 8


# ──────────────────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────────────────

def _extraire_kpis(kpis_list: list[dict]) -> dict[str, float]:
    """Transforme la liste KPI du pivot en dict code → valeur."""
    return {k["code"]: float(k.get("valeur", 0)) for k in kpis_list}


def _icone_risque(kpis: dict[str, float]) -> str:
    """🔴 si critiques ou >30 % de retards, 🟡 si retards, 🟢 sinon."""
    critiques = kpis.get("tickets_critiques", 0)
    en_retard = kpis.get("tickets_en_retard", 0)
    total     = kpis.get("total_tickets", 1) or 1
    if critiques > 0 or (en_retard / total) > 0.30:
        return "🔴"
    if en_retard > 0:
        return "🟡"
    return "🟢"


def _construire_texte(
    nom_projet: str,
    project_id: str,
    kpis: dict[str, float],
    date_rapport: str,
) -> str:
    """Texte lisible du message Teams, utilisable directement dans Power Automate."""
    icone     = _icone_risque(kpis)
    avancement = kpis.get("avancement_pct", 0.0)
    total      = int(kpis.get("total_tickets", 0))
    en_retard  = int(kpis.get("tickets_en_retard", 0))
    critiques  = int(kpis.get("tickets_critiques", 0))
    return (
        f"{icone} Rapport généré — {nom_projet} ({project_id})\n"
        f"Date : {date_rapport}\n"
        f"Avancement : {avancement:.1f} %\n"
        f"Tickets : {total} total | {en_retard} en retard | {critiques} critiques"
    )


def _construire_payload(
    nom_projet: str,
    project_id: str,
    kpis: dict[str, float],
    date_rapport: str,
) -> dict:
    """Corps JSON envoyé au déclencheur HTTP Power Automate.

    Contient :
    - "text" : message complet prêt à l'emploi
      → Power Automate : @{triggerBody()?['text']}
    - champs KPI individuels pour composer un message personnalisé
      → Power Automate : @{triggerBody()?['avancement_pct']}, etc."""
    return {
        "text":               _construire_texte(nom_projet, project_id, kpis, date_rapport),
        "projet":             nom_projet,
        "project_id":         project_id,
        "avancement_pct":     round(kpis.get("avancement_pct", 0.0), 1),
        "tickets_total":      int(kpis.get("total_tickets", 0)),
        "tickets_en_retard":  int(kpis.get("tickets_en_retard", 0)),
        "tickets_critiques":  int(kpis.get("tickets_critiques", 0)),
        "date":               date_rapport,
    }


# ──────────────────────────────────────────────────────────
# Point d'entrée public
# ──────────────────────────────────────────────────────────

def envoyer_notification_rapport(
    pivot: dict,
    context: RequestContext,
) -> bool:
    """Envoie une notification Teams à la fin d'une génération de rapport.

    Paramètres
    ----------
    pivot   : dict au format ProjectReportPivot (issu de model_dump(mode="json"))
    context : RequestContext de l'utilisateur déclencheur (pour l'audit)

    Retourne True si la notification a été envoyée avec succès (HTTP 200/202),
    False dans tous les autres cas. Ne lève jamais d'exception."""
    url = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
    if not url:
        return False

    project      = pivot.get("project", {})
    nom_projet   = project.get("nom_projet") or project.get("project_id", "Inconnu")
    project_id   = project.get("project_id", "?")
    kpis         = _extraire_kpis(pivot.get("kpis", []))
    date_rapport = str(pivot.get("reporting_period", {}).get("genere_le", ""))[:10]

    payload = _construire_payload(nom_projet, project_id, kpis, date_rapport)

    try:
        response = requests.post(
            url,
            data=json.dumps(payload, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        log_event(
            email=context.authenticated_email,
            project_key=project_id,
            action="teams_webhook",
            success=False,
            detail=f"Erreur réseau : {exc}",
        )
        return False

    if response.status_code not in (200, 202):
        log_event(
            email=context.authenticated_email,
            project_key=project_id,
            action="teams_webhook",
            success=False,
            detail=f"HTTP {response.status_code} : {response.text[:300]}",
        )
        return False

    log_event(
        email=context.authenticated_email,
        project_key=project_id,
        action="teams_webhook",
        success=True,
        detail=(
            f"Notification envoyée — {nom_projet} "
            f"(avancement={kpis.get('avancement_pct', 0):.1f}%, "
            f"en_retard={int(kpis.get('tickets_en_retard', 0))})"
        ),
    )
    return True
