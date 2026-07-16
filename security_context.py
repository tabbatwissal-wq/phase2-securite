"""
Sécurité - Phase 1
RequestContext : construit exclusivement par le backend après validation
d'un token. Le client ne peut jamais imposer lui-même son email ou ses
projets autorisés — ces informations viennent uniquement de la config
serveur (.env), jamais d'un champ envoyé par l'appelant.

Support multi-utilisateurs : plusieurs tokens peuvent être configurés,
chacun avec son propre email et son propre périmètre de projets autorisés.

Installation : pip install fastapi
"""

import json
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from audit_service import log_event


class RequestContext(BaseModel):
    """Contexte de sécurité — jamais accepté directement depuis le frontend,
    toujours reconstruit par le backend à partir d'un token validé."""
    request_id: UUID = Field(default_factory=uuid4)
    authenticated_email: EmailStr
    allowed_project_ids: list[str] = Field(default_factory=list)
    requested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


def _charger_config_acces() -> dict:
    """Charge la correspondance token -> (email, projets autorisés).

    Deux modes possibles :
    1. Multi-utilisateurs (recommandé) : API_USERS_JSON contient un JSON
       du type {"token1": {"email": "...", "allowed_project_ids": [...]}, ...}
    2. Utilisateur unique (rétrocompatibilité POC) : API_ACCESS_TOKEN,
       API_USER_EMAIL, API_ALLOWED_PROJECTS.
    """
    users_json = os.getenv("API_USERS_JSON")
    if users_json:
        try:
            config = json.loads(users_json)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"API_USERS_JSON invalide : {e}")
        return config

    # Repli sur l'ancien mode utilisateur unique, pour ne pas casser
    # les installations existantes.
    token = os.getenv("API_ACCESS_TOKEN")
    email = os.getenv("API_USER_EMAIL")
    projets = os.getenv("API_ALLOWED_PROJECTS", "")

    if not token or not email:
        raise RuntimeError(
            "Aucune configuration d'accès trouvée : définissez API_USERS_JSON "
            "(multi-utilisateurs) ou API_ACCESS_TOKEN + API_USER_EMAIL (mode simple)."
        )

    return {
        token: {
            "email": email,
            "allowed_project_ids": [p.strip() for p in projets.split(",") if p.strip()],
        }
    }


def get_request_context(x_api_key: str | None = Header(default=None)) -> RequestContext:
    """Dépendance FastAPI : valide le token reçu dans l'en-tête X-API-Key
    et construit le RequestContext correspondant. Lève une erreur 401 si
    le token est invalide ou absent. Chaque tentative est journalisée."""
    if x_api_key is None:
        log_event(email=None, project_key=None, action="auth", success=False,
                   detail="En-tête X-API-Key manquant")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="En-tête X-API-Key manquant.",
        )

    config_acces = _charger_config_acces()
    entree = config_acces.get(x_api_key)

    if entree is None:
        log_event(email=None, project_key=None, action="auth", success=False,
                   detail="Token API invalide")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token API invalide ou manquant.",
        )

    log_event(email=entree["email"], project_key=None, action="auth", success=True)

    return RequestContext(
        authenticated_email=entree["email"],
        allowed_project_ids=entree["allowed_project_ids"],
    )


def construire_context_depuis_token(token: str) -> RequestContext | None:
    """Construit un RequestContext depuis un token brut.
    Retourne None si le token est invalide.
    Utilisé par les interfaces non-FastAPI (Streamlit, scripts CLI)."""
    try:
        config = _charger_config_acces()
    except RuntimeError:
        return None
    entree = config.get(token)
    if not entree:
        return None
    return RequestContext(
        authenticated_email=entree["email"],
        allowed_project_ids=entree["allowed_project_ids"],
    )


def verifier_acces_projet(project_key: str, context: RequestContext) -> None:
    """Bloque l'accès si le projet demandé n'est pas dans le périmètre
    autorisé du contexte. C'est ici, et nulle part ailleurs, que la
    décision d'autorisation est prise. Chaque décision est journalisée."""
    if project_key not in context.allowed_project_ids:
        log_event(email=context.authenticated_email, project_key=project_key,
                   action="access_project", success=False, detail="Projet hors périmètre")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accès interdit au projet {project_key}.",
        )
    log_event(email=context.authenticated_email, project_key=project_key,
              action="access_project", success=True)