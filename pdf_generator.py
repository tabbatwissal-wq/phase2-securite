"""
Générateur de rapport PDF - Phase 1 (version ReportLab)
Alternative à pdf_generator.py (WeasyPrint) qui évite les problèmes de
dépendances système GTK/Pango sur Windows. Pur Python.

Installation : pip install reportlab
Utilisation  : python pdf_generator_reportlab.py
"""

import json

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.enums import TA_LEFT

from report_constants import (
    STATUS_LABEL, PRIORITY_LABEL, STATUS_HEX_COLOR,
    HEX_NAVY, HEX_TEAL, HEX_GREEN, HEX_CORAL, HEX_GRAY, HEX_LIGHT, HEX_BORDER,
)

NAVY    = colors.HexColor(HEX_NAVY)
TEAL    = colors.HexColor(HEX_TEAL)
GREEN   = colors.HexColor(HEX_GREEN)
CORAL   = colors.HexColor(HEX_CORAL)
GRAY    = colors.HexColor(HEX_GRAY)
LIGHT_BG = colors.HexColor(HEX_LIGHT)

STATUS_COLOR = {k: colors.HexColor(v) for k, v in STATUS_HEX_COLOR.items()}

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitreRapport", fontName="Helvetica-Bold", fontSize=24,
                           leading=28, textColor=colors.white, spaceAfter=6))
styles.add(ParagraphStyle(name="SousTitreRapport", fontName="Helvetica", fontSize=11,
                           leading=14, textColor=colors.HexColor("#CBD5E1")))
styles.add(ParagraphStyle(name="Section", fontName="Helvetica-Bold", fontSize=15,
                           leading=18, textColor=NAVY, spaceBefore=16, spaceAfter=8))
styles.add(ParagraphStyle(name="KpiValeur", fontName="Helvetica-Bold", fontSize=18,
                           leading=22, textColor=TEAL, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="KpiLabel", fontName="Helvetica", fontSize=9,
                           leading=11, textColor=GRAY, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="Cell", fontName="Helvetica", fontSize=9.5, leading=12,
                           textColor=colors.HexColor("#1E293B")))
styles.add(ParagraphStyle(name="CellBold", fontName="Helvetica-Bold", fontSize=9.5,
                           leading=12, textColor=colors.white))


def charger_pivot(chemin: str = "ProjectReportPivot.json") -> dict:
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def construire_bandeau_titre(pivot: dict):
    """Bandeau de titre sur fond navy, en tableau 1x1 pour contrôler le fond."""
    projet = pivot["project"]
    genere_le = pivot["reporting_period"]["genere_le"][:10]

    contenu = [
        Paragraph(projet["nom_projet"], styles["TitreRapport"]),
        Paragraph(f"Rapport généré le {genere_le} — Projet {projet['cle_jira']}",
                   styles["SousTitreRapport"]),
    ]
    table = Table([[contenu]], colWidths=[17 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
    ]))
    return table


def construire_grille_kpis(pivot: dict):
    kpis = pivot.get("kpis", [])
    table_data = []
    for i in range(0, len(kpis), 3):
        row_cells = []
        for kpi in kpis[i:i + 3]:
            unite = kpi.get("unite") or ""
            cell_content = [
                Paragraph(f"{kpi['valeur']:g}{unite}", styles["KpiValeur"]),
                Paragraph(kpi["label"], styles["KpiLabel"]),
            ]
            row_cells.append(cell_content)
        while len(row_cells) < 3:
            row_cells.append([Paragraph("", styles["Cell"])])
        table_data.append(row_cells)

    t = Table(table_data, colWidths=[5.6 * cm] * 3, rowHeights=[1.8 * cm] * len(table_data))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def construire_tableau_taches(pivot: dict):
    tasks = pivot.get("tasks", [])
    header = [Paragraph(h, styles["CellBold"]) for h in ["Ticket", "Titre", "Statut", "Priorité"]]
    data = [header]

    for task in tasks:
        statut = task["statut"]
        couleur = STATUS_COLOR.get(statut, GRAY)
        statut_style = ParagraphStyle(
            name=f"Statut_{statut}", parent=styles["Cell"],
            textColor=couleur, fontName="Helvetica-Bold"
        )
        data.append([
            Paragraph(task["task_id"], styles["Cell"]),
            Paragraph(task["titre"], styles["Cell"]),
            Paragraph(STATUS_LABEL.get(statut, statut), statut_style),
            Paragraph(PRIORITY_LABEL.get(task["priorite"], task["priorite"]), styles["Cell"]),
        ])

    t = Table(data, colWidths=[2 * cm, 8 * cm, 3.5 * cm, 3.5 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def generer_rapport(chemin_pivot: str = "ProjectReportPivot.json", sortie: str = "rapport_demo.pdf"):
    pivot = charger_pivot(chemin_pivot)

    story = [
        construire_bandeau_titre(pivot),
        Spacer(1, 0.6 * cm),
        Paragraph("Indicateurs clés", styles["Section"]),
        construire_grille_kpis(pivot),
        Paragraph("Détail des tâches", styles["Section"]),
        construire_tableau_taches(pivot),
    ]

    doc = SimpleDocTemplate(
        sortie, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=0, bottomMargin=1.5 * cm,
    )
    doc.build(story)
    print(f"Rapport PDF généré : {sortie}")


if __name__ == "__main__":
    generer_rapport()