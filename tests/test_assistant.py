"""
Tests assistant IA - Phase 2
Trois tests de sécurité prioritaires :

1. Cloisonnement : une question sur un projet non autorisé ne renvoie aucune
   donnée de ce projet (filtre ChromaDB par allowed_project_ids).

2. Validation humaine : indexer_rapports.py n'indexe jamais du contenu rejeté
   par valider_lot (aucun appel à _indexer_contenus si la liste est vide).

3. Anonymisation : le texte indexé dans ChromaDB ne contient jamais d'adresse
   email, même si le pivot source en contenait.

Lancement : pytest tests/test_assistant.py -v
"""

import re
import sys
import os

import pytest
from unittest.mock import patch

# Chemin du projet au sys.path pour les imports sans installation de package
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from jira_ai_filter import preparer_contenu_pour_ia

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


# ---------- Fixture : pivot minimal ----------

def _pivot(project_id: str = "PTI", with_email: bool = True) -> dict:
    """Construit un pivot dict minimal compatible avec preparer_contenu_pour_ia."""
    return {
        "project": {
            "project_id": project_id,
            "nom_projet": f"Projet {project_id}",
            "cle_jira": project_id,
        },
        "reporting_period": {"genere_le": "2026-07-13T00:00:00+00:00"},
        "kpis": [
            {"code": "total_tickets",    "label": "Total",      "valeur": 2.0},
            {"code": "avancement_pct",   "label": "Avancement", "valeur": 50.0, "unite": "%"},
            {"code": "tickets_termines", "label": "Terminés",   "valeur": 1.0},
            {"code": "tickets_en_cours", "label": "En cours",   "valeur": 1.0},
            {"code": "tickets_en_retard","label": "En retard",  "valeur": 0.0},
            {"code": "tickets_critiques","label": "Critiques",  "valeur": 0.0},
        ],
        "tasks": [
            {
                "task_id": f"{project_id}-1",
                "titre": "Configurer l'environnement",
                "statut": "termine",
                "priorite": "haute",
                "responsable_email": "agent@sofrecom.com" if with_email else None,
                "date_echeance": None,
                "en_retard": False,
                "source": {
                    "source_system": "jira",
                    "source_record_id": f"{project_id}-1",
                    "champ_origine": "fields.status.name",
                },
            },
            {
                "task_id": f"{project_id}-2",
                "titre": "Développer le module de reporting",
                "statut": "en_cours",
                "priorite": "moyenne",
                "responsable_email": "lead@sofrecom.com" if with_email else None,
                "date_echeance": None,
                "en_retard": False,
                "source": {
                    "source_system": "jira",
                    "source_record_id": f"{project_id}-2",
                    "champ_origine": "fields.status.name",
                },
            },
        ],
    }


# =========================================================
# Test 1 — Cloisonnement par projets autorisés
# =========================================================

def test_question_projet_non_autorise_ne_renvoie_aucune_donnee():
    """_rechercher_documents ne doit retourner aucun document si le projet
    indexé (SECRET) n'est pas dans allowed_project_ids (["KAN"]).

    Le filtre `where` ChromaDB exclut les documents côté base, avant
    tout ranking sémantique — la sécurité ne dépend pas du modèle."""
    import chromadb
    from assistant_service import _rechercher_documents

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        "rapports_projets", metadata={"hnsw:space": "cosine"}
    )

    # Indexer un document pour un projet SECRET
    contenu_secret = preparer_contenu_pour_ia(_pivot("SECRET"))
    collection.add(
        ids=["secret-doc-1"],
        documents=[contenu_secret.to_texte_indexable()],
        metadatas=[{
            "project_id": "SECRET",
            "nom_projet":  "Projet Confidentiel",
            "genere_le":   "2026-07-13",
        }],
    )

    # Interroger avec un contexte n'autorisant que KAN
    with patch("assistant_service._obtenir_collection", return_value=collection):
        docs = _rechercher_documents("quel est l'état du projet", ["KAN"])

    assert docs == [], (
        f"Des données du projet SECRET ont été renvoyées à un utilisateur "
        f"n'ayant accès qu'à KAN : {docs}"
    )


# =========================================================
# Test 2 — Contenu rejeté non indexé
# =========================================================

def test_indexer_rapports_ne_indexe_pas_contenu_rejete():
    """Quand valider_lot retourne [] (opérateur rejette tout),
    _indexer_contenus ne doit jamais être appelé."""
    from indexer_rapports import indexer_tous_les_rapports

    with patch("indexer_rapports.lister_rapports", return_value=[_pivot("PTI")]), \
         patch("indexer_rapports.valider_lot", return_value=[]), \
         patch("indexer_rapports._indexer_contenus") as mock_upsert:

        result = indexer_tous_les_rapports()

    mock_upsert.assert_not_called()
    assert result["indexes"] == 0
    assert result["approuves"] == 0


# =========================================================
# Test 3 — Aucun email dans le texte indexé
# =========================================================

def test_contenu_indexe_ne_contient_pas_email():
    """preparer_contenu_pour_ia doit supprimer toute adresse email du pivot
    source avant de produire le texte destiné à ChromaDB."""
    pivot = _pivot("PTI", with_email=True)

    # Vérifier que le pivot source contient bien des emails
    emails_source = [
        t["responsable_email"]
        for t in pivot["tasks"]
        if t.get("responsable_email")
    ]
    assert emails_source, "Le pivot de test doit contenir au moins un email."

    # Préparer le contenu anonymisé
    contenu = preparer_contenu_pour_ia(pivot)
    texte_indexe = contenu.to_texte_indexable()

    emails_trouves = EMAIL_RE.findall(texte_indexe)
    assert emails_trouves == [], (
        f"Le texte indexé contient des emails qui auraient dû être supprimés : "
        f"{emails_trouves}\n\nTexte complet :\n{texte_indexe}"
    )
