"""Constantes partagées entre pdf_generator.py et pptx_generator.py."""

STATUS_LABEL = {
    "termine": "Terminé",
    "en_cours": "En cours",
    "a_faire": "À faire",
    "bloque": "Bloqué",
}

PRIORITY_LABEL = {
    "basse": "Basse",
    "moyenne": "Moyenne",
    "haute": "Haute",
    "critique": "Critique",
}

# Codes hexa utilisés dans les deux générateurs
HEX_NAVY  = "#1E3A5F"
HEX_TEAL  = "#0F766E"
HEX_GREEN = "#15803D"
HEX_CORAL = "#C2410C"
HEX_GRAY  = "#475569"
HEX_LIGHT = "#F1F5F9"
HEX_BORDER = "#CBD5E1"

STATUS_HEX_COLOR = {
    "termine": HEX_GREEN,
    "en_cours": HEX_TEAL,
    "a_faire": HEX_GRAY,
    "bloque": HEX_CORAL,
}
