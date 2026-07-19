"""
Agent Jira - POC Phase 1
Se connecte au Jira de test, récupère les tickets, calcule les KPIs avec
Pandas (jamais avec l'IA), et écrit ProjectReportPivot.json.

Installation :
  pip install requests python-dotenv pandas "pydantic[email]>=2.0" --break-system-packages

Utilisation :
  1. Copier .env.example en .env et le remplir
  2. python3 agent_jira.py
  3. Le fichier ProjectReportPivot.json est créé dans le dossier courant
"""

import os
import sys
import json
import requests
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import date, datetime
from dotenv import load_dotenv

from pivot_models import (
    ProjectReportPivot,
    ProjectIdentity,
    ReportingPeriod,
    ProjectTask,
    KPI,
    SourceReference,
    SourceSystem,
    TaskStatus,
    Priority,
)
from mongo_service import sauvegarder_pivot

load_dotenv()

JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

# Mapping des statuts Jira (texte libre côté Jira) vers notre enum interne.
# Fichier de mapping externe recommandé en production (voir jira_mapping.yaml) ;
# dictionnaire simple ici pour le POC.
STATUS_MAPPING = {
    "à faire": TaskStatus.A_FAIRE,
    "to do": TaskStatus.A_FAIRE,
    "en cours": TaskStatus.EN_COURS,
    "in progress": TaskStatus.EN_COURS,
    "terminé": TaskStatus.TERMINE,
    "done": TaskStatus.TERMINE,
    "bloqué": TaskStatus.BLOQUE,
    "blocked": TaskStatus.BLOQUE,
}

PRIORITY_MAPPING = {
    "lowest": Priority.BASSE,
    "low": Priority.BASSE,
    "medium": Priority.MOYENNE,
    "high": Priority.HAUTE,
    "highest": Priority.CRITIQUE,
}


def verifier_configuration():
    manquants = [
        nom for nom, val in [
            ("JIRA_URL", JIRA_URL),
            ("JIRA_EMAIL", JIRA_EMAIL),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
            ("JIRA_PROJECT_KEY", JIRA_PROJECT_KEY),
        ] if not val
    ]
    if manquants:
        print(f"Variables manquantes dans .env : {', '.join(manquants)}")
        sys.exit(1)


def recuperer_nom_projet() -> str:
    """Appelle l'API Jira pour obtenir le nom complet du projet.
    Repli sur f'Projet {JIRA_PROJECT_KEY}' si l'appel échoue."""
    url = f"{JIRA_URL}/rest/api/3/project/{JIRA_PROJECT_KEY}"
    try:
        response = requests.get(
            url,
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("name", f"Projet {JIRA_PROJECT_KEY}")
    except Exception:
        pass
    return f"Projet {JIRA_PROJECT_KEY}"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    reraise=True,
)
def recuperer_tickets_jira() -> list[dict]:
    """Appelle l'API Jira et renvoie la liste brute des tickets.
    Le paramètre 'fields' est obligatoire avec le nouvel endpoint /search/jql :
    par défaut, seul 'id' est renvoyé, sans 'key' ni les champs métier.

    Réessaie automatiquement (3 tentatives, backoff exponentiel) en cas
    d'erreur réseau ou de timeout uniquement — jamais sur les erreurs
    d'authentification (401/403), qui ne doivent pas être retentées."""
    url = f"{JIRA_URL}/rest/api/3/search/jql"
    jql = f'project = "{JIRA_PROJECT_KEY}" ORDER BY created DESC'
    response = requests.get(
        url,
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        params={
            "jql": jql,
            "maxResults": 100,
            "fields": "summary,status,priority,assignee,duedate,created,updated",
        },
        timeout=10,
    )
    if response.status_code != 200:
        print(f"Erreur API Jira — code {response.status_code}")
        print(response.text)
        sys.exit(1)
    return response.json().get("issues", [])


