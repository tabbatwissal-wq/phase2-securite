"""
Tests complémentaires - Phase 1
1. Reproductibilité : les mêmes données produisent toujours les mêmes KPIs.
2. Robustesse : des tickets Jira mal formés (champs manquants) ne font pas
   planter le pipeline.

Installation : pip install pytest
Lancement    : pytest test_pipeline.py -v
"""

import pytest

from agent_jira import mapper_ticket_vers_pivot, calculer_kpis, construire_objet_pivot
import agent_jira

agent_jira.JIRA_PROJECT_KEY = "KAN"


TICKETS_COMPLETS = [
    {
        "key": "KAN-1",
        "fields": {
            "summary": "Ticket complet",
            "status": {"name": "Terminé"},
            "priority": {"name": "High"},
            "assignee": {"emailAddress": "test@example.com"},
            "duedate": "2026-01-01",
        },
    },
    {
        "key": "KAN-2",
        "fields": {
            "summary": "Deuxième ticket",
            "status": {"name": "À faire"},
            "priority": {"name": "Low"},
            "assignee": None,
            "duedate": None,
        },
    },
]


# ---------- Reproductibilité ----------

def test_kpis_sont_reproductibles():
    """Les mêmes données d'entrée doivent toujours produire les mêmes KPIs,
    peu importe le nombre de fois où on relance le calcul."""
    tasks_1 = [mapper_ticket_vers_pivot(i) for i in TICKETS_COMPLETS]
    kpis_1 = calculer_kpis(tasks_1)

    tasks_2 = [mapper_ticket_vers_pivot(i) for i in TICKETS_COMPLETS]
    kpis_2 = calculer_kpis(tasks_2)

    valeurs_1 = [(k.code, k.valeur) for k in kpis_1]
    valeurs_2 = [(k.code, k.valeur) for k in kpis_2]

    assert valeurs_1 == valeurs_2


def test_pivot_json_est_reproductible():
    """Deux générations successives du pivot, à partir des mêmes tickets,
    doivent produire les mêmes tâches et les mêmes KPIs (hors horodatage)."""
    tasks = [mapper_ticket_vers_pivot(i) for i in TICKETS_COMPLETS]
    kpis = calculer_kpis(tasks)

    pivot_1 = construire_objet_pivot(tasks, kpis)
    pivot_2 = construire_objet_pivot(tasks, kpis)

    assert [t.model_dump(exclude={"source"}) for t in pivot_1.tasks] == \
           [t.model_dump(exclude={"source"}) for t in pivot_2.tasks]
    assert [k.model_dump() for k in pivot_1.kpis] == [k.model_dump() for k in pivot_2.kpis]


# ---------- Robustesse face à des données malformées ----------

def test_ticket_sans_priorite_ne_plante_pas():
    """Un ticket Jira sans champ 'priority' du tout doit être géré
    gracieusement, avec une priorité par défaut."""
    ticket_sans_priorite = {
        "key": "KAN-9",
        "fields": {
            "summary": "Ticket sans priorité",
            "status": {"name": "À faire"},
            "assignee": None,
            "duedate": None,
        },
    }
    tache = mapper_ticket_vers_pivot(ticket_sans_priorite)
    assert tache.priorite is not None


def test_ticket_sans_assignee_ne_plante_pas():
    """Un ticket non assigné (assignee=None) ne doit pas faire planter le
    mapping — le responsable doit simplement être vide."""
    ticket_non_assigne = {
        "key": "KAN-10",
        "fields": {
            "summary": "Ticket orphelin",
            "status": {"name": "À faire"},
            "priority": {"name": "Medium"},
            "assignee": None,
            "duedate": None,
        },
    }
    tache = mapper_ticket_vers_pivot(ticket_non_assigne)
    assert tache.responsable_email is None


def test_ticket_sans_cle_utilise_repli_sur_id():
    """Si un ticket n'a pas de 'key' (cas du nouvel endpoint Jira sans le
    paramètre fields complet), le mapping doit utiliser 'id' en repli
    plutôt que de planter."""
    ticket_sans_key = {
        "id": "10042",
        "fields": {
            "summary": "Ticket avec id seulement",
            "status": {"name": "À faire"},
            "priority": {"name": "Medium"},
            "assignee": None,
            "duedate": None,
        },
    }
    tache = mapper_ticket_vers_pivot(ticket_sans_key)
    assert tache.task_id == "10042"


def test_liste_tickets_vide_ne_plante_pas():
    """Un projet Jira sans aucun ticket doit renvoyer des KPIs vides,
    pas une erreur."""
    kpis = calculer_kpis([])
    assert kpis == []
