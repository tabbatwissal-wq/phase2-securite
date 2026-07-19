"""
Vérifie que le fichier .env n'est jamais présent dans le dépôt Git,
même par erreur. Ce test doit toujours passer en CI comme en local.
"""

import subprocess


def test_env_est_ignore_par_git():
    """.env doit être ignoré par git (présent dans .gitignore et
    non suivi par le dépôt)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        capture_output=True,
    )
    assert result.returncode == 0, (
        ".env n'est PAS ignoré par git ! Vérifiez le fichier .gitignore "
        "immédiatement — un secret pourrait être exposé."
    )


def test_env_absent_du_suivi_git():
    """.env ne doit apparaître dans aucun commit suivi actuellement."""
    result = subprocess.run(
        ["git", "ls-files", ".env"],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", (
        ".env est actuellement suivi par git ! Il faut le retirer "
        "immédiatement avec 'git rm --cached .env'."
    )