"""
Service d'audit - Phase 1
Journalise chaque tentative d'authentification et chaque décision d'accès
(autorisé ou refusé) dans une collection MongoDB dédiée, séparée du
stockage des rapports eux-mêmes.

Installation : pip install pymongo
"""

from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "sofrecom_reporting"
AUDIT_COLLECTION = "audit_logs"


def _obtenir_collection_audit():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = client[DB_NAME]
    return db[AUDIT_COLLECTION]


def log_event(email: str | None, project_key: str | None, action: str,
              success: bool, detail: str | None = None) -> None:
    """Enregistre un événement d'audit. Ne doit jamais faire planter la
    requête principale si MongoDB est indisponible — on log l'erreur en
    console et on continue, l'audit ne doit pas bloquer le service."""
    evenement = {
        "timestamp": datetime.now(timezone.utc),
        "email": email,
        "project_key": project_key,
        "action": action,
        "success": success,
        "detail": detail,
    }
    try:
        collection = _obtenir_collection_audit()
        collection.insert_one(evenement)
    except PyMongoError as e:
        print(f"[audit] Impossible d'écrire le log d'audit : {e}")


def lister_logs(email: str | None = None, limite: int = 50) -> list[dict]:
    """Liste les derniers événements d'audit, filtrés par utilisateur si précisé."""
    collection = _obtenir_collection_audit()
    filtre = {"email": email} if email else {}
    return list(collection.find(filtre).sort("timestamp", -1).limit(limite))


if __name__ == "__main__":
    log_event(email="test@example.com", project_key="KAN", action="test_manuel", success=True)
    print("Événement de test inséré. Derniers logs :")
    for log in lister_logs(limite=5):
        print(f"  {log['timestamp']} | {log['email']} | {log['action']} | "
              f"succès={log['success']} | {log.get('detail', '')}")
