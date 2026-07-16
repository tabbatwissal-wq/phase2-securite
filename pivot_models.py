"""
Objet Pivot - Phase 1
Le contrat de données central entre les connecteurs (Jira) et les générateurs
de rapports. Aucune source (Jira, Excel, Teams) n'est visible en dehors de
cette structure une fois la normalisation effectuée.

Installation : pip install "pydantic[email]>=2.0" --break-system-packages
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictModel(BaseModel):
    """Configuration commune à tous les objets métier.

    extra="forbid" empêche l'introduction silencieuse de champs inconnus
    dans les données normalisées — toute donnée non prévue est rejetée.
    """
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class TaskStatus(str, Enum):
    A_FAIRE = "a_faire"
    EN_COURS = "en_cours"
    TERMINE = "termine"
    BLOQUE = "bloque"


class Priority(str, Enum):
    BASSE = "basse"
    MOYENNE = "moyenne"
    HAUTE = "haute"
    CRITIQUE = "critique"


class SourceSystem(str, Enum):
    JIRA = "jira"
    EXCEL = "excel"
    TEAMS = "teams"
    MANUEL = "manuel"


class SourceReference(StrictModel):
    """Traçabilité exacte de chaque donnée — d'où elle vient, quand elle a
    été extraite, et quel champ d'origine l'a produite."""
    source_system: SourceSystem
    source_record_id: str
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    champ_origine: Optional[str] = None


class ProjectTask(StrictModel):
    """Un ticket Jira normalisé — peu importe que la source s'appelle
    'issue' (Jira), 'Tâche' (Excel) ou autre chose, ici c'est toujours
    ProjectTask."""
    task_id: str
    titre: str
    statut: TaskStatus
    priorite: Priority = Priority.MOYENNE
    responsable_email: Optional[EmailStr] = None
    date_echeance: Optional[date] = None
    en_retard: bool = False
    source: SourceReference


class KPI(StrictModel):
    """Un indicateur calculé — jamais par l'IA, toujours par du code
    déterministe (Pandas)."""
    code: str
    label: str
    valeur: float
    unite: Optional[str] = None
    commentaire: Optional[str] = None


class ProjectIdentity(StrictModel):
    project_id: str
    nom_projet: str
    cle_jira: str


class ReportingPeriod(StrictModel):
    genere_le: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ProjectReportPivot(StrictModel):
    """L'objet racine — le seul format que voient les générateurs de
    rapports (PPTX/PDF) et le moteur IA. Indépendant de Jira, Excel ou
    Teams."""
    schema_version: str = "1.0.0"

    project: ProjectIdentity
    reporting_period: ReportingPeriod

    kpis: list[KPI] = Field(default_factory=list)
    tasks: list[ProjectTask] = Field(default_factory=list)

    resume_executif: Optional[str] = None  # rempli par le moteur IA, jamais par le code
