"""
Configuration centralisée des logs pour le projet.
À importer une seule fois (déjà fait dans main.py) pour que tous les
modules qui utilisent logging.getLogger(__name__) héritent du même
format et niveau.
"""

import logging


def configurer_logs(niveau: int = logging.INFO) -> None:
    """Configure le format standard des logs pour toute l'application."""
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )