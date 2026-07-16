"""
Crée un ProjectReportPivot.json de test, sans avoir besoin de Jira.
Utile pour tester pptx_generator.py et pdf_generator.py pendant que
le site Jira réel finit de se provisionner.

Utilisation : python creer_pivot_test.py
"""

from agent_jira import mapper_ticket_vers_pivot, calculer_kpis, construire_objet_pivot
import agent_jira

# On force la clé projet pour que le rapport affiche "KAN"
agent_jira.JIRA_PROJECT_KEY = "KAN"

fake_issues = [
    {
        "key": "KAN-1",
        "fields": {
            "summary": "Mettre en place authentification API",
            "status": {"name": "Terminé"},
            "priority": {"name": "High"},
            "assignee": {"emailAddress": "test@example.com"},
            "duedate": "2026-06-01",
        },
    },
    {
        "key": "KAN-2",
        "fields": {
            "summary": "Développer le connecteur Jira",
            "status": {"name": "En cours"},
            "priority": {"name": "High"},
            "assignee": None,
            "duedate": None,
        },
    },
    {
        "key": "KAN-3",
        "fields": {
            "summary": "Créer le template PowerPoint",
            "status": {"name": "À faire"},
            "priority": {"name": "Medium"},
            "assignee": None,
            "duedate": None,
        },
    },
    {
        "key": "KAN-4",
        "fields": {
            "summary": "Tester le filtrage de sécurité",
            "status": {"name": "À faire"},
            "priority": {"name": "Highest"},
            "assignee": None,
            "duedate": "2026-01-01",
        },
    },
    {
        "key": "KAN-5",
        "fields": {
            "summary": "Rédiger la documentation",
            "status": {"name": "À faire"},
            "priority": {"name": "Low"},
            "assignee": None,
            "duedate": None,
        },
    },
]

tasks = [mapper_ticket_vers_pivot(i) for i in fake_issues]
kpis = calculer_kpis(tasks)
pivot = construire_objet_pivot(tasks, kpis)

with open("ProjectReportPivot.json", "w", encoding="utf-8") as f:
    f.write(pivot.model_dump_json(indent=2))

print("ProjectReportPivot.json créé avec des données de test (5 tickets simulés).")
