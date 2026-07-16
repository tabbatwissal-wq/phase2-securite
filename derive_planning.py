"""
Calcul de dérive planning - Phase 3
Analyse l'historique des rapports MongoDB d'un projet pour estimer le risque
de retard. Le résultat est entièrement déterministe (régression linéaire sur
l'avancement_pct historique) — le LLM n'intervient à aucun moment ici.

Principe identique aux KPIs Phase 1 : les chiffres viennent du code, jamais
de l'IA.

Règles de risque (par ordre de priorité) :
  • donnees_insuffisantes : < HISTORIQUE_MINIMUM rapports dans MongoDB
  • faible   : avancement ≥ 95 %, ou pente ≥ 0.5 %/j avec peu de retards
  • modere   : pente 0.1–0.5 %/j, ou bonne pente mais beaucoup de retards
  • eleve    : pente négative, quasi nulle (< 0.1 %/j), ou lente + >30% retards
"""

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from audit_service import log_event
from mongo_service import lister_rapports
from security_context import RequestContext

HISTORIQUE_MINIMUM = 2   # nombre minimum de rapports pour estimer une tendance

NiveauRisque = Literal["faible", "modere", "eleve", "donnees_insuffisantes"]


# ---------- Modèles de données ----------

@dataclass
class PointHistorique:
    """Un instantané des KPIs clés à une date donnée."""
    date_rapport: str        # YYYY-MM-DD
    avancement_pct: float    # 0.0 – 100.0
    tickets_en_retard: int
    tickets_total: int


@dataclass
class PrevisionDerive:
    """Résultat du calcul de dérive pour un projet.

    Si suffisant=False, risque vaut 'donnees_insuffisantes' et les champs
    numériques (tendance, jours_couverts) sont None."""
    project_id: str
    suffisant: bool
    n_points: int
    risque: NiveauRisque
    tendance_pct_par_jour: float | None   # pente de la régression linéaire
    avancement_actuel: float | None       # valeur la plus récente
    avancement_initial: float | None      # valeur la plus ancienne de la fenêtre
    jours_couverts: int | None            # jours entre premier et dernier rapport
    justification: str                    # explication chiffrée lisible
    points: list[PointHistorique] = field(default_factory=list)


# ---------- Extraction ----------

def _extraire_kpi(kpis: list[dict], code: str, defaut: float = 0.0) -> float:
    for kpi in kpis:
        if kpi.get("code") == code:
            return float(kpi.get("valeur", defaut))
    return defaut


def _vers_date_iso(valeur) -> str:
    """Convertit un champ MongoDB date/datetime/str en YYYY-MM-DD."""
    if isinstance(valeur, datetime):
        return valeur.date().isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, str):
        return valeur[:10]
    return str(valeur)[:10]


def _extraire_points(rapports: list[dict]) -> list[PointHistorique]:
    """Transforme la liste brute MongoDB en PointHistorique."""
    points: list[PointHistorique] = []
    for rapport in rapports:
        kpis = rapport.get("kpis", [])
        points.append(PointHistorique(
            date_rapport=_vers_date_iso(
                rapport.get("reporting_period", {}).get("genere_le", "")
            ),
            avancement_pct=_extraire_kpi(kpis, "avancement_pct"),
            tickets_en_retard=int(_extraire_kpi(kpis, "tickets_en_retard")),
            tickets_total=int(_extraire_kpi(kpis, "total_tickets")),
        ))
    return points


# ---------- Calcul de tendance ----------

