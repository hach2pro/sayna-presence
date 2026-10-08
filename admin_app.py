import streamlit as st
from datetime import datetime, timedelta
import json

from shared.db import (
    init_db, create_user, update_user, list_users,
    list_events, create_event, delete_event, event_status,
    create_code, list_codes_for_event,
    get_absences_count, get_presence_count,
    get_user_by_id, delete_user, verify_pwd,
    reset_absences,
)
from shared.auth import login, logout

# === CONFIGURATION ===
SAYNA_URL = "https://app.sayna.io/"           # ← remplace par ton lien
SAYNA_ADMIN_URL = "https://admin.sayna.co"   # ← remplace par ton lien admin

ALL_PERMISSIONS = [
    "modifier_utilisateur",
    "ajouter_utilisateur",
    "acces_purge",
    "creer_evenement",
    "generer_code",
    "nommer_admin",
]

st.set_page_config(page_title="Sayna - Admin", page_icon="🛠️", layout="wide")
init_db()


def is_main_admin(user):
    return bool(user.get("is_main_admin"))


def has_perm(user, perm):
    if is_main_admin(user):
        return True
    perms = json.loads(user.get("permissions") or "[]")
    return perm in perms or "all" in perms


# ============================================================
# LOGIN ADMIN
# ============================================================
def page_login_admin():
    st.title("🛠️ Sayna - Espace Admin")
    with st.form("admin_login"):
        email = st.text_input("Adresse email")
        pwd = st.text_input("Mot de passe", type="password")
        ok = st.form_submit_button("Se connecter")
    if ok:
        user, err = login(email.strip().lower(), pwd)
        if err:
            st.error(err)
        elif not user["is_admin"]:
            st.error("Ce compte n'a pas les droits admin.")
        else:
            st.session_state["admin_id"] = user["id"]
            st.rerun()
    st.caption("0011001")


# ============================================================
# ONGLET MEMBRES
# ============================================================
def tab_membres(admin):
    st.header("👥 Membres")
    users = list_users()

    search = st.text_input("🔍 Rechercher un élève (email)")
    if search:
        users = [u for u in users if search.lower() in u["email"].lower()]

    if not users:
        st.info("Aucun utilisateur.")
        return

    for u in users:
        role = "👑 Admin principal" if u["is_main_admin"] else ("🛠️ Admin" if u["is_admin"] else "🎓 Élève")
        with st.expander(f"{role} — {u['email']} (statut: {u['status']})"):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Présences", get_presence_count(u["id"]))
            with col2:
                st.metric("Absences", get_absences_count(u["id"]))

            perms = json.loads(u["permissions"] or "[]")
            if perms:
                st.caption("Permissions : " + ", ".join(perms))

            if has_perm(admin, "modifier_utilisateur") and not u["is_main_admin"]:
                st.markdown("**Modifier ce membre**")
                new_email = st.text_input("Email", value=u["email"], key=f"e_{u['id']}")
                new_pwd = st.text_input("Nouveau mot de passe (laisser vide pour ne pas changer)",
                                        type="password", key=f"p_{u['id']}")
                new_status = st.selectbox("Statut", ["normal", "suspendu", "bloque"],
                                          index=["normal", "suspendu", "bloque"].index(u["status"]),
                                          key=f"s_{u['id']}")
                sus_until = None
                if new_status == "suspendu":
                    days = st.number_input("Suspendu pendant (jours)", min_value=1, value=7, key=f"sd_{u['id']}")
                    sus_until = (datetime.now() + timedelta(days=int(days))).isoformat()

                if st.button("💾 Enregistrer", key=f"save_{u['id']}"):
                    data = {"email": new_email.strip().lower(), "status": new_status,
                            "suspended_until": sus_until if new_status == "suspendu" else None}
                    if new_pwd:
                        data["password"] = new_pwd
                    update_user(u["id"], **data)
                    st.success("Modifié.")
                    st.rerun()

            if is_main_admin(admin):
                if st.button("🗑️ Supprimer", key=f"del_{u['id']}"):
                    if u["id"] != admin["id"]:
                        delete_user(u["id"])
                        st.rerun()

    st.divider()
    if has_perm(admin, "ajouter_utilisateur"):
        st.subheader("➕ Ajouter un utilisateur manuellement")
        with st.form("add_user_form"):
            e = st.text_input("Email")
            p = st.text_input("Mot de passe", type="password")
            ok = st.form_submit_button("Créer")
        if ok:
            if not e or not p:
                st.error("Champs requis.")
            else:
                success, err = create_user(e.strip().lower(), p)
                if success:
                    st.success("Utilisateur créé.")
                    st.rerun()
                else:
                    st.error(err)


