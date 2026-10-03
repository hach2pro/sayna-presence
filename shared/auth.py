import streamlit as st
from datetime import datetime
from shared.db import get_user_by_email, verify_pwd, update_user


def check_user_status(user):
    """Retourne (ok, message). Gère la fin automatique d'une suspension."""
    if user["status"] == "bloque":
        return False, "🚫 Votre compte a été bloqué pour avoir enfreint une règle ou agi de manière irrégulière. Contactez l'admin."

    if user["status"] == "suspendu":
        until = user.get("suspended_until")
        if until:
            end = datetime.fromisoformat(until)
            if end > datetime.now():
                return False, f"⏸️ Votre compte est suspendu jusqu'au {end.strftime('%d/%m/%Y %H:%M')}. Contactez l'admin."
            else:
                # Suspension expirée -> remettre normal
                update_user(user["id"], status="normal", suspended_until=None)
                user["status"] = "normal"
        else:
            return False, "⏸️ Votre compte est suspendu. Contactez l'admin."

    return True, ""


def login(email, password):
    """Tente une connexion. Retourne (user_dict, None) ou (None, message_erreur)."""
    user = get_user_by_email(email)
    if not user:
        return None, "Aucun compte trouvé avec cette adresse."
    if not verify_pwd(password, user["password"]):
        return None, "Mot de passe incorrect."
    ok, msg = check_user_status(user)
    if not ok:
        return None, msg
    return user, None


def logout():
    """Vide la session Streamlit."""
    for k in list(st.session_state.keys()):
        del st.session_state[k]