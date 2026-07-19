"""
Module d'authentification SSO via Microsoft Entra ID (OIDC).
Ce module fonctionne EN PLUS du système existant (X-API-Key),
il ne le remplace pas.
"""

import os
import msal
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = "http://localhost:8000/auth/callback"
SCOPE = ["User.Read"]


def _creer_msal_app():
    """Crée le client MSAL à la demande (pas au chargement du module),
    pour que l'import de ce fichier ne plante pas si les variables Azure
    ne sont pas configurées (ex: en CI, où le SSO n'est pas testé)."""
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )


@router.get("/auth/login")
def login():
    """Redirige l'utilisateur vers la page de connexion Microsoft."""
    msal_app = _creer_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        redirect_uri=REDIRECT_URI,
    )
    return RedirectResponse(auth_url)


@router.get("/auth/callback")
def callback(request: Request):
    """Reçoit le code de retour de Microsoft, l'échange contre un token,
    puis crée un token de session signé (à utiliser dans l'en-tête
    X-Session-Token pour les appels suivants)."""
    code = request.query_params.get("code")
    if not code:
        return {"error": "Aucun code reçu depuis Microsoft"}

    msal_app = _creer_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        return {"error": result.get("error_description", "Erreur inconnue")}

    email = result.get("id_token_claims", {}).get("preferred_username")

    session_token = jwt.encode(
        {
            "email": email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=8),
        },
        SESSION_SECRET,
        algorithm="HS256",
    )

    return {
        "message": "Connexion réussie",
        "email": email,
        "session_token": session_token,
    }