# ============================================================
# ONGLET ÉVÉNEMENTS
# ============================================================
def tab_evenements(admin):
    st.header("📅 Évènements")
    events = list_events()
    if not events:
        st.info("Aucun évènement.")
        return

    statuts = {"à venir": [], "en cours": [], "passé": []}
    for e in events:
        statuts[event_status(e)].append(e)

    for label in ["en cours", "à venir", "passé"]:
        st.subheader(f"📍 {label.capitalize()}")
        if not statuts[label]:
            st.caption("(aucun)")
            continue
        for e in statuts[label]:
            with st.expander(f"{e['name']} — {datetime.fromisoformat(e['start_at']).strftime('%d/%m/%Y %H:%M')}"):
                st.write(f"Début : {e['start_at']}")
                st.write(f"Fin   : {e['end_at']}")
                codes = list_codes_for_event(e["id"])
                if codes:
                    st.markdown("**Codes générés :**")
                    for c in codes:
                        exp = datetime.fromisoformat(c["expires_at"])
                        state = "✅ valide" if exp >= datetime.now() else "⌛ expiré"
                        st.caption(f"`{c['code']}` — expire {c['expires_at']} ({state})")
                if is_main_admin(admin) or has_perm(admin, "creer_evenement"):
                    if st.button("🗑️ Supprimer", key=f"del_ev_{e['id']}"):
                        delete_event(e["id"])
                        st.rerun()
        st.divider()


# ============================================================
# ONGLET CRÉER ÉVÉNEMENT
# ============================================================
def tab_creer_evenement(admin):
    st.header("➕ Créer un évènement")
    if not (is_main_admin(admin) or has_perm(admin, "creer_evenement")):
        st.error("Vous n'avez pas la permission.")
        return

    with st.form("create_event"):
        name = st.text_input("Nom de l'évènement")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Date de début")
            start_time = st.time_input("Heure de début")
        with col2:
            end_date = st.date_input("Date de fin")
            end_time = st.time_input("Heure de fin")
        ok = st.form_submit_button("Créer")

    if ok:
        if not name:
            st.error("Nom requis.")
        else:
            start_dt = datetime.combine(start_date, start_time)
            end_dt = datetime.combine(end_date, end_time)
            if end_dt <= start_dt:
                st.error("La date de fin doit être après la date de début.")
            else:
                create_event(name, start_dt.isoformat(), end_dt.isoformat(), admin["id"])
                st.success("Évènement créé.")
                st.rerun()


