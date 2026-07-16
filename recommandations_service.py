"""
Recommandations automatiques - Phase 3
Génère des suggestions actionnables via Ollama à partir des données
pré-calculées (KPIs Phase 1 + dérive planning Phase 3).

Garanties :
  • Le LLM ne reçoit QUE des données pré-calculées et anonymisées.
    Aucune donnée brute Jira, aucun email, aucun identifiant technique.
  • Le LLM rédige du texte uniquement — tous les chiffres cités dans les
    recommandations viennent du code (Pandas/régression), jamais du modèle.
  • Toute recommandation est retournée avec approuvee=False.
    Elle ne doit jamais être affichée avant validation humaine explicite
    (valider_recommandation_cli ou dialog Streamlit dans app.py).
  • Contrôle d'accès identique au reste du projet : PermissionError si le
    projet n'est pas dans context.allowed_project_ids.

Flux :
  generer_recommandation()  →  Recommandation(approuvee=False)
       │
       └──▶  valider_recommandation_cli()  ou  dialog Streamlit
                  │
                  └──▶  Recommandation(approuvee=True)  →  affichage
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import ollama

from audit_service import log_event
from derive_planning import PrevisionDerive
from security_context import RequestContext

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_RISQUE_LABEL = {
    "faible":                "FAIBLE",
    "modere":                "MODÉRÉ",
    "eleve":                 "ÉLEVÉ",
    "donnees_insuffisantes": "NON CALCULABLE (historique insuffisant)",
}

_SYSTEM_PROMPT = (
    "Tu es un assistant spécialisé dans le suivi de projets informatiques pour Sofrecom. "
    "CONSIGNE ABSOLUE : Tu dois TOUJOURS répondre en FRANÇAIS. "
    "Tu rédiges des recommandations actionnables uniquement à partir des données chiffrées fournies. "
    "Tu ne cites jamais de chiffres autres que ceux qui figurent dans les données du contexte. "
    "Tu ne mentionnes jamais de noms de personnes, d'adresses email ou d'identifiants techniques. "
    "Tes recommandations doivent être concrètes, numérotées, et limitées à 3 à 5 points."
)


# ---------- Modèle de données ----------

@dataclass
class Recommandation:
    """Recommandation générée par le LLM — en attente de validation humaine.

    La propriété approuvee reste False jusqu'à approbation explicite par un
    opérateur. Une recommandation non approuvée ne doit jamais être affichée
    à l'équipe projet ou transmise vers un canal externe (Teams, email, etc.)."""
    project_id: str
    nom_projet: str
    texte: str                   # texte généré par le LLM
    risque_derive: str           # valeur de PrevisionDerive.risque
    justification_derive: str    # valeur de PrevisionDerive.justification
    genere_le: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    approuvee: bool = False


# ---------- Construction du prompt ----------

def _formater_kpis(kpis: list[dict]) -> str:
    """Convertit la liste KPI en texte structuré.
    Filtre de sécurité : supprime tout email éventuellement présent dans un label."""
    lignes: list[str] = []
    for kpi in kpis:
        label  = _EMAIL_RE.sub("[masqué]", str(kpi.get("label", kpi.get("code", "?"))))
        valeur = kpi.get("valeur", 0)
        unite  = kpi.get("unite", "")
        lignes.append(f"  - {label} : {valeur}{unite}")
    return "\n".join(lignes) if lignes else "  (aucun KPI disponible)"


def _construire_prompt(
    nom_projet: str,
    project_id: str,
    kpis: list[dict],
    prevision: PrevisionDerive,
) -> str:
    """Assemble le prompt utilisateur à partir de données pré-calculées uniquement.

    Ce prompt ne contient jamais :
      • de données brutes Jira (tickets, commentaires, champs libres)
      • d'adresses email (filtrées par _EMAIL_RE même si elles glissaient dans un label)
      • d'identifiants techniques internes

    Il contient uniquement :
      • le nom du projet (anonymisé par jira_ai_filter en Phase 2 si indexé)
      • les KPIs calculés par Pandas (Phase 1)
      • la prévision de dérive calculée par régression (Phase 3)"""
    risque_label = _RISQUE_LABEL.get(prevision.risque, prevision.risque.upper())

    lignes_derive: list[str] = [
        f"  - Niveau de risque de dérive : {risque_label}",
    ]
    if prevision.tendance_pct_par_jour is not None:
        lignes_derive.append(
            f"  - Tendance d'avancement : {prevision.tendance_pct_par_jour:.3f} %/jour"
        )
    if prevision.avancement_actuel is not None:
        lignes_derive.append(
            f"  - Avancement actuel : {prevision.avancement_actuel:.1f} %"
        )
    if prevision.jours_couverts is not None:
        lignes_derive.append(
            f"  - Fenêtre analysée : {prevision.n_points} rapport(s) "
            f"sur {prevision.jours_couverts} jour(s)"
        )
    # La justification est entièrement générée par le code, sans donnée brute Jira
    lignes_derive.append(f"  - Analyse : {prevision.justification}")

    return (
        f"Projet : {nom_projet} (réf. interne : {project_id})\n"
        f"Date d'analyse : {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
        f"KPIs actuels (calculés par le système, non modifiables) :\n"
        f"{_formater_kpis(kpis)}\n\n"
        f"Prévision de dérive planning (calcul déterministe, non modifiable) :\n"
        + "\n".join(lignes_derive)
        + "\n\n"
        "En te basant UNIQUEMENT sur les données chiffrées ci-dessus, "
        "rédige 3 à 5 recommandations concrètes et actionnables pour l'équipe projet. "
        "Chaque recommandation doit s'appuyer explicitement sur un chiffre fourni. "
        "Ne cite aucun chiffre absent des données ci-dessus."
    )


# ---------- Génération ----------

def generer_recommandation(
    project_id: str,
    nom_projet: str,
    kpis: list[dict],
    prevision: PrevisionDerive,
    context: RequestContext,
) -> Recommandation:
    """Génère une recommandation LLM à partir des données pré-calculées.

    Lève PermissionError si project_id n'est pas dans context.allowed_project_ids.
    Lève RuntimeError si Ollama est indisponible.

    La recommandation retournée a toujours approuvee=False.
    Elle doit passer par valider_recommandation_cli() ou le dialog Streamlit
    avant d'être affichée ou transmise."""
    if project_id not in context.allowed_project_ids:
        log_event(
            email=context.authenticated_email,
            project_key=project_id,
            action="recommandation_generation",
            success=False,
            detail="Projet hors périmètre",
        )
        raise PermissionError(
            f"Accès refusé : '{project_id}' n'est pas dans le périmètre autorisé "
            f"de {context.authenticated_email}."
        )

    prompt = _construire_prompt(nom_projet, project_id, kpis, prevision)

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        texte: str = response.message.content
    except Exception as exc:
        log_event(
            email=context.authenticated_email,
            project_key=project_id,
            action="recommandation_generation",
            success=False,
            detail=f"Erreur Ollama : {exc}",
        )
        raise RuntimeError(
            f"Le modèle Ollama ({OLLAMA_MODEL}) est indisponible : {exc}"
        ) from exc

    log_event(
        email=context.authenticated_email,
        project_key=project_id,
        action="recommandation_generation",
        success=True,
        detail=f"risque={prevision.risque} texte_len={len(texte)}",
    )

    return Recommandation(
        project_id=project_id,
        nom_projet=nom_projet,
        texte=texte,
        risque_derive=prevision.risque,
        justification_derive=prevision.justification,
    )


# ---------- Validation humaine CLI ----------

def valider_recommandation_cli(recommandation: Recommandation) -> Recommandation:
    """Présente la recommandation à l'opérateur via CLI et demande approbation.

    Met à jour recommandation.approuvee et retourne le même objet (pas de copie).
    Phase 3 : remplacer par un dialog Streamlit dans app.py (adapter cette fonction
    uniquement — le reste du module est indépendant de l'interface)."""
    print(f"\n{'='*64}")
    print(f"  Projet : {recommandation.nom_projet}  (ID : {recommandation.project_id})")
    print(f"  Risque de derive : {recommandation.risque_derive.upper()}")
    print(f"  {recommandation.justification_derive}")
    print(f"\n  --- Recommandations generees par le modele IA ---")
    for ligne in recommandation.texte.splitlines():
        print(f"  {ligne}")
    print(f"{'='*64}")

    try:
        reponse = input("  Approuver ces recommandations ? [o/N] : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Interruption — recommandation rejetee.")
        recommandation.approuvee = False
        return recommandation

    if reponse == "o":
        recommandation.approuvee = True
        print("  -> Approuve.")
    else:
        recommandation.approuvee = False
        print("  -> Rejete.")

    return recommandation
