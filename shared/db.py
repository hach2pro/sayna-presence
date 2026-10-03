import psycopg2
import psycopg2.extras
import bcrypt
import json
import streamlit as st
from datetime import datetime, timedelta


# ============================================================
# SÉCURITÉ MOTS DE PASSE
# ============================================================
def hash_pwd(pwd: str) -> str:
    """Hash un mot de passe avec bcrypt (sel + work factor)."""
    return bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_pwd(pwd: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt."""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pwd.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ============================================================
# CONNEXION POSTGRESQL (NEON)
# ============================================================
def get_conn():
    """Retourne une connexion PostgreSQL vers Neon."""
    conn = psycopg2.connect(
        st.secrets["connections"]["neon"]["url"],
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn


def init_db():
    """Initialise la base de données (appelée au démarrage de chaque app)."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            status TEXT DEFAULT 'normal',
            is_admin INTEGER DEFAULT 0,
            is_main_admin INTEGER DEFAULT 0,
            permissions TEXT DEFAULT '[]',
            suspended_until TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            validated_at TEXT,
            UNIQUE(user_id, event_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS used_codes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            code_id INTEGER,
            UNIQUE(user_id, code_id)
        )
    """)

    conn.commit()

    # Créer l'admin principal par défaut s'il n'existe pas
    c.execute("SELECT * FROM users WHERE is_main_admin=1")
    row = c.fetchone()
    if not row:
        c.execute("""INSERT INTO users (email, password, is_admin, is_main_admin, permissions, status, created_at)
                     VALUES (%s, %s, 1, 1, %s, 'normal', %s)""",
                  ("admin@sayna.com", hash_pwd("admin123"),
                   json.dumps(["all"]), datetime.now().isoformat()))
        conn.commit()

    c.close()
    conn.close()


# ============================================================
# UTILISATEURS
# ============================================================
def get_user_by_email(email):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=%s", (email,))
    r = c.fetchone()
    c.close()
    conn.close()
    return dict(r) if r else None


def get_user_by_id(uid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    r = c.fetchone()
    c.close()
    conn.close()
    return dict(r) if r else None


def create_user(email, password, is_admin=0, is_main_admin=0, permissions=None):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO users (email, password, is_admin, is_main_admin, permissions, status, created_at)
                     VALUES (%s, %s, %s, %s, %s, 'normal', %s)""",
                  (email, hash_pwd(password), is_admin, is_main_admin,
                   json.dumps(permissions or []), datetime.now().isoformat()))
        conn.commit()
        return True, None
    except psycopg2.IntegrityError as e:
        conn.rollback()
        return False, str(e)
    finally:
        c.close()
        conn.close()


def update_user(uid, **kwargs):
    if not kwargs:
        return
    fields = []
    values = []
    for k, v in kwargs.items():
        if k == "password":
            v = hash_pwd(v)
        if k == "permissions" and isinstance(v, list):
            v = json.dumps(v)
        fields.append(f"{k}=%s")
        values.append(v)
    values.append(uid)
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=%s", values)
    conn.commit()
    c.close()
    conn.close()


def list_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY id")
    rows = c.fetchall()
    c.close()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(uid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()
    c.close()
    conn.close()


# ============================================================
# ÉVÉNEMENTS
# ============================================================
def create_event(name, start_at, end_at, created_by):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO events (name, start_at, end_at, created_by, created_at)
                 VALUES (%s, %s, %s, %s, %s)""",
              (name, start_at, end_at, created_by, datetime.now().isoformat()))
    conn.commit()
    c.close()
    conn.close()


def list_events():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM events ORDER BY start_at DESC")
    rows = c.fetchall()
    c.close()
    conn.close()
    return [dict(r) for r in rows]


def get_event(eid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id=%s", (eid,))
    r = c.fetchone()
    c.close()
    conn.close()
    return dict(r) if r else None


def event_status(ev):
    now = datetime.now()
    start = datetime.fromisoformat(ev["start_at"])
    end = datetime.fromisoformat(ev["end_at"])
    if now < start:
        return "à venir"
    if start <= now <= end:
        return "en cours"
    return "passé"


def delete_event(eid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id=%s", (eid,))
    c.execute("DELETE FROM codes WHERE event_id=%s", (eid,))
    c.execute("DELETE FROM attendance WHERE event_id=%s", (eid,))
    conn.commit()
    c.close()
    conn.close()


# ============================================================
# CODES DE PRÉSENCE
# ============================================================
def create_code(event_id, code, duration_seconds, created_by):
    expires = datetime.now() + timedelta(seconds=duration_seconds)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO codes (event_id, code, expires_at, created_by, created_at)
                 VALUES (%s, %s, %s, %s, %s)""",
              (event_id, code, expires.isoformat(), created_by, datetime.now().isoformat()))
    conn.commit()
    c.close()
    conn.close()


def list_codes_for_event(event_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM codes WHERE event_id=%s ORDER BY created_at DESC", (event_id,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return [dict(r) for r in rows]


def find_valid_code(event_id, code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM codes WHERE event_id=%s AND code=%s", (event_id, code))
    rows = c.fetchall()
    c.close()
    conn.close()
    now = datetime.now()
    for r in rows:
        d = dict(r)
        if datetime.fromisoformat(d["expires_at"]) >= now:
            return d
    return None


def find_valid_code_by_code(code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM codes WHERE code=%s", (code,))
    rows = c.fetchall()
    c.close()
    conn.close()
    now = datetime.now()
    valid = [dict(r) for r in rows if datetime.fromisoformat(dict(r)["expires_at"]) >= now]
    return valid[0] if valid else None


# ============================================================
# PRÉSENCES
# ============================================================
def validate_attendance(user_id, event_id, code_id):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO used_codes (user_id, code_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                  (user_id, code_id))
        c.execute("""INSERT INTO attendance (user_id, event_id, validated_at)
                     VALUES (%s, %s, %s) ON CONFLICT (user_id, event_id) DO NOTHING""",
                  (user_id, event_id, datetime.now().isoformat()))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        c.close()
        conn.close()


def user_attendance(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT a.*, e.name as event_name, e.start_at, e.end_at
                 FROM attendance a JOIN events e ON a.event_id = e.id
                 WHERE a.user_id=%s ORDER BY e.start_at DESC""", (user_id,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return [dict(r) for r in rows]


def user_has_attended(user_id, event_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM attendance WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    r = c.fetchone()
    c.close()
    conn.close()
    return r is not None


def get_absences_count(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM events")
    events = c.fetchall()
    c.execute("SELECT event_id FROM attendance WHERE user_id=%s", (user_id,))
    attended = c.fetchall()
    c.close()
    conn.close()
    attended_ids = {r["event_id"] for r in attended}
    now = datetime.now()
    abs_count = 0
    for e in events:
        end = datetime.fromisoformat(e["end_at"])
        if end < now and e["id"] not in attended_ids:
            abs_count += 1
    return abs_count


def get_presence_count(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as c FROM attendance WHERE user_id=%s", (user_id,))
    r = c.fetchone()
    c.close()
    conn.close()
    return r["c"]


def reset_absences(user_id):
    """Remet à zéro le compteur d'absences en marquant les événements passés comme 'assistés'."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, end_at FROM events")
    events = c.fetchall()
    now = datetime.now()
    for e in events:
        if datetime.fromisoformat(e["end_at"]) < now:
            try:
                c.execute("""INSERT INTO attendance (user_id, event_id, validated_at)
                             VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                          (user_id, e["id"], now.isoformat()))
            except Exception:
                pass
    conn.commit()
    c.close()
    conn.close()