# ============================================================
# ONGLET PURGE
# ============================================================
def tab_purge(admin):
    st.header("🧹 Purge — élèves avec 3 absences ou plus")
    if not (is_main_admin(admin) or has_perm(admin, "acces_purge")):
        st.error("Vous n'avez pas la permission.")
        return

    users = [u for u in list_users() if not u["is_admin"]]
    flagged = [(u, get_absences_count(u["id"])) for u in users]
    flagged = [(u, a) for u, a in flagged if a >= 3]

    if not flagged:
        st.success("Aucun élève avec 3 absences ou plus.")
        return

    for u, ab in flagged:
        st.warning(f"**{u['email']}** — {ab} absences")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("♻️ Reset compteur", key=f"reset_{u['id']}"):
                reset_absences(u["id"])
                st.success("Compteur remis à zéro.")
                st.rerun()
        with col2:
            days = st.number_input("Suspension (jours)", min_value=1, value=7, key=f"pd_{u['id']}")
            if st.button("⏸️ Suspendre", key=f"sus_{u['id']}"):
                update_user(u["id"], status="suspendu",
                            suspended_until=(datetime.now() + timedelta(days=int(days))).isoformat())
                st.success("Suspendu.")
                st.rerun()
        with col3:
            if st.button("🚫 Bloquer", key=f"blk_{u['id']}"):
                update_user(u["id"], status="bloque")
                st.success("Bloqué.")
                st.rerun()
        st.divider()


# ============================================================
# ONGLET NOMMER ADMIN
# ============================================================
def tab_nommer_admin(admin):
    st.header("👑 Nommer un admin")
    if not (is_main_admin(admin) or has_perm(admin, "nommer_admin")):
        st.error("Vous n'avez pas la permission.")
        return

    users = [u for u in list_users() if not u["is_admin"]]
    if not users:
        st.info("Aucun élève à promouvoir.")
        return

    st.markdown("### Élèves disponibles")
    selected_users = {}
    for u in users:
        selected_users[u["id"]] = st.checkbox(u["email"], key=f"sel_{u['id']}")

    st.markdown("### Permissions à accorder")
    perms = {}
    for p in ALL_PERMISSIONS:
        perms[p] = st.checkbox(p, key=f"perm_{p}")

    if st.button("✅ Nommer admin"):
        chosen = [uid for uid, ok in selected_users.items() if ok]
        chosen_perms = [p for p, ok in perms.items() if ok]
        if not chosen:
            st.error("Sélectionnez au moins un élève.")
        elif not chosen_perms:
            st.error("Sélectionnez au moins une permission.")
        else:
            for uid in chosen:
                update_user(uid, is_admin=1, permissions=chosen_perms)
            st.success(f"{len(chosen)} élève(s) nommé(s) admin.")
            st.rerun()

    st.divider()
    st.subheader("Admins actuels")
    admins = [u for u in list_users() if u["is_admin"]]
    for a in admins:
        perms = json.loads(a["permissions"] or "[]")
        role = "👑 Principal" if a["is_main_admin"] else "🛠️ Admin"
        st.caption(f"{role} — {a['email']} — permissions: {', '.join(perms) if perms else '—'}")
        if is_main_admin(admin) and not a["is_main_admin"]:
            if st.button(f"❌ Retirer admin {a['email']}", key=f"rev_{a['id']}"):
                update_user(a["id"], is_admin=0, permissions=[])
                st.rerun()


# ============================================================
# ONGLET GÉNÉRER CODE
# ============================================================
def tab_generer_code(admin):
    st.header("🔑 Générer un code de présence")
    if not (is_main_admin(admin) or has_perm(admin, "generer_code")):
        st.error("Vous n'avez pas la permission.")
        return

    events = [e for e in list_events() if event_status(e) == "en cours"]
    if not events:
        st.info("Aucun évènement en cours.")
        return

    ev_map = {f"{e['name']} (#{e['id']})": e for e in events}
    choice = st.selectbox("Évènement (en cours uniquement)", list(ev_map.keys()))
    ev = ev_map[choice]

    with st.form("code_form"):
        code = st.text_input("Code à générer")
        unit = st.radio("Unité de durée", ["secondes", "minutes"], horizontal=True)
        duration = st.number_input("Durée de validité", min_value=1, value=5)
        ok = st.form_submit_button("Générer")

    if ok:
        if not code.strip():
            st.error("Entrez un code.")
        else:
            secs = int(duration) * (60 if unit == "minutes" else 1)
            create_code(ev["id"], code.strip(), secs, admin["id"])
            st.success(f"Code `{code}` créé pour {ev['name']}, valide {duration} {unit}.")
            st.rerun()

    st.divider()
    st.subheader("Codes existants pour cet évènement")
    for c in list_codes_for_event(ev["id"]):
        exp = datetime.fromisoformat(c["expires_at"])
        state = "✅ valide" if exp >= datetime.now() else "⌛ expiré"
        st.caption(f"`{c['code']}` — expire {c['expires_at']} ({state})")


