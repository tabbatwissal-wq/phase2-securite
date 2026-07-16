# Projet — Automatisation Reporting IA (Phase 1 + Phase 2)

## Architecture

```
┌─────────────────────────────── PHASE 1 ───────────────────────────────┐
│                                                                        │
│  Jira API                                                              │
│     │                                                                  │
│     └─▶ agent_jira.py       — Extraction + normalisation → ProjectTask │
│               │                                                        │
│               └─▶ pivot_models.py   — Objet Pivot (ProjectReportPivot) │
│                       │                                                │
│                       ├─▶ mongo_service.py    — Persistance MongoDB    │
│                       ├─▶ pdf_generator.py    — Export PDF (ReportLab) │
│                       └─▶ pptx_generator.py   — Export PPTX            │
│                                                                        │
│  main.py             — Backend FastAPI (endpoints sécurisés)           │
│  security_context.py — RequestContext & contrôle d'accès projet        │
│  audit_service.py    — Journalisation des actions                      │
│  report_constants.py — Palette couleurs & libellés partagés            │
└────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────── PHASE 2 ───────────────────────────────┐
│                                                                        │
│  MongoDB (rapports)                                                    │
│     │                                                                  │
│     └─▶ jira_ai_filter.py   — Anonymisation → ContenuSurAI            │
│               │                                                        │
│               └─▶ human_validation.py  — Porte humaine (CLI / UI)     │
│                       │                                                │
│                       └─▶ indexer_rapports.py  → ChromaDB             │
│                                                        │               │
│                                           assistant_service.py         │
│                                           (RAG + Ollama llama3.2:3b)  │
│                                                        │               │
│                                                    app.py (chatbot)   │
└────────────────────────────────────────────────────────────────────────┘

app.py             — Dashboard Streamlit (login, chatbot, validation UI)
```

## Contenu des fichiers clés

### Phase 1

| Fichier | Rôle |
|---|---|
| `pivot_models.py` | Modèles Pydantic — contrat de données central |
| `agent_jira.py` | Connexion Jira, calcul KPIs (Pandas), construction du pivot |
| `main.py` | API FastAPI — endpoints `/health`, `/reports/{key}`, `/reports/{key}/generate` |
| `mongo_service.py` | Connexion et stockage MongoDB |
| `pdf_generator.py` | Génération PDF avec ReportLab |
| `pptx_generator.py` | Génération PPTX avec python-pptx |
| `generer_rapport_complet.py` | Génération Word (.docx) du rapport technique Phase 1 |
| `security_context.py` | Authentification et vérification d'accès projet |
| `audit_service.py` | Log des événements (action, succès, détail) |
| `report_constants.py` | Palette couleurs et libellés statuts/priorités partagés |

### Phase 2 — Assistant IA (RAG)

| Fichier | Rôle |
|---|---|
| `jira_ai_filter.py` | Anonymisation des données → `ContenuSurAI` (aucun email, aucun ID source) |
| `human_validation.py` | Porte de validation humaine — CLI (Phase 2) / Streamlit (Phase 3) |
| `indexer_rapports.py` | Pipeline complet : MongoDB → anonymisation → validation → ChromaDB |
| `assistant_service.py` | Recherche sémantique (ChromaDB) + génération réponse (Ollama) |
| `app.py` | Dashboard Streamlit — login sécurisé, chatbot IA, validation JSON |

### Configuration

| Fichier | Rôle |
|---|---|
| `.env.example` | Modèle de configuration — à copier en `.env` |
| `requirements.txt` | Dépendances Python |

## Installation

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Remplir .env avec vos identifiants
```

## Lancement

### Dashboard Streamlit
```powershell
streamlit run app.py
```

### API FastAPI
```powershell
uvicorn main:app --reload
# Documentation interactive : http://127.0.0.1:8000/docs
```

### Pipeline en ligne de commande
```powershell
python agent_jira.py
```

### Rapport Word (Phase 1)
```powershell
python generer_rapport_complet.py
```

### Indexation ChromaDB (Phase 2)
```powershell
# Nécessite Ollama installé et MongoDB actif
python indexer_rapports.py
```

### Tests
```powershell
pytest tests/ -v
```

## Variables d'environnement (.env)

### Phase 1

| Variable | Description |
|---|---|
| `JIRA_URL` | URL de votre instance Jira Cloud |
| `JIRA_EMAIL` | Email du compte Jira |
| `JIRA_API_TOKEN` | Token API Jira |
| `JIRA_PROJECT_KEY` | Clé du projet (ex. `KAN`) |
| `API_ACCESS_TOKEN` | Token d'accès pour le dashboard Streamlit |
| `API_USER_EMAIL` | Email de l'utilisateur associé au token |
| `API_ALLOWED_PROJECTS` | Projets autorisés (ex. `KAN`) |
| `MONGO_URI` | URI MongoDB (défaut : `mongodb://localhost:27017`) |

### Phase 2

| Variable | Description |
|---|---|
| `OLLAMA_MODEL` | Modèle Ollama (défaut : `llama3.2:3b`) |
| `CHROMA_PATH` | Dossier de persistance ChromaDB (défaut : `./chroma_db`) |
| `RAG_N_RESULTS` | Nombre de documents RAG par requête (défaut : `4`) |

## Prérequis système

- Python 3.11+
- MongoDB Community Server installé localement et lancé (service Windows actif)
- [Ollama](https://ollama.com) installé avec `ollama pull llama3.2:3b`
- Un compte Jira Cloud avec accès au projet de test
