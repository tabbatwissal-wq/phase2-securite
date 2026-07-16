"""Compatibilité pour la génération de rapports PDF depuis l'interface Streamlit."""

from pdf_generator import generer_rapport as _generer_rapport_pdf


def generer_rapport(chemin_pivot: str = "ProjectReportPivot.json", sortie: str = "rapport_demo.pdf"):
    """Appelle le générateur PDF existant avec un point d'entrée stable."""
    return _generer_rapport_pdf(chemin_pivot=chemin_pivot, sortie=sortie)