def mapper_ticket_vers_pivot(issue: dict) -> ProjectTask:
    """Transforme un ticket Jira brut en ProjectTask normalisé (JiraMapper)."""
    fields = issue["fields"]
    ticket_key = issue.get("key", issue.get("id", "INCONNU"))

    statut_brut = fields["status"]["name"].strip().lower()
    statut = STATUS_MAPPING.get(statut_brut, TaskStatus.A_FAIRE)

    priorite_brute = (fields.get("priority") or {}).get("name", "medium").lower()
    priorite = PRIORITY_MAPPING.get(priorite_brute, Priority.MOYENNE)

    assignee = fields.get("assignee")
    responsable_email = assignee.get("emailAddress") if assignee else None

    date_echeance = None
    en_retard = False
    if fields.get("duedate"):
        date_echeance = datetime.strptime(fields["duedate"], "%Y-%m-%d").date()
        en_retard = date_echeance < date.today() and statut != TaskStatus.TERMINE

    return ProjectTask(
        task_id=ticket_key,
        titre=fields["summary"],
        statut=statut,
        priorite=priorite,
        responsable_email=responsable_email,
        date_echeance=date_echeance,
        en_retard=en_retard,
        source=SourceReference(
            source_system=SourceSystem.JIRA,
            source_record_id=ticket_key,
            champ_origine="fields.status.name",
        ),
    )


def calculer_kpis(tasks: list[ProjectTask]) -> list[KPI]:
    """Calcule les indicateurs avec Pandas — jamais avec l'IA.
    C'est le principe central de l'architecture : le LLM ne produit aucun chiffre."""
    if not tasks:
        return []

    df = pd.DataFrame([t.model_dump() for t in tasks])

    total = len(df)
    termines = (df["statut"] == TaskStatus.TERMINE.value).sum()
    en_cours = (df["statut"] == TaskStatus.EN_COURS.value).sum()
    en_retard = df["en_retard"].sum()
    critiques = (df["priorite"] == Priority.CRITIQUE.value).sum()

    avancement_pct = round((termines / total) * 100, 1) if total else 0.0

    return [
        KPI(code="total_tickets", label="Nombre total de tickets", valeur=float(total)),
        KPI(code="avancement_pct", label="Avancement global", valeur=avancement_pct, unite="%"),
        KPI(code="tickets_termines", label="Tickets terminés", valeur=float(termines)),
        KPI(code="tickets_en_cours", label="Tickets en cours", valeur=float(en_cours)),
        KPI(code="tickets_en_retard", label="Tickets en retard", valeur=float(en_retard)),
        KPI(code="tickets_critiques", label="Tickets priorité critique", valeur=float(critiques)),
    ]


def construire_objet_pivot(
    tasks: list[ProjectTask], kpis: list[KPI], nom_projet: str | None = None
) -> ProjectReportPivot:
    return ProjectReportPivot(
        project=ProjectIdentity(
            project_id=JIRA_PROJECT_KEY,
            nom_projet=nom_projet or f"Projet {JIRA_PROJECT_KEY}",
            cle_jira=JIRA_PROJECT_KEY,
        ),
        reporting_period=ReportingPeriod(),
        kpis=kpis,
        tasks=tasks,
        resume_executif=None,
    )


def main():
    verifier_configuration()

    print(f"Récupération du nom du projet {JIRA_PROJECT_KEY} depuis Jira...")
    nom_projet = recuperer_nom_projet()
    print(f"  Nom : {nom_projet}")

    print(f"Récupération des tickets du projet {JIRA_PROJECT_KEY}...")
    issues = recuperer_tickets_jira()
    print(f"{len(issues)} ticket(s) récupéré(s).")

    print("Normalisation vers l'Objet Pivot (ProjectTask)...")
    tasks = [mapper_ticket_vers_pivot(issue) for issue in issues]

    print("Calcul des KPIs avec Pandas...")
    kpis = calculer_kpis(tasks)
    for kpi in kpis:
        print(f"  - {kpi.label} : {kpi.valeur}{kpi.unite or ''}")

    print("Construction de l'Objet Pivot final...")
    pivot = construire_objet_pivot(tasks, kpis, nom_projet)

    output_path = "ProjectReportPivot.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(pivot.model_dump_json(indent=2))
    print(f"\nFichier écrit avec succès : {output_path}")

    print("Sauvegarde dans MongoDB...")
    try:
        doc_id = sauvegarder_pivot(pivot.model_dump(mode="json"))
        print(f"Document enregistré dans MongoDB — id : {doc_id}")
    except Exception as e:
        print(f"MongoDB indisponible, sauvegarde locale uniquement. Détail : {e}")


if __name__ == "__main__":
    main()