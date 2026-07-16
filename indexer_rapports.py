"""
Indexation RAG - Phase 2
Pipeline : MongoDB → déduplication → anonymisation → validation humaine → ChromaDB.

Garanties :
  • Aucune donnée indexée sans approbation humaine (human_validation.valider_lot)
  • Aucun email ni identifiant source dans ChromaDB (jira_ai_filter)
  • Un seul document par projet dans ChromaDB (identifiant = project_id)
  • Idempotent : ré-exécuter met à jour le document existant sans créer de doublon

Installation : pip install chromadb
Lancement    : python indexer_rapports.py
"""

import os

import chromadb

from mongo_service import lister_rapports
from jira_ai_filter import preparer_contenu_pour_ia, ContenuSurAI
from human_validation import valider_lot

CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = "rapports_projets"


# ---------- ChromaDB ----------

def obtenir_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------- Identifiants ----------

def _doc_id(rapport: dict) -> str:
    """Identifiant ChromaDB basé sur project_id — un seul document par projet.
    L'upsert ChromaDB remplace l'entrée précédente → aucun doublon possible."""
    return rapport.get("project", {}).get("project_id", "INCONNU")


# ---------- Indexation ----------

def _indexer_contenus(
    contenus: list[ContenuSurAI],
    doc_ids: list[str],
) -> int:
    """Upserte les contenus approuvés dans ChromaDB.
    Renvoie le nombre de documents réellement indexés."""
    if not contenus:
        return 0

    collection = obtenir_collection()
    collection.upsert(
        ids=doc_ids,
        documents=[c.to_texte_indexable() for c in contenus],
        metadatas=[
            {
                "project_id": c.project_id,
                "nom_projet":  c.nom_projet,
                "genere_le":   c.genere_le,
            }
            for c in contenus
        ],
    )
    return len(contenus)


# ---------- Pipeline complet ----------

def indexer_tous_les_rapports(limite: int = 100) -> dict:
    """Charge les rapports MongoDB, les anonymise, les fait valider, les indexe.

    Renvoie un dict résumé :
      {"recuperes": int, "prepares": int, "approuves": int, "indexes": int}
    """
    print(f"[indexation] Récupération des rapports depuis MongoDB (limite={limite})…")
    rapports = lister_rapports(limite=limite)
    print(f"[indexation] {len(rapports)} rapport(s) récupéré(s).")

    if not rapports:
        print("[indexation] Aucun rapport dans MongoDB — arrêt.")
        return {"recuperes": 0, "prepares": 0, "approuves": 0, "indexes": 0}

    # --- Déduplication : un seul rapport par projet, le plus récent ---
    recents: dict[str, dict] = {}
    for rapport in rapports:
        pid = rapport.get("project", {}).get("project_id", "INCONNU")
        date_r = str(rapport.get("reporting_period", {}).get("genere_le", ""))
        if pid not in recents or date_r > str(recents[pid].get("reporting_period", {}).get("genere_le", "")):
            recents[pid] = rapport
    rapports = list(recents.values())
    print(f"[indexation] {len(rapports)} rapport(s) après déduplication par projet.")

    # --- Anonymisation ---
    contenus: list[ContenuSurAI] = []
    doc_ids:  list[str]          = []

    for rapport in rapports:
        pid = rapport.get("project", {}).get("project_id", "?")
        try:
            contenus.append(preparer_contenu_pour_ia(rapport))
            doc_ids.append(_doc_id(rapport))
        except Exception as e:
            print(f"[indexation] Rapport ignoré (projet {pid}) : {e}")

    print(f"[indexation] {len(contenus)} rapport(s) anonymisé(s), prêts pour validation.")

    # --- Validation humaine (porte obligatoire) ---
    approuves = valider_lot(contenus)

    if not approuves:
        print("[indexation] Aucun rapport approuvé — arrêt sans écriture dans ChromaDB.")
        return {"recuperes": len(rapports), "prepares": len(contenus), "approuves": 0, "indexes": 0}

    # Retrouver les doc_ids des contenus approuvés par identité objet
    approuves_set = {id(c) for c in approuves}
    approuves_ids = [
        doc_id
        for contenu, doc_id in zip(contenus, doc_ids)
        if id(contenu) in approuves_set
    ]

    # --- Indexation ChromaDB ---
    n = _indexer_contenus(approuves, approuves_ids)
    print(
        f"[indexation] {n} rapport(s) indexé(s) dans ChromaDB "
        f"(collection='{COLLECTION_NAME}', chemin='{CHROMA_PATH}')."
    )

    return {
        "recuperes": len(rapports),
        "prepares":  len(contenus),
        "approuves": len(approuves),
        "indexes":   n,
    }


if __name__ == "__main__":
    resume = indexer_tous_les_rapports()
    print(f"\nRésumé final : {resume}")
