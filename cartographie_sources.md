# Cartographie des sources de données — Phase 1

## Objectif

Documenter précisément quelles données sont récupérées, depuis quelles sources,
et par quelle méthode d'authentification sécurisée — avant tout développement.

---

## Source 1 — Jira (implémentée en Phase 1)

### Champs récupérés

| Champ Jira (API) | Nom technique | Description | Utilisation dans le rapport |
|---|---|---|---|
| `key` | `issue.key` | Identifiant unique du ticket (ex: PTI-12) | Traçabilité (SourceReference) |
| `fields.summary` | `issue.fields.summary` | Titre du ticket | Affichage dans le rapport |
| `fields.status.name` | `issue.fields.status.name` | Statut (À faire / En cours / Terminé) | Calcul du % d'avancement |
| `fields.priority.name` | `issue.fields.priority.name` | Priorité (Basse à Critique) | Tri et alertes |
| `fields.assignee.emailAddress` | `issue.fields.assignee` | Responsable du ticket | Filtrage par utilisateur |
| `fields.duedate` | `issue.fields.duedate` | Date d'échéance prévue | Détection de retard |
| `fields.created` | `issue.fields.created` | Date de création | Traçabilité |
| `fields.updated` | `issue.fields.updated` | Dernière modification | Traçabilité |

### Méthode d'accès

- **Protocole** : REST API v3 (`GET /rest/api/3/search`)
- **Authentification** : Token API (Basic Auth : email + token)
- **Portée** : Un seul projet à la fois, filtré par `project = "CLE_PROJET"` dans la requête JQL
- **Sécurité** : Le token n'est jamais écrit en dur dans le code — chargé depuis un fichier `.env`
  non commité dans le dépôt Git

---

## Source 2 — Teams (planifiée, Phase 3 — non implémentée actuellement)

### Champs prévus

| Champ prévu | Description | Utilisation prévue |
|---|---|---|
| Transcript de réunion | Texte complet du compte-rendu | Indexation dans la base vectorielle (RAG) |
| Date de réunion | Horodatage | Traçabilité |
| Participants | Liste des participants | Contexte pour l'analyse de sensibilité |

### Méthode d'accès prévue

- OAuth délégué (Microsoft Graph API) — consentement individuel, pas d'accès administrateur global
- Passage obligatoire par un analyseur de sensibilité (détection PII) avant tout stockage
- Validation humaine avant indexation définitive

**Statut : documenté mais non développé — dépendance externe (Azure AD) à valider avant
implémentation, voir décisions d'architecture antérieures.**

---

## Ce que cette cartographie garantit

1. Chaque champ utilisé dans le rapport final a une origine documentée et traçable.
2. Aucune donnée n'est récupérée "au cas où" — seuls les champs listés ci-dessus sont extraits.
3. Le token d'accès Jira a une portée limitée en lecture seule (`read:jira-work`), jamais en écriture.
4. Cette cartographie sert de référence pour le mapping utilisé dans `ExcelMapper` /
   `JiraMapper` du code (voir Livrable 2 et 3).
