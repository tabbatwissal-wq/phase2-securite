"""
Backend FastAPI - Phase 1
Expose des endpoints sécurisés pour générer l'Objet Pivot depuis Jira,
protégés par le RequestContext (voir security_context.py).

Installation : pip install fastapi "uvicorn[standard]"
Lancement    : uvicorn main:app --reload
Documentation interactive : http://127.0.0.1:8000/docs
"""

from fastapi import Depends, FastAPI, Header
from auth_sso import router as sso_router

from security_context import (
    RequestContext,
    get_request_context,
    get_request_context_sso,
    verifier_acces_projet,
)
from agent_jira import (
    recuperer_tickets_jira,
    mapper_ticket_vers_pivot,
    calculer_kpis,
    construire_objet_pivot,
)
from mongo_service import sauvegarder_pivot
from audit_service import log_event
from pptx_generatore import generer_rapport as generer_pptx
from pdf_service import generer_rapport as generer_pdf
from teams_webhook import envoyer_notification_rapport
import agent_jira
import json

app = FastAPI(
    title="Sofrecom Reporting IA - API",
    description="Backend sécurisé pour la génération de rapports depuis Jira.",
    version="0.2.0",
)

app.include_router(sso_router)


def get_context_sso_or_key(
    x_api_key: str | None = Header(default=None),
    x_session_token: str | None = Header(default=None),
) -> RequestContext:
    """Accepte soit une session SSO (X-Session-Token), soit l'ancien
    système X-API-Key. Essaie d'abord la session SSO si présente."""
    if x_session_token:
        return get_request_context_sso(session=x_session_token)
    return get_request_context(x_api_key=x_api_key)


@app.get("/health")
def health_check():
    """Endpoint public, sans authentification — juste pour vérifier que
    le serveur tourne."""
    return {"status": "ok"}


def _construire_pivot(project_key: str):
    """Étapes communes : récupération Jira + normalisation + calcul KPI."""
    agent_jira.JIRA_PROJECT_KEY = project_key
    nom_projet = agent_jira.recuperer_nom_projet()
    issues = recuperer_tickets_jira()
    tasks = [mapper_ticket_vers_pivot(issue) for issue in issues]
    kpis = calculer_kpis(tasks)
    return construire_objet_pivot(tasks, kpis, nom_projet)


@app.get("/reports/{project_key}")
def generer_rapport_securise(
    project_key: str,
    context: RequestContext = Depends(get_context_sso_or_key),
):
    """Génère l'Objet Pivot pour le projet demandé et le renvoie en JSON,
    uniquement si le RequestContext autorise l'accès à ce projet précis."""
    verifier_acces_projet(project_key, context)

    pivot = _construire_pivot(project_key)

    return {
        "request_id": str(context.request_id),
        "requested_by": context.authenticated_email,
        "pivot": pivot.model_dump(mode="json"),
    }


def executer_pipeline_complet(project_key: str, context=None, output_path: str = "ProjectReportPivot.json"):
    """Pipeline partagé utilisé par l'API FastAPI et l'interface Streamlit."""
    pivot = _construire_pivot(project_key)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(pivot.model_dump_json(indent=2))

    mongo_id = None
    try:
        mongo_id = sauvegarder_pivot(pivot.model_dump(mode="json"))
    except Exception as e:
        if context is not None:
            log_event(email=context.authenticated_email, project_key=project_key,
                      action="mongo_save", success=False, detail=str(e))

    generer_pptx(output_path, "rapport_demo.pptx")
    generer_pdf(output_path, "rapport_demo.pdf")

    if context is not None:
        log_event(email=context.authenticated_email, project_key=project_key,
                  action="generate_full_report", success=True,
                  detail=f"mongo_id={mongo_id}")
        envoyer_notification_rapport(pivot.model_dump(mode="json"), context)

    return {
        "mongo_id": mongo_id,
        "fichiers_generes": ["rapport_demo.pptx", "rapport_demo.pdf"],
        "kpis": [k.model_dump() for k in pivot.kpis],
    }


@app.post("/reports/{project_key}/generate")
def generer_pipeline_complet(
    project_key: str,
    context: RequestContext = Depends(get_context_sso_or_key),
):
    """Pipeline complet en un seul appel : Jira -> Objet Pivot -> MongoDB
    -> génération PPTX + PDF. C'est l'endpoint de démonstration de bout
    en bout, celui à utiliser pour une présentation."""
    verifier_acces_projet(project_key, context)

    result = executer_pipeline_complet(project_key, context=context)

    return {
        "request_id": str(context.request_id),
        "requested_by": context.authenticated_email,
        **result,
    }