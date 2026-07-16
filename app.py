import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

from main import executer_pipeline_complet
from report_constants import STATUS_LABEL, PRIORITY_LABEL
from security_context import construire_context_depuis_token

PIVOT_PATH = "ProjectReportPivot.json"

st.set_page_config(
    page_title="Sofrecom Reporting IA",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
    <style>
    .main-title  { color: #1A365D; font-size: 32px; font-weight: bold; margin-bottom: 4px; }
    .section-h1  { color: #2B6CB0; font-size: 22px; font-weight: bold; margin-top: 20px; }
    .login-box   { max-width: 420px; margin: 80px auto; padding: 40px;
                   background: #F7FAFC; border-radius: 12px;
                   border: 1px solid #CBD5E1; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
    div.chat-float-wrapper { position: fixed; bottom: 32px; right: 32px; z-index: 9999; }
    div.chat-float-wrapper button {
        background: #2B6CB0 !important; color: white !important;
        border-radius: 50px !important; padding: 12px 22px !important;
        font-size: 18px !important; font-weight: bold !important;
        border: none !important; box-shadow: 0 4px 16px rgba(0,0,0,0.28) !important;
    }
    </style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────
for key, default in {
    "app_context":           None,   # RequestContext unique pour toute la session
    "chatbot_ouvert":        False,
    "chat_messages":         [],
    "pivot_a_valider":       None,
    "phase3_derive":         None,   # PrevisionDerive | None
    "phase3_recommandation": None,   # Recommandation | None (en attente ou approuvée)
    "phase3_reco_dialog":    False,  # dialog de validation recommandation ouvert
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ──────────────────────────────────────────────────────────
# ÉCRAN DE LOGIN — bloque tout le reste si non connecté
# ──────────────────────────────────────────────────────────
if st.session_state.app_context is None:
    st.markdown("""
        <div style='text-align:center; margin-top:60px;'>
            <span style='font-size:52px;'>📊</span>
            <h1 style='color:#1A365D; margin-bottom:4px;'>Sofrecom Reporting IA</h1>
            <p style='color:#475569; font-size:16px;'>
                Entrez votre token API pour accéder au dashboard.
            </p>
        </div>
    """, unsafe_allow_html=True)

    col_left, col_center, col_right = st.columns([1, 1.2, 1])
    with col_center:
        st.write("")
        token_saisi = st.text_input(
            "Token API",
            type="password",
            placeholder="Collez votre token ici…",
            label_visibility="collapsed",
        )
        if st.button("Se connecter", use_container_width=True, type="primary"):
            ctx = construire_context_depuis_token(token_saisi.strip())
            if ctx:
                st.session_state.app_context = ctx
                st.rerun()
            else:
                st.error("Token invalide. Vérifiez votre configuration.")

    st.stop()   # ← rien d'autre ne s'affiche tant que non connecté


# ──────────────────────────────────────────────────────────
# À partir d'ici : utilisateur authentifié
# ──────────────────────────────────────────────────────────
ctx = st.session_state.app_context


# ──────────────────────────────────────────────────────────
# Dialog : Chatbot IA (utilise ctx de la session, pas de 2e login)
# ──────────────────────────────────────────────────────────
@st.dialog("💬 Assistant IA — Sofrecom", width="large")
def dialog_chatbot():
    from assistant_service import repondre_question

    projets = ", ".join(ctx.allowed_project_ids) or "aucun"
    st.caption(f"Connecté : **{ctx.authenticated_email}** | Projets : `{projets}`")

    historique = st.container(height=340)
    with historique:
        if not st.session_state.chat_messages:
            st.write("*Posez une question sur vos projets…*")
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        question = st.text_input(
            "question", label_visibility="collapsed",
            placeholder="Ex : Quel est l'avancement du projet KAN ?",
            key="chat_question",
        )
    with col_btn:
        envoyer = st.button("Envoyer", use_container_width=True, type="primary")

    if envoyer and question.strip():
        st.session_state.chat_messages.append({"role": "user", "content": question})
        with st.spinner("Génération de la réponse…"):
            try:
                reponse = repondre_question(question, ctx)
            except RuntimeError as e:
                reponse = f"Erreur : {e}"
        st.session_state.chat_messages.append({"role": "assistant", "content": reponse})
        st.rerun()

    col_clear, col_close = st.columns(2)
    with col_clear:
        if st.button("Effacer la conversation", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()
    with col_close:
        if st.button("Fermer", use_container_width=True):
            st.session_state.chatbot_ouvert = False
            st.rerun()


# ──────────────────────────────────────────────────────────
# Dialog : Validation humaine du rapport (JSON éditable)
# ──────────────────────────────────────────────────────────
@st.dialog("Validation du rapport avant indexation ChromaDB", width="large")
def dialog_validation():
    from jira_ai_filter import preparer_contenu_pour_ia
    from indexer_rapports import _indexer_contenus

    pivot = st.session_state.pivot_a_valider
    if not pivot:
        st.error("Aucun pivot à valider.")
        return

    project = pivot.get("project", {})
    kpis    = {k["code"]: k for k in pivot.get("kpis", [])}
    tasks   = pivot.get("tasks", [])

    st.subheader(f"{project.get('nom_projet', '?')}  —  `{project.get('project_id', '?')}`")

    def _kval(code: str) -> str:
        k = kpis.get(code)
        return f"{k['valeur']:g}{k.get('unite') or ''}" if k else "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total tickets", _kval("total_tickets"))
    c2.metric("Avancement",    _kval("avancement_pct"))
    c3.metric("En retard",     _kval("tickets_en_retard"))
    c4.metric("Critiques",     _kval("tickets_critiques"))

    st.write(f"**{len(tasks)} tâche(s) :**")
    for t in tasks[:8]:
        statut_fr = STATUS_LABEL.get(t.get("statut", ""), t.get("statut", ""))
        retard    = " ⚠️" if t.get("en_retard") else ""
        st.write(f"- `{t['task_id']}` {t['titre']} — *{statut_fr}*{retard}")
    if len(tasks) > 8:
        st.caption(f"… et {len(tasks) - 8} autre(s) tâche(s)")

    st.divider()

    json_brut = json.dumps(pivot, ensure_ascii=False, indent=2, default=str)
    with st.expander("📝 Voir / modifier le JSON du pivot (avancé)", expanded=False):
        json_edite = st.text_area(
            "JSON", value=json_brut, height=320,
            label_visibility="collapsed", key="json_validation",
        )
    st.caption("Vous pouvez modifier le JSON ci-dessus avant d'approuver.")

    col_ok, col_ko = st.columns(2)
    with col_ok:
        if st.button("Approuver et indexer dans ChromaDB", type="primary", use_container_width=True):
            try:
                pivot_final = json.loads(st.session_state.get("json_validation", json_brut))
            except json.JSONDecodeError as e:
                st.error(f"JSON invalide : {e}")
                return
            with st.spinner("Indexation…"):
                contenu = preparer_contenu_pour_ia(pivot_final)
                _indexer_contenus([contenu], [f"validated_{project.get('project_id', 'INCONNU')}"])
            st.success("Rapport approuvé et indexé dans ChromaDB !")
            st.session_state.pivot_a_valider = None
            st.rerun()
    with col_ko:
        if st.button("Rejeter (ne pas indexer)", use_container_width=True):
            st.session_state.pivot_a_valider = None
            st.warning("Rapport rejeté — aucune donnée écrite dans ChromaDB.")
            st.rerun()


# ──────────────────────────────────────────────────────────
# Dialog : Validation des recommandations IA (Phase 3)
# ──────────────────────────────────────────────────────────
_RISQUE_ICONE = {"faible": "🟢", "modere": "🟡", "eleve": "🔴", "donnees_insuffisantes": "⚪"}
_RISQUE_TEXTE = {"faible": "FAIBLE", "modere": "MODÉRÉ", "eleve": "ÉLEVÉ",
                 "donnees_insuffisantes": "NON CALCULABLE"}


@st.dialog("Validation des recommandations IA — Phase 3", width="large")
def dialog_recommandation_validation():
    reco = st.session_state.phase3_recommandation
    if not reco:
        st.error("Aucune recommandation à valider.")
        return

    icone       = _RISQUE_ICONE.get(reco.risque_derive, "⚪")
    texte_risque = _RISQUE_TEXTE.get(reco.risque_derive, reco.risque_derive.upper())

    st.subheader(f"{reco.nom_projet}  —  `{reco.project_id}`")

    if reco.risque_derive == "eleve":
        st.error(f"{icone}  Risque de dérive : **{texte_risque}**")
    elif reco.risque_derive == "modere":
        st.warning(f"{icone}  Risque de dérive : **{texte_risque}**")
    else:
        st.success(f"{icone}  Risque de dérive : **{texte_risque}**")

    st.caption(reco.justification_derive)
    st.divider()

    st.markdown("**Recommandations générées par le modèle IA :**")
    st.markdown(reco.texte)
    st.caption(
        f"*Générées le {reco.genere_le[:10]} · en attente de validation humaine*"
    )
    st.divider()

    col_ok, col_ko = st.columns(2)
    with col_ok:
        if st.button("Approuver et afficher", type="primary", use_container_width=True):
            reco.approuvee = True
            st.session_state.phase3_reco_dialog = False
            st.rerun()
    with col_ko:
        if st.button("Rejeter (ne pas afficher)", use_container_width=True):
            st.session_state.phase3_recommandation = None
            st.session_state.phase3_reco_dialog    = False
            st.rerun()


# ──────────────────────────────────────────────────────────
# Dialogs (un seul à la fois)
# ──────────────────────────────────────────────────────────
if st.session_state.pivot_a_valider:
    dialog_validation()
elif st.session_state.phase3_reco_dialog:
    dialog_recommandation_validation()
elif st.session_state.chatbot_ouvert:
    dialog_chatbot()


# ──────────────────────────────────────────────────────────
# BARRE LATÉRALE
# ──────────────────────────────────────────────────────────
st.sidebar.markdown("<h2 style='color: #1A365D;'>Configuration</h2>", unsafe_allow_html=True)

# Infos utilisateur connecté
st.sidebar.success(f"**{ctx.authenticated_email}**")
projets_label = ", ".join(ctx.allowed_project_ids) if ctx.allowed_project_ids else "Aucun"
st.sidebar.caption(f"Projets autorisés : `{projets_label}`")
if st.sidebar.button("Se déconnecter", use_container_width=True):
    st.session_state.app_context    = None
    st.session_state.chat_messages  = []
    st.session_state.chatbot_ouvert = False
    st.rerun()

st.sidebar.divider()

source = st.sidebar.radio("Source de données", ["Jira", "Microsoft Teams"], index=0)
if source == "Microsoft Teams":
    st.sidebar.info("Teams : intégration Phase 3 — en cours par l'équipe IA.")

st.sidebar.divider()

project_key = st.sidebar.text_input(
    "Clé du projet Jira",
    value=os.getenv("JIRA_PROJECT_KEY", "KAN"),
    disabled=(source == "Microsoft Teams"),
)
status_filtre = st.sidebar.selectbox(
    "Filtrer par Statut",
    ["Tous", "À faire", "En cours", "Terminé", "Bloqué"],
)


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────
def charger_pivot() -> dict | None:
    p = Path(PIVOT_PATH)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def afficher_kpis(pivot: dict):
    kpis = {k["code"]: k for k in pivot.get("kpis", [])}
    def _fmt(code: str) -> str:
        k = kpis.get(code)
        return f"{k['valeur']:g}{k.get('unite') or ''}" if k else "—"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total tickets",     _fmt("total_tickets"))
    c2.metric("Avancement global", _fmt("avancement_pct"))
    c3.metric("Tickets en retard", _fmt("tickets_en_retard"))
    c4.metric("Tickets critiques", _fmt("tickets_critiques"))


def afficher_tableau(pivot: dict, filtre: str):
    tasks = pivot.get("tasks", [])
    if not tasks:
        st.info("Aucune tâche dans le pivot courant.")
        return
    rows = [
        {
            "Ticket":    t["task_id"],
            "Titre":     t["titre"],
            "Statut":    STATUS_LABEL.get(t["statut"], t["statut"]),
            "Priorité":  PRIORITY_LABEL.get(t["priorite"], t["priorite"]),
            "En retard": "⚠️" if t.get("en_retard") else "",
        }
        for t in tasks
    ]
    df = pd.DataFrame(rows)
    if filtre != "Tous":
        df = df[df["Statut"] == filtre]
    st.dataframe(df, use_container_width=True)


def afficher_graphique(pivot: dict):
    tasks = pivot.get("tasks", [])
    if not tasks:
        return
    counts: dict[str, int] = {}
    for t in tasks:
        counts[STATUS_LABEL.get(t["statut"], t["statut"])] = \
            counts.get(STATUS_LABEL.get(t["statut"], t["statut"]), 0) + 1
    st.bar_chart(pd.DataFrame({"Nombre": counts}).rename_axis("Statut"))


def lancer_pipeline(project_key: str) -> dict:
    result = executer_pipeline_complet(project_key, context=ctx)
    pivot_dict = charger_pivot()
    if pivot_dict:
        st.session_state.pivot_a_valider = pivot_dict
    return result


# ──────────────────────────────────────────────────────────
# EN-TÊTE
# ──────────────────────────────────────────────────────────
col_titre, col_chat_btn = st.columns([5, 1])
with col_titre:
    st.markdown(
        "<div class='main-title'>📊 Suivi de Projet — Sofrecom Reporting IA</div>",
        unsafe_allow_html=True,
    )
    badge = "🟢 Jira" if source == "Jira" else "🔵 Teams (à venir)"
    st.caption(f"Source active : {badge}")
with col_chat_btn:
    st.write("")
    st.write("")
    if st.button("💬 Assistant IA", use_container_width=True, type="primary"):
        st.session_state.chatbot_ouvert = True
        st.rerun()

# ──────────────────────────────────────────────────────────
# KPIs
# ──────────────────────────────────────────────────────────
pivot = charger_pivot()

st.markdown("<div class='section-h1'>Indicateurs de Performance (KPIs)</div>", unsafe_allow_html=True)
if pivot:
    afficher_kpis(pivot)
    genere_le = pivot.get("reporting_period", {}).get("genere_le", "")[:10]
    st.caption(f"Dernière synchronisation : {genere_le}")
else:
    st.info("Aucun pivot disponible. Lancez la synchronisation ci-dessous.")
    c1, c2, c3, c4 = st.columns(4)
    for col, label in zip(
        [c1, c2, c3, c4],
        ["Total tickets", "Avancement global", "Tickets en retard", "Tickets critiques"]
    ):
        col.metric(label, "—")

st.markdown("---")

# ──────────────────────────────────────────────────────────
# DONNÉES & GRAPHIQUES
# ──────────────────────────────────────────────────────────
left_col, right_col = st.columns([2, 1])

with left_col:
    st.markdown("<div class='section-h1'>📥 Flux de Données</div>", unsafe_allow_html=True)
    if source == "Microsoft Teams":
        st.info("Connexion Teams : développée par l'équipe en Phase 3.")
    elif pivot:
        afficher_tableau(pivot, status_filtre)
    else:
        st.warning("Données non chargées — lancez la synchronisation.")

with right_col:
    st.markdown("<div class='section-h1'>📈 Répartition des Tâches</div>", unsafe_allow_html=True)
    if pivot and source == "Jira":
        afficher_graphique(pivot)

st.markdown("---")

# ──────────────────────────────────────────────────────────
# CONSOLE DE CONTRÔLE
# ──────────────────────────────────────────────────────────
st.markdown("<div class='section-h1'>⚙️ Actions</div>", unsafe_allow_html=True)

if source == "Microsoft Teams":
    st.info("Actions désactivées pour la source Teams (Phase 3).")
else:
    c_btn1, c_btn2, c_btn3 = st.columns(3)

    with c_btn1:
        if st.button("🔄 Synchroniser Jira → MongoDB + rapport", use_container_width=True):
            try:
                with st.spinner("Pipeline en cours…"):
                    result = lancer_pipeline(project_key)
                st.success(f"Pipeline OK — fichiers : {', '.join(result['fichiers_generes'])}")
                st.rerun()
            except Exception as exc:
                st.error(f"Erreur : {exc}")

    with c_btn2:
        if st.button("📄 Générer PPTX & PDF uniquement", use_container_width=True):
            try:
                with st.spinner("Génération…"):
                    result = lancer_pipeline(project_key)
                st.info(f"Rapports : {', '.join(result['fichiers_generes'])}")
                st.rerun()
            except Exception as exc:
                st.error(f"Erreur : {exc}")

    with c_btn3:
        if st.button("🚀 Tester URL Ngrok", use_container_width=True):
            ngrok_url = os.getenv("NGROK_URL", "")
            if ngrok_url:
                st.success(f"Tunnel actif : {ngrok_url} → local:8000")
            else:
                st.warning("NGROK_URL non défini dans .env")

# ──────────────────────────────────────────────────────────
# PHASE 3 — Prévisions & Recommandations
# ──────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div class='section-h1'>🔮 Prévisions & Recommandations (Phase 3)</div>",
    unsafe_allow_html=True,
)

if source == "Microsoft Teams":
    st.info("Prévisions désactivées pour la source Teams.")
elif not pivot:
    st.info("Lancez d'abord une synchronisation Jira pour activer les prévisions.")
else:
    project_id_actif = pivot.get("project", {}).get("project_id", project_key)
    nom_projet_actif = pivot.get("project", {}).get("nom_projet", project_id_actif)
    kpis_actifs      = pivot.get("kpis", [])

    col_derive, col_reco = st.columns(2)

    # ── Colonne gauche : Dérive planning ──
    with col_derive:
        st.markdown("##### Dérive planning")

        if st.button("🔍 Analyser l'historique MongoDB", use_container_width=True):
            from derive_planning import calculer_derive
            try:
                with st.spinner("Analyse de l'historique MongoDB…"):
                    derive_calc = calculer_derive(project_id_actif, ctx)
                st.session_state.phase3_derive         = derive_calc
                st.session_state.phase3_recommandation = None   # reset si on recalcule
                st.rerun()
            except PermissionError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Erreur lors du calcul : {exc}")

        derive = st.session_state.phase3_derive

        if derive:
            icone        = _RISQUE_ICONE.get(derive.risque, "⚪")
            texte_risque = _RISQUE_TEXTE.get(derive.risque, derive.risque.upper())

            if derive.risque == "eleve":
                st.error(f"{icone}  Risque : **{texte_risque}**")
            elif derive.risque == "modere":
                st.warning(f"{icone}  Risque : **{texte_risque}**")
            elif derive.risque == "donnees_insuffisantes":
                st.info(f"{icone}  {texte_risque}")
            else:
                st.success(f"{icone}  Risque : **{texte_risque}**")

            if derive.tendance_pct_par_jour is not None:
                signe = "+" if derive.tendance_pct_par_jour >= 0 else ""
                st.metric(
                    "Tendance d'avancement",
                    f"{signe}{derive.tendance_pct_par_jour:.3f} %/jour",
                )

            st.caption(derive.justification)

            # Graphique de l'historique d'avancement
            if len(derive.points) >= 2:
                df_hist = pd.DataFrame([
                    {"Date": p.date_rapport, "Avancement (%)": p.avancement_pct}
                    for p in derive.points
                ]).set_index("Date")
                st.line_chart(df_hist, height=160, use_container_width=True)

    # ── Colonne droite : Recommandations ──
    with col_reco:
        st.markdown("##### Recommandations IA")

        derive = st.session_state.phase3_derive
        reco   = st.session_state.phase3_recommandation

        if derive is None:
            st.info("Analysez d'abord l'historique (colonne gauche).")

        elif not derive.suffisant:
            st.info(
                f"Historique insuffisant : {derive.n_points} rapport(s) disponible(s), "
                "minimum requis : 2.\n\n"
                "Générez un rapport supplémentaire via la synchronisation Jira."
            )

        else:
            if st.button(
                "💡 Générer les recommandations IA",
                use_container_width=True,
                type="primary",
            ):
                from recommandations_service import generer_recommandation
                try:
                    with st.spinner("Génération via Ollama (quelques secondes)…"):
                        reco_gen = generer_recommandation(
                            project_id_actif, nom_projet_actif,
                            kpis_actifs, derive, ctx,
                        )
                    st.session_state.phase3_recommandation = reco_gen
                    st.session_state.phase3_reco_dialog    = True
                    st.rerun()
                except RuntimeError as exc:
                    st.error(f"Ollama indisponible : {exc}")
                except PermissionError as exc:
                    st.error(str(exc))

            # État de la recommandation
            if reco and reco.approuvee:
                st.success("Recommandations validées par l'opérateur :")
                st.markdown(reco.texte)
                st.caption(f"Générées le {reco.genere_le[:10]}")
                if st.button("Régénérer", use_container_width=True):
                    st.session_state.phase3_recommandation = None
                    st.rerun()

            elif reco and not reco.approuvee:
                st.info("Recommandations générées — en attente de validation.")
                if st.button("Ouvrir la validation", use_container_width=True):
                    st.session_state.phase3_reco_dialog = True
                    st.rerun()


# ──────────────────────────────────────────────────────────
# Bouton flottant chatbot (CSS)
# ──────────────────────────────────────────────────────────
st.markdown('<div class="chat-float-wrapper">', unsafe_allow_html=True)
if st.button("💬", key="chat_float", help="Ouvrir l'assistant IA"):
    st.session_state.chatbot_ouvert = True
    st.rerun()
st.markdown("</div>", unsafe_allow_html=True)
