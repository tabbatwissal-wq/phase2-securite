"""
Dashboard Assistant IA - Phase 2
Interface chatbot Streamlit pour interroger les données de projet via RAG.

Lancement : streamlit run dashboard_assistant.py

Flux :
  1. L'utilisateur entre son token API dans la barre latérale
  2. Le backend construit un RequestContext (mêmes règles que main.py)
  3. Chaque question est traitée par assistant_service.repondre_question()
     qui filtre ChromaDB sur les projets autorisés avant d'appeler Ollama
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from security_context import construire_context_depuis_token, RequestContext
from assistant_service import repondre_question

st.set_page_config(
    page_title="Assistant Projets - Sofrecom",
    page_icon="🤖",
    layout="wide",
)

st.markdown("""
    <style>
    .main-title { color: #1A365D; font-size: 28px; font-weight: bold; }
    .badge      { background: #EBF8FF; color: #2B6CB0; padding: 3px 10px;
                  border-radius: 12px; font-size: 13px; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []
if "context" not in st.session_state:
    st.session_state.context: RequestContext | None = None

# ---------- Barre latérale : authentification ----------
st.sidebar.markdown("<h2 style='color:#1A365D;'>🔐 Connexion</h2>", unsafe_allow_html=True)
token_saisi = st.sidebar.text_input("Token API", type="password", key="token_input")

if st.sidebar.button("Se connecter", use_container_width=True):
    ctx = construire_context_depuis_token(token_saisi)
    if ctx:
        st.session_state.context = ctx
        st.session_state.messages = []       # réinitialise la conversation
        st.sidebar.success(f"Connecté : {ctx.authenticated_email}")
    else:
        st.session_state.context = None
        st.sidebar.error("Token invalide ou configuration absente.")

if st.session_state.context:
    ctx = st.session_state.context
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Utilisateur :** {ctx.authenticated_email}")
    projets = ctx.allowed_project_ids
    label_projets = ", ".join(projets) if projets else "Aucun"
    st.sidebar.markdown(f"**Projets autorisés :** `{label_projets}`")
    if st.sidebar.button("Se déconnecter", use_container_width=True):
        st.session_state.context = None
        st.session_state.messages = []
        st.rerun()

# ---------- En-tête ----------
st.markdown("<div class='main-title'>🤖 Assistant Projets Sofrecom</div>", unsafe_allow_html=True)
st.caption("Posez vos questions sur l'état des projets — réponses basées uniquement sur vos données.")

# ---------- Accès non authentifié ----------
if not st.session_state.context:
    st.info("Entrez votre token API dans la barre latérale pour démarrer la conversation.")
    st.stop()

# ---------- Historique de la conversation ----------
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ---------- Saisie de question ----------
if prompt := st.chat_input("Ex : Quel est l'avancement du projet PTI ?"):
    # Afficher la question de l'utilisateur
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Générer la réponse
    with st.chat_message("assistant"):
        with st.spinner("Recherche et génération en cours…"):
            try:
                reponse = repondre_question(prompt, st.session_state.context)
            except RuntimeError as exc:
                reponse = f"⚠️ {exc}"
            except Exception as exc:
                reponse = f"⚠️ Erreur inattendue : {exc}"
        st.write(reponse)

    st.session_state.messages.append({"role": "assistant", "content": reponse})

# ---------- Bouton de réinitialisation ----------
if st.session_state.messages:
    if st.button("🗑️ Effacer la conversation", use_container_width=False):
        st.session_state.messages = []
        st.rerun()
