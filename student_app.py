import streamlit as st
from datetime import datetime

from shared.db import (
    init_db, create_user, list_events, event_status,
    find_valid_code_by_code, validate_attendance,
    user_attendance, get_absences_count, get_presence_count,
    get_user_by_id, update_user, user_has_attended,
    verify_pwd,
)
from shared.auth import login, logout

# === CONFIGURATION ===
SAYNA_URL = "https://www.sayna.co"           # ← remplace par ton lien Sayna

st.set_page_config(page_title="Sayna - Élève", page_icon="🎓", layout="wide")
init_db()


# ============================================================
# PAGE DE CONNEXION / INSCRIPTION
# ============================================================
def page_login():
    st.title("🎓 Sayna - Espace Élève")
    tab1, tab2 = st.tabs(["Se connecter", "Créer un compte"])

    with tab1:
        with st.form("login_form"):
            email = st.text_input("Adresse email")
            pwd = st.text_input("Mot de passe", type="password")
            ok = st.form_submit_button("Se connecter")
        if ok:
            user, err = login(email.strip().lower(), pwd)
            if err:
                st.error(err)
            else:
                st.session_state["user_id"] = user["id"]
                st.rerun()

    with tab2:
        with st.form("register_form"):
            email = st.text_input("Entrer l'adresse utilisée pour l'app Sayna", key="r_email")
            pwd = st.text_input("Mot de passe", type="password", key="r_pwd")
            pwd2 = st.text_input("Confirmer le mot de passe", type="password", key="r_pwd2")
            accept = st.checkbox("J'accepte les politiques de confidentialité et les règles.")
            ok = st.form_submit_button("Créer mon compte")
        if ok:
            if not email or not pwd:
                st.error("Veuillez remplir tous les champs.")
            elif pwd != pwd2:
                st.error("Les mots de passe ne correspondent pas.")
            elif not accept:
                st.error("Vous devez accepter les politiques de confidentialité.")
            else:
                success, err = create_user(email.strip().lower(), pwd)
                if success:
                    st.success("✅ Compte créé ! Vous pouvez maintenant vous connecter.")
                else:
                    st.error(f"Erreur : {err}")


# ============================================================
# PAGE ÉVÉNEMENTS
# ============================================================
def page_events():
    st.header("📅 Évènements")
    events = list_events()

    tab1, tab2, tab3 = st.tabs(["✅ Évènements effectués", "❌ Ratés / Refusés", "🕐 En cours / À venir"])

    uid = st.session_state["user_id"]
    my_att = user_attendance(uid)
    attended_ids = {a["event_id"] for a in my_att}

    with tab1:
        if not my_att:
            st.info("Aucun évènement validé pour l'instant.")
        else:
            for a in my_att:
                st.success(f"✅ **{a['event_name']}** — validé le {datetime.fromisoformat(a['validated_at']).strftime('%d/%m/%Y %H:%M')}")

    with tab2:
        missed = []
        for e in events:
            if event_status(e) == "passé" and e["id"] not in attended_ids:
                missed.append(e)
        if not missed:
            st.info("Aucun évènement raté. Bravo !")
        else:
            for e in missed:
                st.error(f"❌ **{e['name']}** — {datetime.fromisoformat(e['start_at']).strftime('%d/%m/%Y %H:%M')}")

    with tab3:
        upcoming = [e for e in events if event_status(e) in ("en cours", "à venir")]
        if not upcoming:
            st.info("Aucun évènement en cours ou à venir.")
        else:
            for e in upcoming:
                status = event_status(e)
                badge = "🟢 En cours" if status == "en cours" else "🔵 À venir"
                with st.expander(f"{badge} — **{e['name']}**"):
                    st.write(f"Début : {datetime.fromisoformat(e['start_at']).strftime('%d/%m/%Y %H:%M')}")
                    st.write(f"Fin   : {datetime.fromisoformat(e['end_at']).strftime('%d/%m/%Y %H:%M')}")
                    if status == "en cours" and not user_has_attended(uid, e["id"]):
                        st.markdown("**Valider votre présence :**")
                        code = st.text_input(f"Code de présence ({e['name']})", key=f"code_{e['id']}")
                        if st.button("Valider", key=f"btn_{e['id']}"):
                            if not code:
                                st.warning("Entrez un code.")
                            else:
                                found = find_valid_code_by_code(code.strip())
                                if not found:
                                    st.error("Code invalide ou expiré.")
                                elif found["event_id"] != e["id"]:
                                    st.error("Ce code n'est pas lié à cet évènement.")
                                else:
                                    validate_attendance(uid, e["id"], found["id"])
                                    st.success("✅ Présence validée !")
                                    st.rerun()
                    elif status == "en cours":
                        st.success("Vous avez déjà validé votre présence pour cet évènement.")
                    else:
                        st.info("Le code sera disponible pendant l'évènement.")


# ============================================================
# PAGE MON COMPTE
# ============================================================
def page_account():
    st.header("👤 Informations du compte")
    uid = st.session_state["user_id"]
    u = get_user_by_id(uid)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Présences", get_presence_count(uid))
    with col2:
        st.metric("Absences", get_absences_count(uid))

    st.divider()
    st.subheader("Modifier mon mot de passe")
    with st.form("pwd_form"):
        old = st.text_input("Mot de passe actuel", type="password")
        new = st.text_input("Nouveau mot de passe", type="password")
        new2 = st.text_input("Confirmer", type="password")
        ok = st.form_submit_button("Enregistrer")
    if ok:
        if not verify_pwd(old, u["password"]):
            st.error("Mot de passe actuel incorrect.")
        elif not new or new != new2:
            st.error("Les nouveaux mots de passe ne correspondent pas.")
        else:
            update_user(uid, password=new)
            st.success("✅ Mot de passe modifié.")

    st.divider()
    st.caption(f"Email : **{u['email']}**")
    st.caption(f"Statut : **{u['status']}**")


# ============================================================
# PAGE SAYNA
# ============================================================
def page_sayna():
    st.header("🌐 Sayna")
    st.write("Cliquez ci-dessous pour accéder à la plateforme Sayna.")
    st.link_button("🔗 Rediriger vers Sayna", SAYNA_URL, use_container_width=True)


# ============================================================
# APPLICATION PRINCIPALE
# ============================================================
def main_app():
    uid = st.session_state["user_id"]
    u = get_user_by_id(uid)
    if not u:
        st.session_state.clear()
        st.rerun()

    with st.sidebar:
        st.markdown("### 🎓 Bonjour")
        st.caption(u["email"])
        st.divider()
        choix = st.radio("Navigation", [
            "📅 Évènements",
            "👤 Mon compte",
            "🌐 Sayna",
        ])
        st.divider()
        if st.button("Se déconnecter"):
            logout()
            st.rerun()

    if choix == "📅 Évènements":
        page_events()
    elif choix == "👤 Mon compte":
        page_account()
    elif choix == "🌐 Sayna":
        page_sayna()


# ============================================================
# POINT D'ENTRÉE
# ============================================================
if "user_id" not in st.session_state:
    page_login()
else:
    main_app()