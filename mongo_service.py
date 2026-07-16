"""
Service MongoDB - Phase 1
Stocke chaque ProjectReportPivot généré dans une base MongoDB locale.

Installation :
  pip install pymongo

Prérequis :
  MongoDB Community Server installé et lancé en local (service Windows).
  Par défaut, il écoute sur mongodb://localhost:27017
"""

from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "sofrecom_reporting"
COLLECTION_NAME = "project_reports"


def obtenir_collection():
    """Ouvre la connexion et renvoie la collection MongoDB à utiliser."""
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except ConnectionFailure:
        print("Impossible de se connecter à MongoDB.")
        print("Vérifiez que le service tourne : Get-Service -Name MongoDB")
        raise
    db = client[DB_NAME]
    return db[COLLECTION_NAME]


def sauvegarder_pivot(pivot_dict: dict) -> str:
    """Insère un ProjectReportPivot (déjà converti en dict) dans MongoDB.
    Renvoie l'identifiant du document créé."""
    collection = obtenir_collection()

    document = {
        **pivot_dict,
        "inserted_at": datetime.now(timezone.utc),
    }
    result = collection.insert_one(document)
    return str(result.inserted_id)


def lister_rapports(project_id: str | None = None, limite: int = 20) -> list[dict]:
    """Liste les derniers rapports générés, filtrés par projet si précisé."""
    collection = obtenir_collection()
    filtre = {"project.project_id": project_id} if project_id else {}
    curseur = collection.find(filtre).sort("inserted_at", -1).limit(limite)
    return list(curseur)


if __name__ == "__main__":
    # Test rapide de connexion
    collection = obtenir_collection()
    print(f"Connexion réussie à MongoDB — base '{DB_NAME}', collection '{COLLECTION_NAME}'")
    print(f"Nombre de documents actuellement stockés : {collection.count_documents({})}")
