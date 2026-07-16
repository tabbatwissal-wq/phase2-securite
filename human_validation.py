"""
Validation humaine - Phase 2
Présente chaque ContenuSurAI à un opérateur (CLI) et ne retourne que les
contenus explicitement approuvés. Aucun document n'entre dans ChromaDB
sans passer par cette porte.

Phase 3 : remplacer l'interaction CLI par un formulaire Streamlit ou
un message Teams interactif (adapter uniquement cette fonction valider_lot).
"""

from jira_ai_filter import ContenuSurAI


def _afficher_apercu(contenu: ContenuSurAI, index: int, total: int) -> None:
    print(f"\n{'='*62}")
    print(f"  [{index}/{total}]  {contenu.nom_projet}  (ID : {contenu.project_id})")
    print(f"  Rapport du : {contenu.genere_le}")
    print(f"  {contenu.resume_kpis}")
    if contenu.anomalies:
        print(f"  /!\\ {', '.join(contenu.anomalies)}")
    apercu_taches = contenu.titres_taches[:3]
    suite = " …" if len(contenu.titres_taches) > 3 else ""
    print(f"  Tâches ({len(contenu.titres_taches)}) : {', '.join(apercu_taches)}{suite}")
    print(f"{'='*62}")


def valider_lot(contenus: list[ContenuSurAI]) -> list[ContenuSurAI]:
    """Présente chaque contenu à l'opérateur et renvoie uniquement les approuvés.
    Un contenu refusé ou non répondu n'est jamais indexé.

    Retourne une liste contenant les mêmes objets que l'entrée (pas de copie),
    ce qui permet à l'appelant de retrouver les doc_ids associés par identité."""
    if not contenus:
        print("[validation] Aucun contenu à valider.")
        return []

    print(f"\n[validation] {len(contenus)} rapport(s) à valider avant indexation ChromaDB.")
    approuves: list[ContenuSurAI] = []

    for i, contenu in enumerate(contenus, start=1):
        _afficher_apercu(contenu, i, len(contenus))
        try:
            reponse = input("  Approuver pour indexation ? [o/N] : ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interruption — les contenus restants sont rejetés.")
            break

        if reponse == "o":
            approuves.append(contenu)
            print("  -> Approuve.")
        else:
            print("  -> Rejete, ne sera pas indexe.")

    print(
        f"\n[validation] Résultat : {len(approuves)}/{len(contenus)} "
        "rapport(s) approuvé(s)."
    )
    return approuves