def _calculer_prevision(project_id: str, points: list[PointHistorique]) -> PrevisionDerive:
    """Régression linéaire sur l'avancement, puis classification du risque.
    Reçoit les points déjà triés dans l'ordre chronologique (le plus ancien en premier)."""

    # Conversion des dates en offsets de jours depuis le premier rapport
    try:
        dates = [date.fromisoformat(p.date_rapport) for p in points]
    except (ValueError, TypeError):
        today = date.today()
        dates = [today - timedelta(days=len(points) - i - 1) for i in range(len(points))]

    jour0 = dates[0]
    x = [float((d - jour0).days) for d in dates]
    y = [p.avancement_pct for p in points]

    # Régression linéaire — impossible si tous les rapports ont la même date
    if len(set(x)) >= 2:
        try:
            reg = statistics.linear_regression(x, y)
            slope = reg.slope
        except statistics.StatisticsError:
            slope = 0.0
    else:
        slope = 0.0   # même date pour tous les rapports → pente inestimable

    avancement_actuel  = points[-1].avancement_pct
    avancement_initial = points[0].avancement_pct
    jours_couverts     = int((dates[-1] - dates[0]).days)
    retard_actuel      = points[-1].tickets_en_retard
    total_actuel       = points[-1].tickets_total
    taux_retard        = retard_actuel / total_actuel if total_actuel > 0 else 0.0

    # --- Classification du risque ---
    if avancement_actuel >= 95.0:
        risque: NiveauRisque = "faible"
        justification = (
            f"Projet quasi terminé : avancement actuel à {avancement_actuel:.1f}%."
        )

    elif slope < 0:
        risque = "eleve"
        variation = avancement_actuel - avancement_initial
        justification = (
            f"Régression détectée : l'avancement a baissé de {abs(variation):.1f} pt(s) "
            f"sur {jours_couverts} jour(s) "
            f"(tendance : {slope:.3f}%/jour). "
            f"{retard_actuel}/{total_actuel} ticket(s) en retard."
        )

    elif slope < 0.1:
        risque = "eleve"
        justification = (
            f"Avancement quasi nul sur {jours_couverts} jour(s) : "
            f"{avancement_initial:.1f}% → {avancement_actuel:.1f}% "
            f"(tendance : {slope:.3f}%/jour). "
            f"{retard_actuel}/{total_actuel} ticket(s) en retard."
        )

    elif slope < 0.5:
        if taux_retard > 0.3:
            risque = "eleve"
            justification = (
                f"Progression lente ({slope:.3f}%/jour) aggravée par un taux de retard élevé : "
                f"{retard_actuel}/{total_actuel} tickets ({taux_retard * 100:.0f}%) en retard."
            )
        else:
            risque = "modere"
            jours_restants = (100.0 - avancement_actuel) / slope if slope > 0 else None
            estimation = (
                f"Complétion estimée dans ~{jours_restants:.0f} jour(s)."
                if jours_restants is not None
                else "Durée de complétion non estimable (progression nulle)."
            )
            justification = (
                f"Progression modérée : {slope:.3f}%/jour sur {jours_couverts} jour(s) "
                f"({avancement_initial:.1f}% → {avancement_actuel:.1f}%). "
                f"{estimation} "
                f"{retard_actuel}/{total_actuel} ticket(s) en retard."
            )

    else:   # slope >= 0.5
        if taux_retard > 0.4:
            risque = "modere"
            justification = (
                f"Bonne progression ({slope:.3f}%/jour) mais {retard_actuel}/{total_actuel} "
                f"tickets en retard ({taux_retard * 100:.0f}%) — à surveiller."
            )
        else:
            risque = "faible"
            jours_restants = (100.0 - avancement_actuel) / slope
            justification = (
                f"Progression régulière : {slope:.3f}%/jour sur {jours_couverts} jour(s) "
                f"({avancement_initial:.1f}% → {avancement_actuel:.1f}%). "
                f"Complétion estimée dans ~{jours_restants:.0f} jour(s). "
                f"{retard_actuel}/{total_actuel} ticket(s) en retard."
            )

    return PrevisionDerive(
        project_id=project_id,
        suffisant=True,
        n_points=len(points),
        risque=risque,
        tendance_pct_par_jour=round(slope, 4),
        avancement_actuel=avancement_actuel,
        avancement_initial=avancement_initial,
        jours_couverts=jours_couverts,
        justification=justification,
        points=points,
    )


# ---------- Point d'entrée public ----------

def calculer_derive(
    project_id: str,
    context: RequestContext,
    limite: int = 20,
) -> PrevisionDerive:
    """Calcule la prévision de dérive planning pour un projet autorisé.

    Contrôle d'accès : lève PermissionError si project_id n'est pas dans
    context.allowed_project_ids (même périmètre que le reste du projet).

    Données insuffisantes : renvoie une PrevisionDerive avec
    risque='donnees_insuffisantes' si MongoDB contient moins de
    HISTORIQUE_MINIMUM rapports pour ce projet — jamais de fausse tendance.

    Ne sollicite aucun LLM : les chiffres viennent uniquement de l'historique
    MongoDB et du calcul de régression."""
    if project_id not in context.allowed_project_ids:
        log_event(
            email=context.authenticated_email,
            project_key=project_id,
            action="derive_calcul",
            success=False,
            detail="Projet hors périmètre",
        )
        raise PermissionError(
            f"Accès refusé : '{project_id}' n'est pas dans le périmètre autorisé "
            f"de {context.authenticated_email}."
        )

    # lister_rapports renvoie les plus récents en premier → on inverse pour l'ordre chronologique
    rapports = list(reversed(lister_rapports(project_id=project_id, limite=limite)))
    points = _extraire_points(rapports)

    if len(points) < HISTORIQUE_MINIMUM:
        log_event(
            email=context.authenticated_email,
            project_key=project_id,
            action="derive_calcul",
            success=True,
            detail=f"donnees_insuffisantes n_points={len(points)}",
        )
        return PrevisionDerive(
            project_id=project_id,
            suffisant=False,
            n_points=len(points),
            risque="donnees_insuffisantes",
            tendance_pct_par_jour=None,
            avancement_actuel=points[0].avancement_pct if points else None,
            avancement_initial=points[0].avancement_pct if points else None,
            jours_couverts=None,
            justification=(
                f"Historique insuffisant : {len(points)} rapport(s) disponible(s) "
                f"pour '{project_id}', minimum requis : {HISTORIQUE_MINIMUM}. "
                "Générez au moins un rapport supplémentaire avant de relancer l'analyse."
            ),
            points=points,
        )

    prevision = _calculer_prevision(project_id, points)

    log_event(
        email=context.authenticated_email,
        project_key=project_id,
        action="derive_calcul",
        success=True,
        detail=(
            f"risque={prevision.risque} "
            f"slope={prevision.tendance_pct_par_jour} "
            f"n_points={prevision.n_points}"
        ),
    )

    return prevision
