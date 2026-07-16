"""
Test de connexion à Jira Cloud - Phase 1 (endpoint corrigé)
Vérifie que le token API fonctionne et affiche les tickets du projet test.

Avant d'exécuter :
1. Copier .env.example en .env
2. Remplir JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
3. pip install requests python-dotenv
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")


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


def tester_connexion():
    """Vérifie que l'authentification fonctionne."""
    url = f"{JIRA_URL}/rest/api/3/myself"
    response = requests.get(
        url,
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
    )
    if response.status_code == 200:
        data = response.json()
        print(f"Connexion réussie — connecté en tant que : {data.get('displayName')}")
        return True
    else:
        print(f"Échec de connexion — code {response.status_code}")
        print(response.text)
        return False


def recuperer_tickets():
    """Récupère les tickets du projet test via JQL (endpoint /search/jql).
    Le nouvel endpoint ne renvoie que 'id' par défaut : il faut demander
    explicitement les champs voulus via le paramètre 'fields'."""
    url = f"{JIRA_URL}/rest/api/3/search/jql"
    jql = f'project = "{JIRA_PROJECT_KEY}" ORDER BY created DESC'
    response = requests.get(
        url,
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        params={
            "jql": jql,
            "maxResults": 50,
            "fields": "summary,status,priority,assignee,duedate,created,updated",
        },
    )
    if response.status_code != 200:
        print(f"Erreur lors de la récupération des tickets — code {response.status_code}")
        print(response.text)
        return []

    issues = response.json().get("issues", [])
    print(f"\n{len(issues)} ticket(s) trouvé(s) dans le projet {JIRA_PROJECT_KEY} :\n")
    for issue in issues:
        key = issue.get("key", issue.get("id", "?"))
        summary = issue["fields"]["summary"]
        status = issue["fields"]["status"]["name"]
        priority = issue["fields"].get("priority", {}).get("name", "Non définie")
        print(f"  [{key}] {summary}")
        print(f"      Statut : {status}  |  Priorité : {priority}")
    return issues


if __name__ == "__main__":
    verifier_configuration()
    if tester_connexion():
        recuperer_tickets()