# ============================================================
# ONGLET SAYNA (admin principal uniquement)
# ============================================================
def tab_sayna_admin(admin):
    st.header("🌐 Sayna (admin principal uniquement)")
    if not is_main_admin(admin):
        st.error("Accès réservé à l'admin principal.")
        return
    col1, col2 = st.columns(2)
    with col1:
        st.link_button("🔗 Sayna", SAYNA_URL, use_container_width=True)
    with col2:
        st.link_button("🔗 Sayna Admin", SAYNA_ADMIN_URL, use_container_width=True)


# ============================================================
# ONGLET MON COMPTE
# ============================================================
def tab_mon_compte(admin):
    st.header("👤 Mon compte admin")
    u = get_user_by_id(admin["id"])
    st.caption(f"Email actuel : **{u['email']}**")
    with st.form("acc_form"):
        new_email = st.text_input("Nouvelle adresse email", value=u["email"])
        old_pwd = st.text_input("Mot de passe actuel", type="password")
        new_pwd = st.text_input("Nouveau mot de passe", type="password")
        new_pwd2 = st.text_input("Confirmer le nouveau mot de passe", type="password")
        ok = st.form_submit_button("Enregistrer")

    if ok:
        if not verify_pwd(old_pwd, u["password"]):
            st.error("Mot de passe actuel incorrect.")
        else:
            data = {}
            if new_email and new_email.strip().lower() != u["email"]:
                data["email"] = new_email.strip().lower()
            if new_pwd:
                if new_pwd != new_pwd2:
                    st.error("Les nouveaux mots de passe ne correspondent pas.")
                    st.stop()
                data["password"] = new_pwd
            if data:
                update_user(u["id"], **data)
                st.success("Informations mises à jour.")
                st.rerun()
            else:
                st.info("Aucune modification.")


# ============================================================
# MAIN ADMIN
# ============================================================
def main_admin():
    admin = get_user_by_id(st.session_state["admin_id"])
    if not admin or not admin["is_admin"]:
        st.session_state.clear()
        st.rerun()

    with st.sidebar:
        role = "👑 Admin principal" if is_main_admin(admin) else "🛠️ Admin"
        st.markdown(f"### {role}")
        st.caption(admin["email"])
        st.divider()

        tabs = ["👥 Membres", "📅 Évènements", "➕ Créer un évènement",
                "🧹 Purge", "👑 Nommer admin", "🔑 Générer un code"]
        if is_main_admin(admin):
            tabs.append("🌐 Sayna")
        tabs.append("👤 Mon compte")

        choice = st.radio("Navigation", tabs)

        st.divider()
        if st.button("Se déconnecter"):
            logout()
            st.rerun()

    if choice == "👥 Membres":
        tab_membres(admin)
    elif choice == "📅 Évènements":
        tab_evenements(admin)
    elif choice == "➕ Créer un évènement":
        tab_creer_evenement(admin)
    elif choice == "🧹 Purge":
        tab_purge(admin)
    elif choice == "👑 Nommer admin":
        tab_nommer_admin(admin)
    elif choice == "🔑 Générer un code":
        tab_generer_code(admin)
    elif choice == "🌐 Sayna":
        tab_sayna_admin(admin)
    elif choice == "👤 Mon compte":
        tab_mon_compte(admin)


# ============================================================
# POINT D'ENTRÉE
# ============================================================
if "admin_id" not in st.session_state:
    page_login_admin()
else:
    main_admin()
