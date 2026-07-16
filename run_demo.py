"""
Démonstration de bout en bout - Phase 1
Exécute tout le pipeline en une seule commande, sans passer par le serveur
HTTP : Jira -> Sécurité -> Objet Pivot -> MongoDB -> PPTX -> PDF.

Utilisation : python run_demo.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from security_context import RequestContext, get_request_context, verifier_acces_projet, _charger_config_acces
from agent_jira import (
    recuperer_tickets_jira,
    mapper_ticket_vers_pivot,
    calculer_kpis,
    construire_objet_pivot,
)
from mongo_service import sauvegarder_pivot
from audit_service import log_event, lister_logs
from pptx_generator import generer_rapport as generer_pptx
from pdf_generator import generer_rapport as generer_pdf
import agent_jira


def executer_demo():
    print("=" * 60)
    print("DÉMONSTRATION DE BOUT EN BOUT — PHASE 1")
    print("=" * 60)

    project_key = os.getenv("JIRA_PROJECT_KEY")
    if not project_key:
        print("JIRA_PROJECT_KEY manquant dans .env")
        sys.exit(1)

    # ---- 1. Sécurité : simulation d'une requête authentifiée ----
    print("\n[1/6] Vérification du contexte de sécurité...")
    config = _charger_config_acces()
    premier_token = next(iter(config))
    entree = config[premier_token]
    context = RequestContext(
        authenticated_email=entree["email"],
        allowed_project_ids=entree["allowed_project_ids"],
    )
    verifier_acces_projet(project_key, context)
    print(f"    Accès autorisé pour {context.authenticated_email} sur le projet {project_key}")

    # ---- 2. Connexion Jira ----
    print("\n[2/6] Récupération des tickets Jira...")
    agent_jira.JIRA_PROJECT_KEY = project_key
    issues = recuperer_tickets_jira()
    print(f"    {len(issues)} ticket(s) récupéré(s)")

    # ---- 3. Objet Pivot + KPIs ----
    print("\n[3/6] Normalisation et calcul des KPIs...")
    tasks = [mapper_ticket_vers_pivot(issue) for issue in issues]
    kpis = calculer_kpis(tasks)
    pivot = construire_objet_pivot(tasks, kpis)
    for kpi in kpis:
        print(f"    - {kpi.label} : {kpi.valeur}{kpi.unite or ''}")

    with open("ProjectReportPivot.json", "w", encoding="utf-8") as f:
        f.write(pivot.model_dump_json(indent=2))
    print("    ProjectReportPivot.json écrit")

    # ---- 4. MongoDB ----
    print("\n[4/6] Sauvegarde dans MongoDB...")
    try:
        mongo_id = sauvegarder_pivot(pivot.model_dump(mode="json"))
        print(f"    Document enregistré — id : {mongo_id}")
    except Exception as e:
        mongo_id = None
        print(f"    MongoDB indisponible : {e}")

    # ---- 5. Génération des rapports ----
    print("\n[5/6] Génération des rapports PPTX et PDF...")
    generer_pptx()
    generer_pdf()

    # ---- 6. Audit ----
    print("\n[6/6] Journalisation de l'audit...")
    log_event(email=context.authenticated_email, project_key=project_key,
              action="run_demo_complete", success=True, detail=f"mongo_id={mongo_id}")
    print("    Événement enregistré dans audit_logs")

    print("\n" + "=" * 60)
    print("DÉMONSTRATION TERMINÉE — pipeline complet exécuté avec succès")
    print("=" * 60)
    print("\nDerniers événements d'audit :")
    try:
        for log in lister_logs(limite=3):
            print(f"  {log['timestamp']} | {log['action']} | succès={log['success']}")
    except Exception as e:
        print(f"  (impossible de lire les logs : {e})")


if __name__ == "__main__":
    executer_demo()
