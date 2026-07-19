\# Checklist Sécurité — Projet Reporting IA (Sofrecom)



Document de synthèse de la partie sécurité du projet, à destination de

l'encadrant / RSSI. Couvre l'authentification, l'autorisation, la

protection des secrets, et la robustesse de l'API.



\---



\## 1. Authentification



\*\*Fait :\*\*

\- Système X-API-Key (token statique par utilisateur, configuré côté serveur)

\- SSO Microsoft Entra ID (OIDC) : `/auth/login` → `/auth/callback`, via MSAL

\- Session SSO signée (JWT, expiration 8h) — évite de repasser par Microsoft à chaque requête

\- Les deux méthodes coexistent : l'API accepte X-API-Key \*\*ou\*\* une session SSO



\*\*Comment vérifier :\*\*

\- `pytest test\_security.py -v` → 6/6 tests passent

\- Tester `/auth/login` dans un navigateur → redirige vers Microsoft

\- Appeler `/reports/{project\_key}` sans aucun token → 401



\*\*Amélioration future :\*\*

\- SSO en environnement de production (actuellement testé sur un tenant Entra ID personnel)

\- Refresh token pour prolonger la session sans reconnexion complète



\---



\## 2. Autorisation (RBAC)



\*\*Fait :\*\*

\- `RequestContext` construit exclusivement côté serveur (jamais depuis une donnée envoyée par le client)

\- Vérification systématique du périmètre projet (`allowed\_project\_ids`) avant tout accès

\- Rôles `admin` / `reader` : seul un admin peut déclencher la génération complète de rapport



\*\*Comment vérifier :\*\*

\- Appeler `/reports/{project\_key}/generate` avec un token "reader" → 403

\- Appeler `/reports/{project\_key}` avec un projet hors périmètre → 403



\*\*Amélioration future :\*\*

\- Rôles supplémentaires si besoin (ex: "auditeur" en lecture seule sur les logs)

\- Gestion des rôles depuis une vraie base de données plutôt que `.env`



\---



\## 3. Protection des secrets



\*\*Fait :\*\*

\- `.gitignore` exclut `.env`, `.env.\*` (sauf `.env.example`)

\- Vérifié : aucun `.env` n'a jamais été commité dans l'historique Git

\- `SECRETS.md` : registre de tous les secrets utilisés, leur rôle, et comment les régénérer

\- Test automatique (`test\_gitignore.py`) qui garantit que `.env` reste toujours ignoré par Git



\*\*Comment vérifier :\*\*

\- `pytest test\_gitignore.py -v` → 2/2 tests passent

\- `git log --all --full-history -- .env` → aucun résultat



\*\*Amélioration future :\*\*

\- Remplacer `.env` par un vrai coffre-fort de secrets (Azure Key Vault, HashiCorp Vault) en production

\- Rotation automatisée des secrets plutôt que manuelle



\---



\## 4. Robustesse de l'API



\*\*Fait :\*\*

\- Rate limiting : 10 req/min sur `/reports/{project\_key}`, 3 req/min sur `/reports/{project\_key}/generate`

\- Gestion d'erreurs centralisée : toute exception non prévue renvoie un message générique (jamais de stack trace exposée au client), avec un `request\_id` pour le débogage interne

\- Retry automatique (3 tentatives, backoff exponentiel) sur les appels réseau à Jira, uniquement pour les erreurs de connexion/timeout (jamais sur les erreurs d'authentification)



\*\*Comment vérifier :\*\*

\- Appeler `/reports/{project\_key}/generate` plus de 3 fois en une minute → 429

\- Simuler une erreur interne → réponse JSON générique, pas de trace Python visible



\*\*Amélioration future :\*\*

\- Retry également sur les appels au modèle Ollama local

\- Rate limiting basé sur l'utilisateur authentifié plutôt que sur l'adresse IP



\---



\## 5. Observabilité



\*\*Fait :\*\*

\- Logs structurés (horodatage, niveau, module) via le module `logging` standard, remplaçant les `print()` de debug

\- Audit trail dans MongoDB : chaque tentative d'authentification et chaque décision d'autorisation est journalisée



\*\*Amélioration future :\*\*

\- Centralisation des logs (ex: ELK, Azure Monitor) plutôt que console locale

\- Alerting automatique sur les échecs répétés d'authentification



\---



\## 6. Intégration continue (CI/CD)



\*\*Fait :\*\*

\- GitHub Actions : tests de sécurité relancés automatiquement à chaque push

\- `pip-audit` intégré à la CI pour détecter les vulnérabilités connues dans les dépendances (non bloquant sauf vulnérabilité critique)

\- Docker Compose : l'ensemble du projet (API + MongoDB) démarre avec une seule commande, garantissant un environnement reproductible



\*\*Comment vérifier :\*\*

\- Onglet "Actions" du dépôt GitHub → dernier run vert

\- `docker-compose up` → API accessible sur `http://localhost:8000/docs`



\---



\## Résumé



| Point | Statut |

|---|---|

| Authentification (X-API-Key + SSO) | Fait |

| Autorisation (RBAC) |  Fait |

| Protection des secrets |  Fait |

| Rate limiting | Fait |

| Gestion d'erreurs |  Fait |

| Retry automatique |  Fait |

| Logs structurés |  Fait |

| pip-audit CI |  Fait |

| Docker Compose |  Fait |

