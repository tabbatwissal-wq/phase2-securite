\# Registre des secrets — Projet Reporting IA



Ce document liste les secrets utilisés par le projet, leur rôle, et

comment les régénérer. Aucune valeur sensible n'est écrite ici — 

uniquement des références et des instructions.



\## JIRA\_API\_TOKEN

\- \*\*Rôle\*\* : authentifie les appels à l'API Jira pour récupérer les tickets.

\- \*\*Où le régénérer\*\* : https://id.atlassian.com/manage-profile/security/api-tokens

\- \*\*Rotation recommandée\*\* : tous les 6 mois, ou immédiatement en cas de doute.



\## API\_ACCESS\_TOKEN / API\_USERS\_JSON

\- \*\*Rôle\*\* : authentifie les appels à notre propre API (mode X-API-Key).

\- \*\*Où le régénérer\*\* : généré manuellement (chaîne aléatoire longue).

\- \*\*Rotation recommandée\*\* : tous les 3 mois, ou à chaque changement d'équipe.



\## TEAMS\_WEBHOOK\_URL

\- \*\*Rôle\*\* : envoie des notifications dans un canal Microsoft Teams.

\- \*\*Où le régénérer\*\* : dans Teams → canal cible → Connecteurs → Incoming Webhook.

\- \*\*Rotation recommandée\*\* : si le canal ou l'équipe change.



\## AZURE\_CLIENT\_SECRET

\- \*\*Rôle\*\* : authentifie l'application auprès de Microsoft Entra ID pour le SSO.

\- \*\*Où le régénérer\*\* : portal Azure → Microsoft Entra ID → App registrations

&#x20; → Reporting IA Test → Certificates \& secrets.

\- \*\*Rotation recommandée\*\* : avant expiration (6 mois par défaut), ou

&#x20; immédiatement si exposé (ex: partagé par erreur dans un chat, un email, etc.).



\## SESSION\_SECRET

\- \*\*Rôle\*\* : signe les tokens de session SSO générés côté serveur.

\- \*\*Où le régénérer\*\* : générer une nouvelle chaîne aléatoire longue soi-même.

\- \*\*Rotation recommandée\*\* : en cas de doute de compromission ; invalide

&#x20; automatiquement toutes les sessions actives lors du changement.



\## Amélioration future

Pour une utilisation en production réelle, remplacer le fichier `.env`

local par un vrai coffre-fort de secrets (ex: Azure Key Vault, HashiCorp

Vault), avec accès restreint et rotation automatisée.

