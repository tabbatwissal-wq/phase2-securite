"""
Service assistant IA - Phase 2
Recherche sémantique dans ChromaDB (filtrée par projets autorisés)
puis génération de réponse via un modèle Ollama local (Qwen).

Garanties de sécurité :
  • Seuls les documents dont project_id est dans context.allowed_project_ids
    sont transmis au modèle — le filtre est appliqué côté ChromaDB, avant
    toute construction du prompt.
  • Chaque interaction est journalisée via audit_service.

Prérequis :
  • ollama run qwen2.5:7b  (ou le modèle défini dans OLLAMA_MODEL)
  • ChromaDB peuplé via indexer_rapports.py
"""

import os

import chromadb
import ollama

from security_context import RequestContext
from audit_service import log_event

CHROMA_PATH  = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = "rapports_projets"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
N_RESULTS    = int(os.getenv("RAG_N_RESULTS", "4"))

_SYSTEM_PROMPT = (
    "Tu es un assistant spécialisé dans le suivi de projets informatiques pour Sofrecom. "
    "CONSIGNE ABSOLUE : Tu dois TOUJOURS répondre en FRANÇAIS, peu importe la langue de la question. "
    "Tu réponds UNIQUEMENT à partir des données de projet fournies dans le contexte. "
    "Si une information ne figure pas dans le contexte, dis-le clairement sans inventer. "
    "Tu ne fournis jamais d'informations sur des projets absents du contexte. "
    "RAPPEL OBLIGATOIRE : Ta réponse doit être rédigée UNIQUEMENT en français, "
    "de façon concise et professionnelle."
)


# ---------- ChromaDB ----------

def _obtenir_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------- Recherche sémantique ----------

def _rechercher_documents(question: str, allowed_project_ids: list[str]) -> list[str]:
    """Recherche les documents ChromaDB pertinents, restreints aux projets autorisés.

    Le filtre `where` est appliqué dans ChromaDB avant le ranking sémantique :
    un document d'un projet non autorisé ne peut jamais remonter,
    même s'il est sémantiquement très proche de la question."""
    if not allowed_project_ids:
        return []

    collection = _obtenir_collection()
    if collection.count() == 0:
        return []

    n = min(N_RESULTS, collection.count())
    where: dict = {"project_id": {"$in": allowed_project_ids}}

    try:
        results = collection.query(
            query_texts=[question],
            n_results=n,
            where=where,
        )
    except Exception:
        # ChromaDB lève une ValueError si le filtre ne correspond à aucun document
        return []

    return [doc for doc in results.get("documents", [[]])[0] if doc]


# ---------- Prompt ----------

def _construire_prompt_utilisateur(question: str, documents: list[str]) -> str:
    if not documents:
        contexte = (
            "Aucune donnée de projet n'est disponible pour répondre à cette question. "
            "Soit l'index ChromaDB est vide, soit l'utilisateur n'a accès à aucun projet indexé."
        )
    else:
        blocs = "\n\n---\n\n".join(documents)
        contexte = f"Données de projet disponibles :\n\n{blocs}"

    return f"{contexte}\n\nQuestion : {question}"


# ---------- Point d'entrée public ----------

def repondre_question(question: str, context: RequestContext) -> str:
    """Répond à une question en s'appuyant uniquement sur les données des projets
    autorisés pour cet utilisateur.

    Flux :
      1. Recherche ChromaDB filtrée par context.allowed_project_ids
      2. Construction du prompt (contexte + question)
      3. Appel Ollama (modèle local)
      4. Log d'audit
      5. Retour de la réponse

    Lève RuntimeError si Ollama est indisponible."""
    documents = _rechercher_documents(question, context.allowed_project_ids)

    prompt = _construire_prompt_utilisateur(question, documents)

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        reponse_texte: str = response.message.content
    except Exception as exc:
        log_event(
            email=context.authenticated_email,
            project_key=None,
            action="assistant_question",
            success=False,
            detail=f"Erreur Ollama : {exc}",
        )
        raise RuntimeError(
            f"Le modèle Ollama ({OLLAMA_MODEL}) est indisponible : {exc}"
        ) from exc

    log_event(
        email=context.authenticated_email,
        project_key=None,
        action="assistant_question",
        success=True,
        detail=f"question={question[:80]!r} n_docs={len(documents)}",
    )

    return reponse_texte
