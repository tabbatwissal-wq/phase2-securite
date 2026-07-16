"""Compatibilité pour la génération de rapports PowerPoint depuis l'interface Streamlit."""

from pptx_generator import generer_rapport as _generer_rapport_pptx


def generer_rapport(chemin_pivot: str = "ProjectReportPivot.json", sortie: str = "rapport_demo.pptx"):
    """Appelle le générateur PPTX existant avec un point d'entrée stable."""
    return _generer_rapport_pptx(chemin_pivot=chemin_pivot, sortie=sortie)
