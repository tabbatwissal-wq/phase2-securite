"""
Module d'authentification SSO via Microsoft Entra ID (OIDC).
Ce module fonctionne EN PLUS du système existant (X-API-Key),
il ne le remplace pas.
"""

import os
import msal
from dotenv import load_dotenv
load_dotenv()
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = "http://localhost:8000/auth/callback"
SCOPE = ["User.Read"]

msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET,
)


@router.get("/auth/login")
def login():
    """Redirige l'utilisateur vers la page de connexion Microsoft."""
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        redirect_uri=REDIRECT_URI,
    )
    return RedirectResponse(auth_url)


@router.get("/auth/callback")
def callback(request: Request):
    """Reçoit le code de retour de Microsoft et l'échange contre un token."""
    code = request.query_params.get("code")
    if not code:
        return {"error": "Aucun code reçu depuis Microsoft"}

    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        return {"error": result.get("error_description", "Erreur inconnue")}

    email = result.get("id_token_claims", {}).get("preferred_username")
    return {
        "message": "Connexion réussie",
        "email": email,
    }