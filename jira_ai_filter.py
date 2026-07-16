"""
Filtre IA - Phase 2
Transforme un ProjectReportPivot brut (depuis MongoDB) en ContenuSurAI :
  • Anonymisation : suppression de responsable_email et de tous les identifiants
    techniques (source, _id MongoDB, inserted_at…)
  • Structuration : résumé KPIs en langue naturelle + liste de titres de tâches
  • Détection d'anomalies : tickets en retard, bloqués ou critiques non terminés

Ce module est la seule porte d'entrée autorisée vers ChromaDB.
Aucun dict brut MongoDB ne peut passer directement à l'indexation.
"""

from dataclasses import dataclass, field


@dataclass
class ContenuSurAI:
    """Représentation anonymisée et structurée d'un rapport de projet.
    Seul format autorisé à entrer dans ChromaDB — garantit l'absence
    de données personnelles (email, identifiants source, _id Mongo)."""

    project_id: str
    nom_projet: str
    genere_le: str              # "YYYY-MM-DD" uniquement
    resume_kpis: str            # texte en langue naturelle, depuis les KPIs Pandas
    titres_taches: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)

    def to_texte_indexable(self) -> str:
        """Document texte plat destiné à la recherche sémantique (ChromaDB).
        Combine resume_kpis + titres_taches en un seul bloc cohérent."""
        lignes = [
            f"Projet : {self.nom_projet} (ID : {self.project_id})",
            f"Rapport du {self.genere_le}",
            "",
            "Indicateurs clés :",
            self.resume_kpis,
            "",
            "Tâches du projet :",
        ]
        lignes += [f"- {titre}" for titre in self.titres_taches]
        if self.anomalies:
            lignes += ["", "Points d'attention :"]
            lignes += [f"- {a}" for a in self.anomalies]
        return "\n".join(lignes)


def detecter_anomalies(pivot_dict: dict) -> list[str]:
    """Identifie les situations à signaler (retards, blocages, critiques).
    Aucun calcul IA — uniquement des comparaisons sur les données du pivot."""
    tasks = pivot_dict.get("tasks", [])
    en_retard = sum(1 for t in tasks if t.get("en_retard"))
    bloques   = sum(1 for t in tasks if t.get("statut") == "bloque")
    critiques_non_termines = sum(
        1 for t in tasks
        if t.get("priorite") == "critique" and t.get("statut") != "termine"
    )

    anomalies = []
    if en_retard:
        anomalies.append(f"{en_retard} ticket(s) en retard")
    if bloques:
        anomalies.append(f"{bloques} ticket(s) bloqué(s)")
    if critiques_non_termines:
        anomalies.append(f"{critiques_non_termines} ticket(s) critique(s) non terminé(s)")
    return anomalies


def preparer_contenu_pour_ia(pivot_dict: dict) -> ContenuSurAI:
    """Transforme un pivot MongoDB brut en ContenuSurAI anonymisé.

    Garantit explicitement :
      - Pas de responsable_email dans le résultat
      - Pas d'identifiant source (source_record_id, _id, inserted_at)
      - Les titres de tâches sont copiés tels quels (pas de résumé IA ici)
    """
    project = pivot_dict.get("project", {})
    period  = pivot_dict.get("reporting_period", {})
    kpis    = {k["code"]: k for k in pivot_dict.get("kpis", [])}
    tasks   = pivot_dict.get("tasks", [])

    def _val(code: str, default: float = 0.0) -> float:
        kpi = kpis.get(code)
        return float(kpi["valeur"]) if kpi else default

    total      = int(_val("total_tickets"))
    avancement = _val("avancement_pct")
    termines   = int(_val("tickets_termines"))
    en_cours   = int(_val("tickets_en_cours"))
    en_retard  = int(_val("tickets_en_retard"))
    critiques  = int(_val("tickets_critiques"))

    resume_kpis = (
        f"{total} tickets au total — {avancement:.1f}% terminés ({termines} tickets). "
        f"{en_cours} en cours, {en_retard} en retard, {critiques} critique(s)."
    )

    # Titres uniquement — aucun email, aucun identifiant source
    titres = [t["titre"] for t in tasks if t.get("titre")]

    return ContenuSurAI(
        project_id=project.get("project_id", "INCONNU"),
        nom_projet=project.get("nom_projet", "Projet sans nom"),
        genere_le=str(period.get("genere_le", ""))[:10],
        resume_kpis=resume_kpis,
        titres_taches=titres,
        anomalies=detecter_anomalies(pivot_dict),
    )
