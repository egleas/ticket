from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash
)
import sqlite3
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader

# ============================================================
# CONFIG
# ============================================================

app = Flask(__name__)
print("### ALMABAT NEW APP ###")
app.secret_key = "ALMABAT-HELPDESK-2026-SECRET"

DB = "helpdesk.db"

# ============================================================
# DATABASE
# ============================================================

def db():
    # SQLite robuste pour les accès simultanés Flask
    conn = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def migrate_database(conn):
    """
    Migration robuste pour anciens DB.
    Ne supprime aucune donnée.
    """

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            full_name TEXT,
            email TEXT,
            department TEXT,
            service TEXT,
            role TEXT DEFAULT 'user',
            created_at TEXT
        )
    """)

    # anciennes colonnes possibles
    add_column_if_missing(conn, "users", "username", "TEXT")
    add_column_if_missing(conn, "users", "password", "TEXT")
    add_column_if_missing(conn, "users", "full_name", "TEXT")
    add_column_if_missing(conn, "users", "email", "TEXT")
    add_column_if_missing(conn, "users", "department", "TEXT")
    add_column_if_missing(conn, "users", "service", "TEXT")
    add_column_if_missing(conn, "users", "role", "TEXT DEFAULT 'user'")
    add_column_if_missing(conn, "users", "created_at", "TEXT")
    add_column_if_missing(conn, "users", "notifications_enabled", "INTEGER DEFAULT 1")

    # --------------------------------------------------------
    # TICKETS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER,
            title TEXT,
            subject TEXT,
            description TEXT,
            type TEXT,
            category TEXT,
            subcategory TEXT,
            department TEXT,
            service TEXT,
            priority TEXT,
            status TEXT,
            location TEXT,
            asset TEXT,
            technician_id INTEGER,
            resolution TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # Colonnes legacy + nouvelles
    add_column_if_missing(conn, "tickets", "requester_id", "INTEGER")
    add_column_if_missing(conn, "tickets", "title", "TEXT")
    add_column_if_missing(conn, "tickets", "subject", "TEXT")
    add_column_if_missing(conn, "tickets", "description", "TEXT")
    add_column_if_missing(conn, "tickets", "type", "TEXT")
    add_column_if_missing(conn, "tickets", "category", "TEXT")
    add_column_if_missing(conn, "tickets", "subcategory", "TEXT")
    add_column_if_missing(conn, "tickets", "department", "TEXT")
    add_column_if_missing(conn, "tickets", "service", "TEXT")
    add_column_if_missing(conn, "tickets", "priority", "TEXT")
    add_column_if_missing(conn, "tickets", "status", "TEXT")
    add_column_if_missing(conn, "tickets", "location", "TEXT")
    add_column_if_missing(conn, "tickets", "asset", "TEXT")
    add_column_if_missing(conn, "tickets", "technician_id", "INTEGER")
    add_column_if_missing(conn, "tickets", "resolution", "TEXT")
    add_column_if_missing(conn, "tickets", "created_at", "TEXT")
    add_column_if_missing(conn, "tickets", "updated_at", "TEXT")

    # Legacy mapping
    if column_exists(conn, "tickets", "user_id"):
        conn.execute("""
            UPDATE tickets
            SET requester_id = user_id
            WHERE requester_id IS NULL
        """)

    if column_exists(conn, "tickets", "content"):
        conn.execute("""
            UPDATE tickets
            SET description = content
            WHERE description IS NULL OR description = ''
        """)

    # title <-> subject
    conn.execute("""
        UPDATE tickets
        SET subject = title
        WHERE (subject IS NULL OR subject = '')
        AND title IS NOT NULL
    """)

    conn.execute("""
        UPDATE tickets
        SET title = subject
        WHERE (title IS NULL OR title = '')
        AND subject IS NOT NULL
    """)

    # valeurs par défaut
    conn.execute("""
        UPDATE tickets
        SET subject = 'Sans objet'
        WHERE subject IS NULL OR subject = ''
    """)

    conn.execute("""
        UPDATE tickets
        SET title = subject
        WHERE title IS NULL OR title = ''
    """)

    conn.execute("""
        UPDATE tickets
        SET description = ''
        WHERE description IS NULL
    """)

    conn.execute("""
        UPDATE tickets
        SET type = 'Incident'
        WHERE type IS NULL OR type = ''
    """)

    conn.execute("""
        UPDATE tickets
        SET priority = 'Moyenne'
        WHERE priority IS NULL OR priority = ''
    """)

    conn.execute("""
        UPDATE tickets
        SET status = 'Nouveau'
        WHERE status IS NULL OR status = ''
    """)

    conn.execute("""
        UPDATE tickets
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL OR created_at = ''
    """)

    conn.execute("""
        UPDATE tickets
        SET updated_at = created_at
        WHERE updated_at IS NULL OR updated_at = ''
    """)

    # --------------------------------------------------------
    # COMMENTS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            user_id INTEGER,
            comment TEXT,
            is_internal INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    add_column_if_missing(conn, "comments", "ticket_id", "INTEGER")
    add_column_if_missing(conn, "comments", "user_id", "INTEGER")
    add_column_if_missing(conn, "comments", "comment", "TEXT")
    add_column_if_missing(conn, "comments", "is_internal", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "comments", "created_at", "TEXT")

    # --------------------------------------------------------
    # ACTIVITY LOGS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ticket_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TEXT
        )
    """)

    add_column_if_missing(conn, "activity_logs", "user_id", "INTEGER")
    add_column_if_missing(conn, "activity_logs", "ticket_id", "INTEGER")
    add_column_if_missing(conn, "activity_logs", "action", "TEXT")
    add_column_if_missing(conn, "activity_logs", "details", "TEXT")
    add_column_if_missing(conn, "activity_logs", "created_at", "TEXT")

    # --------------------------------------------------------
    # NOTIFICATIONS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticket_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    add_column_if_missing(conn, "notifications", "user_id", "INTEGER")
    add_column_if_missing(conn, "notifications", "ticket_id", "INTEGER")
    add_column_if_missing(conn, "notifications", "title", "TEXT")
    add_column_if_missing(conn, "notifications", "message", "TEXT")
    add_column_if_missing(conn, "notifications", "is_read", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "notifications", "created_at", "TEXT")

    # --------------------------------------------------------
    # DEFAULT ADMIN
    # --------------------------------------------------------

    admin = conn.execute("""
        SELECT id FROM users
        WHERE username = 'admin'
        LIMIT 1
    """).fetchone()

    if not admin:
        conn.execute("""
            INSERT INTO users
            (
                username,
                password,
                full_name,
                email,
                department,
                service,
                role,
                notifications_enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "admin",
            generate_password_hash("Admin@123"),
            "Administrateur",
            "admin@almabat.ma",
            "IT",
            "Support IT",
            "admin",
            1,
            datetime.now().isoformat(timespec="seconds")
        ))

    conn.commit()


def init_db():
    conn = db()
    migrate_database(conn)
    conn.close()


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.now().isoformat(timespec="seconds")


def current_user():
    if "user_id" not in session:
        return None

    conn = db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    conn.close()
    return user


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()

        if not user:
            return redirect(url_for("login"))

        if user["role"] not in ("admin", "technician"):
            flash("Accès réservé au service IT.", "danger")
            return redirect(url_for("dashboard"))

        return f(*args, **kwargs)

    return decorated


def admin_only_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login"))
        if user["role"] != "admin":
            flash("Accès réservé à l'administrateur.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def log_activity(user_id, ticket_id, action, details=""):
    conn = db()

    conn.execute("""
        INSERT INTO activity_logs
        (
            user_id,
            ticket_id,
            action,
            details,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        ticket_id,
        action,
        details,
        now()
    ))

    conn.commit()
    conn.close()


def create_ticket_notifications(ticket_id, subject, requester_id):
    """Crée une notification pour tous les admins/techniciens sauf le créateur."""
    conn = db()
    recipients = conn.execute("""
        SELECT id FROM users
        WHERE role IN ('admin', 'technician')
          AND COALESCE(notifications_enabled, 1) = 1
          AND id != ?
    """, (requester_id,)).fetchall()

    title = "Nouveau ticket"
    message = f"Ticket #{ticket_id} : {subject}"
    created = now()

    for row in recipients:
        conn.execute("""
            INSERT INTO notifications
            (user_id, ticket_id, title, message, is_read, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (row["id"], ticket_id, title, message, created))

    conn.commit()
    conn.close()


def status_class(status):
    mapping = {
        "Nouveau": "status-new",
        "En cours": "status-progress",
        "En attente": "status-wait",
        "Résolu": "status-resolved",
        "Fermé": "status-closed"
    }

    return mapping.get(status, "status-new")


def priority_class(priority):
    mapping = {
        "Basse": "priority-low",
        "Moyenne": "priority-medium",
        "Haute": "priority-high",
        "Critique": "priority-critical"
    }

    return mapping.get(priority, "priority-medium")


# ============================================================
# DATA
# ============================================================

DEPARTMENTS = {
    "Finance / Comptabilité": [
        "Comptabilité",
        "Trésorerie",
        "Facturation"
    ],
    "Achats": [
        "Achats",
        "Approvisionnement"
    ],
    "Commercial": [
        "Commercial",
        "Administration des ventes"
    ],
    "Planification": [
        "Planification"
    ],
    "Direction Projet": [
        "Projet"
    ],
    "RH": [
        "Ressources Humaines"
    ],
    "Logistique": [
        "Logistique",
        "Stock"
    ],
    "Direction": [
        "Direction Générale"
    ],
    "IT": [
        "Support IT",
        "Infrastructure",
        "Systèmes & Réseaux"
    ],
    "Marketing": [
        "Marketing"
    ],
    "Juridique": [
        "Juridique"
    ],
    "Autre": [
        "Autre"
    ]
}


CATEGORIES = {
    "Poste de travail": [
        "PC lent",
        "PC ne démarre pas",
        "Windows",
        "Écran",
        "Clavier/Souris"
    ],
    "Réseau": [
        "Internet",
        "Wi-Fi",
        "RJ45",
        "VPN",
        "DNS/DHCP"
    ],
    "Impression": [
        "Imprimante",
        "Scanner",
        "Toner",
        "Impression bloquée"
    ],
    "Messagerie": [
        "Outlook",
        "Email",
        "Boîte pleine",
        "Spam"
    ],
    "Accès & Sécurité": [
        "Compte utilisateur",
        "Mot de passe",
        "Active Directory",
        "Droits",
        "VPN"
    ],
    "Fichiers & Partages": [
        "Dossier partagé",
        "Permissions",
        "NAS/Serveur"
    ],
    "Logiciels": [
        "Sage",
        "Adobe",
        "Office",
        "Application métier"
    ],
    "Serveurs & Infrastructure": [
        "Serveur",
        "Virtualisation",
        "Backup"
    ],
    "Téléphonie / VoIP": [
        "Téléphone",
        "VoIP"
    ],
    "Matériel": [
        "PC",
        "Écran",
        "Switch",
        "Accessoire"
    ],
    "Demande de service": [
        "Nouveau PC",
        "Installation logiciel",
        "Création compte",
        "Accès dossier",
        "Installation imprimante"
    ],
    "Sécurité informatique": [
        "Antivirus",
        "CrowdStrike",
        "Phishing",
        "Email suspect"
    ]
}


# ============================================================
# BASE TEMPLATE
# ============================================================

BASE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>{{ title or "ALMABAT Helpdesk" }}</title>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

:root {
    --bg: #07111f;
    --bg2: #0b1728;
    --card: rgba(17, 31, 51, .72);
    --card2: rgba(20, 37, 60, .85);
    --border: rgba(255,255,255,.08);

    --text: #f4f7fb;
    --muted: #8fa2bb;

    --blue: #2388ff;
    --blue2: #4da3ff;

    --green: #22c55e;
    --orange: #f59e0b;
    --red: #ef4444;
    --purple: #8b5cf6;

    --shadow: 0 20px 60px rgba(0,0,0,.35);
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background:
        radial-gradient(circle at 10% 10%, rgba(35,136,255,.15), transparent 30%),
        radial-gradient(circle at 90% 20%, rgba(139,92,246,.10), transparent 25%),
        linear-gradient(135deg, #06101d, #091728 55%, #06111f);

    color: var(--text);
    font-family: Inter, Arial, sans-serif;
    min-height: 100vh;
}

a {
    color: inherit;
    text-decoration: none;
}

button,
input,
select,
textarea {
    font-family: inherit;
}

.app {
    display: flex;
    min-height: 100vh;
}

/* =========================================================
SIDEBAR
========================================================= */

.sidebar {
    width: 260px;
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;

    background: rgba(5,14,26,.88);
    backdrop-filter: blur(20px);

    border-right: 1px solid var(--border);

    padding: 24px 16px;

    z-index: 100;
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 10px 28px;
}

.logo-mark {
    width: 42px;
    height: 42px;
    border-radius: 13px;

    display: flex;
    align-items: center;
    justify-content: center;

    background: linear-gradient(135deg, #2388ff, #6a5cff);
    box-shadow: 0 10px 30px rgba(35,136,255,.3);

    font-size: 20px;
    font-weight: 800;
}

.logo-text strong {
    display: block;
    font-size: 15px;
}

.logo-text span {
    display: block;
    color: var(--muted);
    font-size: 11px;
    margin-top: 3px;
}

.nav-title {
    color: #60738d;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 16px 12px 8px;
}

.nav a {
    display: flex;
    align-items: center;
    gap: 12px;

    padding: 12px 14px;
    margin-bottom: 5px;

    border-radius: 12px;

    color: #9fb0c7;
    font-size: 13px;

    transition: .2s;
}

.nav a:hover {
    background: rgba(255,255,255,.05);
    color: white;
    transform: translateX(3px);
}

.nav a.active {
    background: linear-gradient(
        90deg,
        rgba(35,136,255,.22),
        rgba(35,136,255,.06)
    );

    color: white;

    border: 1px solid rgba(35,136,255,.18);
}

.nav-icon {
    width: 22px;
    text-align: center;
}

.sidebar-bottom {
    position: absolute;
    bottom: 18px;
    left: 16px;
    right: 16px;
}

.user-mini {
    padding: 13px;
    border-radius: 14px;

    background: rgba(255,255,255,.035);
    border: 1px solid var(--border);

    display: flex;
    align-items: center;
    gap: 10px;
}

.avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;

    display: flex;
    align-items: center;
    justify-content: center;

    background: linear-gradient(135deg,#2388ff,#7c3aed);

    font-size: 12px;
    font-weight: 800;
}

.user-mini-info {
    overflow: hidden;
}

.user-mini-info strong {
    display: block;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.user-mini-info span {
    color: var(--muted);
    font-size: 10px;
}

/* =========================================================
MAIN
========================================================= */

.main {
    margin-left: 260px;
    width: calc(100% - 260px);
    padding: 25px 32px;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;

    margin-bottom: 28px;
}

.page-title h1 {
    margin: 0;
    font-size: 27px;
    letter-spacing: -.5px;
}

.page-title p {
    margin: 7px 0 0;
    color: var(--muted);
    font-size: 12px;
}

.top-actions {
    display: flex;
    gap: 10px;
    align-items: center;
}

/* =========================================================
BUTTONS
========================================================= */

.btn {
    border: 0;
    cursor: pointer;

    border-radius: 11px;
    padding: 11px 16px;

    color: white;

    font-size: 12px;
    font-weight: 700;

    transition: .2s;
}

.btn:hover {
    transform: translateY(-2px);
}

.btn-primary {
    background: linear-gradient(135deg,#2388ff,#4169ff);
    box-shadow: 0 8px 25px rgba(35,136,255,.25);
}

.btn-success {
    background: linear-gradient(135deg,#16a34a,#22c55e);
}

.btn-danger {
    background: linear-gradient(135deg,#dc2626,#ef4444);
}

.btn-warning {
    background: linear-gradient(135deg,#d97706,#f59e0b);
}

.btn-secondary {
    background: rgba(255,255,255,.06);
    border: 1px solid var(--border);
}

/* =========================================================
CARDS
========================================================= */

.grid {
    display: grid;
    gap: 16px;
}

.grid-4 {
    grid-template-columns: repeat(4,1fr);
}

.grid-3 {
    grid-template-columns: repeat(3,1fr);
}

.grid-2 {
    grid-template-columns: repeat(2,1fr);
}

.card {
    background: var(--card);
    backdrop-filter: blur(18px);

    border: 1px solid var(--border);
    border-radius: 18px;

    padding: 20px;

    box-shadow: var(--shadow);
}

.card:hover {
    border-color: rgba(255,255,255,.13);
}

.kpi {
    position: relative;
    overflow: hidden;
}

.kpi::after {
    content: "";
    position: absolute;

    width: 120px;
    height: 120px;

    border-radius: 50%;

    right: -45px;
    top: -50px;

    background: rgba(35,136,255,.08);
}

.kpi-label {
    color: var(--muted);
    font-size: 11px;
}

.kpi-number {
    font-size: 31px;
    font-weight: 800;
    margin-top: 9px;
}

.kpi-bottom {
    margin-top: 9px;
    font-size: 10px;
    color: #71849e;
}

/* =========================================================
TABLE
========================================================= */

.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th {
    text-align: left;
    color: #70849e;
    font-size: 10px;

    text-transform: uppercase;
    letter-spacing: .7px;

    padding: 12px;
    border-bottom: 1px solid var(--border);
}

td {
    padding: 14px 12px;
    border-bottom: 1px solid rgba(255,255,255,.045);

    font-size: 12px;
}

tr:hover td {
    background: rgba(255,255,255,.018);
}

.ticket-id {
    color: #5caaff;
    font-weight: 800;
}

.ticket-title {
    font-weight: 700;
}

.muted {
    color: var(--muted);
}

/* =========================================================
BADGES
========================================================= */

.badge {
    display: inline-flex;
    align-items: center;

    padding: 5px 9px;

    border-radius: 30px;

    font-size: 9px;
    font-weight: 800;
}

.status-new {
    background: rgba(35,136,255,.14);
    color: #5cabff;
}

.status-progress {
    background: rgba(245,158,11,.14);
    color: #fbbf24;
}

.status-wait {
    background: rgba(139,92,246,.14);
    color: #a78bfa;
}

.status-resolved {
    background: rgba(34,197,94,.14);
    color: #4ade80;
}

.status-closed {
    background: rgba(148,163,184,.12);
    color: #94a3b8;
}

.priority-low {
    color: #4ade80;
}

.priority-medium {
    color: #fbbf24;
}

.priority-high {
    color: #fb923c;
}

.priority-critical {
    color: #f87171;
}

/* =========================================================
FORMS
========================================================= */

.form-grid {
    display: grid;
    grid-template-columns: repeat(2,1fr);
    gap: 16px;
}

.form-group {
    margin-bottom: 4px;
}

.form-group.full {
    grid-column: 1 / -1;
}

label {
    display: block;

    margin-bottom: 7px;

    color: #9fb0c7;
    font-size: 11px;
    font-weight: 700;
}

input,
select,
textarea {
    width: 100%;

    padding: 12px 13px;

    color: white;
    background: rgba(4,13,25,.65);

    border: 1px solid rgba(255,255,255,.08);
    border-radius: 10px;

    outline: none;

    font-size: 12px;

    transition: .2s;
}

input:focus,
select:focus,
textarea:focus {
    border-color: rgba(35,136,255,.65);
    box-shadow: 0 0 0 3px rgba(35,136,255,.08);
}

textarea {
    min-height: 130px;
    resize: vertical;
}

select option {
    background: #0d1a2c;
}

/* =========================================================
ALERT
========================================================= */

.flash-container {
    margin-bottom: 18px;
}

.flash {
    padding: 12px 15px;
    border-radius: 12px;

    font-size: 12px;

    margin-bottom: 8px;
}

.flash-success {
    background: rgba(34,197,94,.12);
    color: #4ade80;
    border: 1px solid rgba(34,197,94,.15);
}

.flash-danger {
    background: rgba(239,68,68,.12);
    color: #f87171;
    border: 1px solid rgba(239,68,68,.15);
}

.flash-warning {
    background: rgba(245,158,11,.12);
    color: #fbbf24;
    border: 1px solid rgba(245,158,11,.15);
}

/* =========================================================
DETAIL
========================================================= */

.detail-grid {
    display: grid;
    grid-template-columns: 1fr 330px;
    gap: 18px;
}

.ticket-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;

    gap: 20px;
}

.ticket-header h2 {
    margin: 0;
    font-size: 22px;
}

.ticket-header p {
    color: var(--muted);
    font-size: 11px;
}

.meta-grid {
    display: grid;
    grid-template-columns: repeat(2,1fr);
    gap: 12px;
    margin-top: 20px;
}

.meta {
    padding: 13px;

    background: rgba(255,255,255,.025);
    border: 1px solid var(--border);

    border-radius: 12px;
}

.meta small {
    color: #657991;
    display: block;
    font-size: 9px;
    margin-bottom: 5px;
}

.meta strong {
    font-size: 11px;
}

.description {
    margin-top: 20px;

    line-height: 1.7;
    color: #c6d2e1;

    font-size: 13px;

    white-space: pre-wrap;
}

.timeline {
    margin-top: 25px;
}

.timeline-item {
    display: flex;
    gap: 12px;

    padding-bottom: 20px;
}

.timeline-dot {
    width: 10px;
    height: 10px;

    border-radius: 50%;

    background: #2388ff;

    margin-top: 5px;

    box-shadow: 0 0 15px rgba(35,136,255,.7);

    flex-shrink: 0;
}

.timeline-content {
    flex: 1;
}

.timeline-content strong {
    font-size: 11px;
}

.timeline-content p {
    color: #a7b7cb;
    font-size: 11px;
    margin: 6px 0;
}

.timeline-date {
    color: #60738d;
    font-size: 9px;
}

/* =========================================================
LOGIN
========================================================= */

.login-page {
    min-height: 100vh;

    display: flex;
    align-items: center;
    justify-content: center;

    padding: 20px;
}

.login-card {
    width: 420px;

    padding: 35px;

    background: rgba(12,25,42,.78);
    backdrop-filter: blur(25px);

    border: 1px solid rgba(255,255,255,.08);
    border-radius: 25px;

    box-shadow: 0 30px 100px rgba(0,0,0,.5);
}

.login-logo {
    width: 58px;
    height: 58px;

    border-radius: 18px;

    display: flex;
    align-items: center;
    justify-content: center;

    margin-bottom: 20px;

    background: linear-gradient(135deg,#2388ff,#6d5dfc);

    font-size: 25px;
    font-weight: 800;
}

.login-card h1 {
    margin: 0;
    font-size: 25px;
}

.login-card p {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 28px;
}

.login-card .form-group {
    margin-bottom: 15px;
}

/* =========================================================
SEARCH
========================================================= */

.toolbar {
    display: flex;
    gap: 10px;

    margin-bottom: 18px;
}

.toolbar input {
    max-width: 320px;
}

/* =========================================================
EMPTY
========================================================= */

.empty {
    text-align: center;
    padding: 45px 20px;

    color: var(--muted);
}

.empty-icon {
    font-size: 35px;
    margin-bottom: 10px;
}

/* =========================================================
RESPONSIVE
========================================================= */

.mobile-menu {
    display: none;
}

@media(max-width:1100px) {

    .grid-4 {
        grid-template-columns: repeat(2,1fr);
    }

    .detail-grid {
        grid-template-columns: 1fr;
    }

}

@media(max-width:800px) {

    .sidebar {
        transform: translateX(-100%);
        transition: .25s;
    }

    .sidebar.open {
        transform: translateX(0);
    }

    .main {
        margin-left: 0;
        width: 100%;
        padding: 18px;
    }

    .mobile-menu {
        display: flex;
    }

    .form-grid {
        grid-template-columns: 1fr;
    }

    .grid-2,
    .grid-3,
    .grid-4 {
        grid-template-columns: 1fr;
    }

    .topbar {
        align-items: flex-start;
    }

}


.notification-wrap { position: relative; }
.notification-btn { position: relative; min-width: 48px; }
.notification-badge { position: absolute; top: -5px; right: -5px; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 99px; background: #ef4444; color: #fff; font-size: 11px; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; }
.notification-panel { position: absolute; right: 0; top: calc(100% + 10px); width: 360px; max-width: calc(100vw - 30px); background: #0d1b2e; border: 1px solid rgba(255,255,255,.10); border-radius: 16px; box-shadow: 0 20px 50px rgba(0,0,0,.35); z-index: 9999; overflow: hidden; }
.notification-header { padding: 13px 15px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,.08); color:#fff; }
.notification-header button { border:0; background:transparent; color:#5fa0ff; cursor:pointer; }
.notification-item { padding: 13px 15px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; }
.notification-item:hover { background: rgba(255,255,255,.04); }
.notification-item strong { color:#fff; display:block; margin-bottom:4px; }
.notification-item span { color:#9fb0c7; font-size:13px; }
.notification-item small { color:#64748b; display:block; margin-top:6px; }
.notification-empty { padding: 25px 15px; text-align:center; color:#71849e; }
@media (max-width: 600px) { .notification-panel { position: fixed; right: 12px; top: 72px; width: calc(100vw - 24px); } }
</style>
</head>

<body>

{% if current_user %}

<div class="app">

<!-- SIDEBAR -->

<aside class="sidebar" id="sidebar">

    <div class="logo">
        <div class="logo-mark">A</div>

        <div class="logo-text">
            <strong>ALMABAT</strong>
            <span>IT HELPDESK</span>
        </div>
    </div>

    <div class="nav-title">Navigation</div>

    <div class="nav">

        <a href="{{ url_for('dashboard') }}"
           class="{% if request.endpoint == 'dashboard' %}active{% endif %}">
            <span class="nav-icon">⌂</span>
            Dashboard
        </a>

        <a href="{{ url_for('tickets') }}"
           class="{% if request.endpoint in ['tickets','ticket_detail'] %}active{% endif %}">
            <span class="nav-icon">▣</span>
            Tickets
        </a>

        <a href="{{ url_for('new_ticket') }}">
            <span class="nav-icon">＋</span>
            Nouveau ticket
        </a>

        {% if current_user["role"] in ["admin","technician"] %}

        <div class="nav-title">Administration</div>

        <a href="{{ url_for('users') }}"
           class="{% if request.endpoint == 'users' %}active{% endif %}">
            <span class="nav-icon">♙</span>
            Utilisateurs
        </a>

        <a href="{{ url_for('statistics') }}"
           class="{% if request.endpoint == 'statistics' %}active{% endif %}">
            <span class="nav-icon">◒</span>
            Statistiques
        </a>

        <a href="{{ url_for('history') }}"
           class="{% if request.endpoint == 'history' %}active{% endif %}">
            <span class="nav-icon">◷</span>
            Historique
        </a>

        {% endif %}

        <div class="nav-title">Compte</div>

        <a href="{{ url_for('profile') }}"
           class="{% if request.endpoint == 'profile' %}active{% endif %}">
            <span class="nav-icon">⚙</span>
            Mon profil
        </a>

        <a href="{{ url_for('logout') }}">
            <span class="nav-icon">↪</span>
            Déconnexion
        </a>

    </div>

    <div class="sidebar-bottom">

        <div class="user-mini">

            <div class="avatar">
                {{ current_user["full_name"][0]|upper if current_user["full_name"] else "U" }}
            </div>

            <div class="user-mini-info">
                <strong>{{ current_user["full_name"] }}</strong>
                <span>
                    {% if current_user["role"] == "admin" %}
                    Administrateur
                    {% elif current_user["role"] == "technician" %}
                    Technicien IT
                    {% else %}
                    Utilisateur
                    {% endif %}
                </span>
            </div>

        </div>

    </div>

</aside>

<!-- MAIN -->

<main class="main">

    <div class="topbar">

        <div class="page-title">

            <div style="display:flex;gap:10px;align-items:center">

                <button
                    class="btn btn-secondary mobile-menu"
                    onclick="document.getElementById('sidebar').classList.toggle('open')">
                    ☰
                </button>

                <div>

                    <h1>{{ page_title }}</h1>

                    <p>{{ page_subtitle }}</p>

                </div>

            </div>

        </div>

        <div class="top-actions">

            {% if current_user["role"] in ["admin", "technician"] %}
            <div class="notification-wrap">
                <button id="notificationBtn" class="btn btn-secondary notification-btn" type="button" onclick="toggleNotifications()" title="Notifications">
                    🔔 <span id="notificationBadge" class="notification-badge" style="display:none">0</span>
                </button>
                <div id="notificationPanel" class="notification-panel" style="display:none">
                    <div class="notification-header">
                        <strong>Notifications</strong>
                        <button type="button" onclick="markAllNotificationsRead()">Tout lire</button>
                    </div>
                    <div id="notificationList">
                        <div class="notification-empty">Aucune nouvelle notification</div>
                    </div>
                </div>
            </div>
            {% endif %}

            {% if request.endpoint != 'new_ticket' %}
            <a href="{{ url_for('new_ticket') }}" class="btn btn-primary">
                ＋ Nouveau ticket
            </a>
            {% endif %}

        </div>

    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}

        {% if messages %}

        <div class="flash-container">

            {% for category, message in messages %}

            <div class="flash flash-{{ category }}">
                {{ message }}
            </div>

            {% endfor %}

        </div>

        {% endif %}

    {% endwith %}

    {{ content|safe }}

</main>

</div>

{% else %}

{{ content|safe }}

{% endif %}

<script>

function updateServices() {

    const department =
        document.getElementById("department");

    const service =
        document.getElementById("service");

    if (!department || !service) return;

    const data = {{ departments_json|safe }};

    const services = data[department.value] || [];

    service.innerHTML = "";

    services.forEach(function(item) {

        const option =
            document.createElement("option");

        option.value = item;
        option.textContent = item;

        service.appendChild(option);

    });

}


function updateSubcategories() {

    const category =
        document.getElementById("category");

    const subcategory =
        document.getElementById("subcategory");

    if (!category || !subcategory) return;

    const data = {{ categories_json|safe }};

    const values = data[category.value] || [];

    subcategory.innerHTML = "";

    values.forEach(function(item) {

        const option =
            document.createElement("option");

        option.value = item;
        option.textContent = item;

        subcategory.appendChild(option);

    });

}

</script>


<script>
let notificationTimer = null;
let lastNotificationId = 0;

function toggleNotifications() {
    const panel = document.getElementById('notificationPanel');
    if (!panel) return;
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    if (panel.style.display === 'block') loadNotifications();
}

async function loadNotifications() {
    try {
        const r = await fetch('/api/notifications', {cache:'no-store'});
        if (!r.ok) return;
        const data = await r.json();
        const badge = document.getElementById('notificationBadge');
        const list = document.getElementById('notificationList');
        if (!badge || !list) return;

        const unread = data.unread_count || 0;
        badge.textContent = unread > 99 ? '99+' : unread;
        badge.style.display = unread ? 'inline-flex' : 'none';

        if (!data.notifications.length) {
            list.innerHTML = '<div class="notification-empty">Aucune nouvelle notification</div>';
        } else {
            list.innerHTML = data.notifications.map(n => `
                <div class="notification-item" onclick="openNotification(${n.id}, ${n.ticket_id || 0})">
                    <strong>${escapeHtml(n.title)}</strong>
                    <span>${escapeHtml(n.message)}</span>
                    <small>${escapeHtml(n.created_at)}</small>
                </div>`).join('');
        }

        // Notification navigateur quand elle est autorisée.
        if (lastNotificationId && data.notifications.length) {
            const newest = data.notifications[0];
            if (newest.id > lastNotificationId && 'Notification' in window && Notification.permission === 'granted') {
                new Notification(newest.title, {body:newest.message});
            }
        }
        if (data.notifications.length) lastNotificationId = Math.max(lastNotificationId, ...data.notifications.map(n => n.id));
    } catch (e) {
        console.log('Notification polling:', e);
    }
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
}

async function openNotification(id, ticketId) {
    try { await fetch('/api/notifications/' + id + '/read', {method:'POST'}); } catch(e) {}
    if (ticketId) window.location.href = '/tickets/' + ticketId;
}

async function markAllNotificationsRead() {
    try { await fetch('/api/notifications/read-all', {method:'POST'}); } catch(e) {}
    loadNotifications();
}

async function enableBrowserNotifications() {
    if (!('Notification' in window)) return;
    try {
        if (Notification.permission === 'default') await Notification.requestPermission();
    } catch(e) {}
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('notificationBtn')) {
        loadNotifications();
        notificationTimer = setInterval(loadNotifications, 4000);
        document.getElementById('notificationBtn').addEventListener('click', enableBrowserNotifications, {once:true});
    }
});
</script>
</body>
</html>
"""


# ============================================================
# TEMPLATE RENDER
# ============================================================

def render_page(content, page_title="ALMABAT Helpdesk",
                page_subtitle="Gestion du support informatique"):

    import json

    return render_template_string(
        BASE,
        content=content,
        title=page_title,
        page_title=page_title,
        page_subtitle=page_subtitle,
        current_user=current_user(),
        departments_json=json.dumps(DEPARTMENTS, ensure_ascii=False),
        categories_json=json.dumps(CATEGORIES, ensure_ascii=False)
    )


# ============================================================
# LOGIN
# ============================================================

LOGIN_HTML = """
<div class="login-page">

    <div class="login-card">

        <div class="login-logo">
            A
        </div>

        <h1>ALMABAT Helpdesk</h1>

        <p>
            Plateforme de gestion des incidents
            et demandes IT
        </p>

        <form method="POST">

            <div class="form-group">

                <label>Nom utilisateur</label>

                <input
                    type="text"
                    name="username"
                    placeholder="Votre identifiant"
                    required
                    autofocus>

            </div>

            <div class="form-group">

                <label>Mot de passe</label>

                <input
                    type="password"
                    name="password"
                    placeholder="Votre mot de passe"
                    required>

            </div>

            <button
                class="btn btn-primary"
                style="width:100%;margin-top:8px">

                Se connecter

            </button>

        </form>


    </div>

</div>
"""


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE username = ?
        """, (username,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        flash(
            "Identifiant ou mot de passe incorrect.",
            "danger"
        )

    return render_page(
        LOGIN_HTML,
        page_title="Connexion - ALMABAT",
        page_subtitle="Plateforme de support informatique"
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():

    conn = db()

    user = current_user()

    if user["role"] in ("admin", "technician"):

        total = conn.execute("""
            SELECT COUNT(*) c FROM tickets
        """).fetchone()["c"]

        new = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE status = 'Nouveau'
        """).fetchone()["c"]

        progress = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE status = 'En cours'
        """).fetchone()["c"]

        resolved = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE status IN ('Résolu','Fermé')
        """).fetchone()["c"]
        unassigned = conn.execute("SELECT COUNT(*) c FROM tickets WHERE status NOT IN ('Résolu','Fermé') AND (technician_id IS NULL OR technician_id=0)").fetchone()["c"]
        it_staff = conn.execute("SELECT COUNT(*) c FROM users WHERE role IN ('admin','technician')").fetchone()["c"]
        active_users = conn.execute("SELECT COUNT(*) c FROM users WHERE role='user'").fetchone()["c"]

        recent = conn.execute("""
            SELECT
                t.*,
                u.full_name requester,
                tech.full_name technician
            FROM tickets t
            LEFT JOIN users u
                ON u.id = t.requester_id
            LEFT JOIN users tech
                ON tech.id = t.technician_id
            ORDER BY t.id DESC
            LIMIT 8
        """).fetchall()

    else:

        total = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE requester_id = ?
        """, (user["id"],)).fetchone()["c"]

        new = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE requester_id = ?
            AND status = 'Nouveau'
        """, (user["id"],)).fetchone()["c"]

        progress = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE requester_id = ?
            AND status = 'En cours'
        """, (user["id"],)).fetchone()["c"]

        resolved = conn.execute("""
            SELECT COUNT(*) c
            FROM tickets
            WHERE requester_id = ?
            AND status IN ('Résolu','Fermé')
        """, (user["id"],)).fetchone()["c"]

        recent = conn.execute("""
            SELECT
                t.*,
                u.full_name requester,
                tech.full_name technician
            FROM tickets t
            LEFT JOIN users u
                ON u.id = t.requester_id
            LEFT JOIN users tech
                ON tech.id = t.technician_id
            WHERE t.requester_id = ?
            ORDER BY t.id DESC
            LIMIT 8
        """, (user["id"],)).fetchall()

    conn.close()

    rows = ""

    for t in recent:

        rows += f"""
        <tr>

            <td>
                <a
                    class="ticket-id"
                    href="{url_for('ticket_detail', ticket_id=t['id'])}">
                    #{t['id']}
                </a>
            </td>

            <td>
                <div class="ticket-title">
                    {t['subject'] or t['title'] or 'Sans objet'}
                </div>

                <div class="muted">
                    {t['category'] or ''}
                </div>
            </td>

            <td>
                {t['requester'] or 'Utilisateur'}
            </td>

            <td>
                <span class="badge {status_class(t['status'])}">
                    {t['status']}
                </span>
            </td>

            <td>
                <span class="{priority_class(t['priority'])}">
                    {t['priority']}
                </span>
            </td>

            <td>
                <a
                    class="btn btn-secondary"
                    href="{url_for('ticket_detail', ticket_id=t['id'])}">
                    Voir
                </a>
            </td>

        </tr>
        """

    extra_admin_html = ""
    if user["role"] == "admin":
        extra_admin_html = f"""<div class="grid grid-3" style="margin-top:18px"><div class="card kpi"><div class="kpi-label">Tickets non assignés</div><div class="kpi-number">{unassigned}</div><div class="kpi-bottom">À prendre en charge</div></div><div class="card kpi"><div class="kpi-label">Équipe IT</div><div class="kpi-number">{it_staff}</div><div class="kpi-bottom">Administrateurs + techniciens</div></div><div class="card kpi"><div class="kpi-label">Utilisateurs</div><div class="kpi-number">{active_users}</div><div class="kpi-bottom">Comptes employés</div></div></div>"""

    content = f"""

    <div class="grid grid-4">

        <div class="card kpi">

            <div class="kpi-label">
                Total tickets
            </div>

            <div class="kpi-number">
                {total}
            </div>

            <div class="kpi-bottom">
                Tous les tickets
            </div>

        </div>

        <div class="card kpi">

            <div class="kpi-label">
                Nouveaux
            </div>

            <div class="kpi-number">
                {new}
            </div>

            <div class="kpi-bottom">
                À traiter
            </div>

        </div>

        <div class="card kpi">

            <div class="kpi-label">
                En cours
            </div>

            <div class="kpi-number">
                {progress}
            </div>

            <div class="kpi-bottom">
                Interventions actives
            </div>

        </div>

        <div class="card kpi">

            <div class="kpi-label">
                Résolus
            </div>

            <div class="kpi-number">
                {resolved}
            </div>

            <div class="kpi-bottom">
                Tickets terminés
            </div>

        </div>

    </div>


    {extra_admin_html}

    <div class="grid grid-2" style="margin-top:18px">

        <div class="card">

            <div style="
                display:flex;
                justify-content:space-between;
                margin-bottom:15px">

                <div>

                    <strong>
                        Activité des tickets
                    </strong>

                    <div class="muted"
                         style="margin-top:5px">
                        Vue globale
                    </div>

                </div>

            </div>

            <canvas id="ticketChart"
                    height="150"></canvas>

        </div>


        <div class="card">

            <strong>
                Répartition des statuts
            </strong>

            <div style="
                max-width:250px;
                margin:20px auto">

                <canvas id="statusChart"></canvas>

            </div>

        </div>

    </div>


    <div class="card" style="margin-top:18px">

        <div style="
            display:flex;
            justify-content:space-between;
            align-items:center;
            margin-bottom:15px">

            <div>

                <strong>
                    Tickets récents
                </strong>

                <div class="muted"
                     style="margin-top:5px">
                    Dernières demandes
                </div>

            </div>

            <a
                class="btn btn-secondary"
                href="{url_for('tickets')}">
                Voir tous
            </a>

        </div>

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>ID</th>
                        <th>Ticket</th>
                        <th>Demandeur</th>
                        <th>Statut</th>
                        <th>Priorité</th>
                        <th></th>
                    </tr>

                </thead>

                <tbody>

                    {rows if rows else '''
                    <tr>
                        <td colspan="6">
                            <div class="empty">
                                Aucun ticket
                            </div>
                        </td>
                    </tr>
                    '''}

                </tbody>

            </table>

        </div>

    </div>


    <script>

    new Chart(
        document.getElementById('ticketChart'),
        {{
            type: 'line',

            data: {{
                labels: ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'],

                datasets: [{{
                    label: 'Tickets',
                    data: [4,7,5,9,6,8,11],
                    tension: .4,
                    fill: true
                }}]
            }},

            options: {{
                responsive:true,
                plugins: {{
                    legend: {{
                        display:false
                    }}
                }}
            }}
        }}
    );


    new Chart(
        document.getElementById('statusChart'),
        {{
            type:'doughnut',

            data:{{
                labels:[
                    'Nouveau',
                    'En cours',
                    'Résolu'
                ],

                datasets:[{{
                    data:[
                        {new},
                        {progress},
                        {resolved}
                    ]
                }}]
            }},

            options:{{
                plugins:{{
                    legend:{{
                        position:'bottom'
                    }}
                }}
            }}
        }}
    );

    </script>
    """

    return render_page(
        content,
        "Dashboard",
        "Vue globale du support informatique"
    )


# ============================================================
# TICKETS LIST
# ============================================================

@app.route("/tickets")
@login_required
def tickets():

    user = current_user()

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()

    conn = db()

    query = """
        SELECT
            t.*,
            u.full_name requester,
            tech.full_name technician
        FROM tickets t
        LEFT JOIN users u
            ON u.id = t.requester_id
        LEFT JOIN users tech
            ON tech.id = t.technician_id
        WHERE 1=1
    """

    params = []

    if user["role"] not in ("admin", "technician"):

        query += """
            AND t.requester_id = ?
        """

        params.append(user["id"])

    if search:

        query += """
            AND (
                t.subject LIKE ?
                OR t.title LIKE ?
                OR t.description LIKE ?
                OR CAST(t.id AS TEXT) LIKE ?
            )
        """

        value = f"%{search}%"

        params.extend([
            value,
            value,
            value,
            value
        ])

    if status:

        query += """
            AND t.status = ?
        """

        params.append(status)

    if priority:

        query += """
            AND t.priority = ?
        """

        params.append(priority)

    query += """
        ORDER BY t.id DESC
    """

    ticket_rows = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    rows = ""

    for t in ticket_rows:

        rows += f"""

        <tr>

            <td>
                <a
                    href="{url_for('ticket_detail', ticket_id=t['id'])}"
                    class="ticket-id">
                    #{t['id']}
                </a>
            </td>

            <td>

                <div class="ticket-title">
                    {t['subject'] or t['title'] or 'Sans objet'}
                </div>

                <div class="muted">
                    {t['category'] or '-'}
                    /
                    {t['subcategory'] or '-'}
                </div>

            </td>

            <td>
                {t['requester'] or '-'}
            </td>

            <td>
                {t['department'] or '-'}
            </td>

            <td>
                {t['service'] or '-'}
            </td>

            <td>
                <span class="badge {status_class(t['status'])}">
                    {t['status']}
                </span>
            </td>

            <td>
                <span class="{priority_class(t['priority'])}">
                    {t['priority']}
                </span>
            </td>

            <td>
                <a
                    href="{url_for('ticket_detail', ticket_id=t['id'])}"
                    class="btn btn-secondary">
                    Ouvrir
                </a>
            </td>

        </tr>
        """

    content = f"""

    <div class="card">

        <form method="GET"
              class="toolbar">

            <input
                name="search"
                value="{search}"
                placeholder="Rechercher ticket, utilisateur, ID...">

            <select name="status">

                <option value="">
                    Tous les statuts
                </option>

                <option {'selected' if status == 'Nouveau' else ''}>
                    Nouveau
                </option>

                <option {'selected' if status == 'En cours' else ''}>
                    En cours
                </option>

                <option {'selected' if status == 'En attente' else ''}>
                    En attente
                </option>

                <option {'selected' if status == 'Résolu' else ''}>
                    Résolu
                </option>

                <option {'selected' if status == 'Fermé' else ''}>
                    Fermé
                </option>

            </select>

            <select name="priority">

                <option value="">
                    Toutes priorités
                </option>

                <option {'selected' if priority == 'Basse' else ''}>
                    Basse
                </option>

                <option {'selected' if priority == 'Moyenne' else ''}>
                    Moyenne
                </option>

                <option {'selected' if priority == 'Haute' else ''}>
                    Haute
                </option>

                <option {'selected' if priority == 'Critique' else ''}>
                    Critique
                </option>

            </select>

            <button class="btn btn-primary">
                Filtrer
            </button>

            <a
                class="btn btn-secondary"
                href="{url_for('tickets')}">
                Reset
            </a>

        </form>


        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>ID</th>
                        <th>Ticket</th>
                        <th>Demandeur</th>
                        <th>Département</th>
                        <th>Service</th>
                        <th>Statut</th>
                        <th>Priorité</th>
                        <th></th>
                    </tr>

                </thead>

                <tbody>

                    {rows if rows else '''
                    <tr>
                        <td colspan="8">
                            <div class="empty">
                                <div class="empty-icon">◌</div>
                                Aucun ticket trouvé
                            </div>
                        </td>
                    </tr>
                    '''}

                </tbody>

            </table>

        </div>

    </div>

    """

    return render_page(
        content,
        "Tickets",
        "Gestion des incidents et demandes IT"
    )


# ============================================================
# NEW TICKET
# ============================================================

@app.route("/tickets/new", methods=["GET", "POST"])
@login_required
def new_ticket():

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        ticket_type = request.form.get(
            "type",
            "Incident"
        )

        category = request.form.get(
            "category",
            ""
        )

        subcategory = request.form.get(
            "subcategory",
            ""
        )

        department = request.form.get(
            "department",
            ""
        )

        service = request.form.get(
            "service",
            ""
        )

        priority = request.form.get(
            "priority",
            "Moyenne"
        )

        location = request.form.get(
            "location",
            ""
        ).strip()

        asset = request.form.get(
            "asset",
            ""
        ).strip()

        if not subject or not description:

            flash(
                "Objet et description obligatoires.",
                "danger"
            )

            return redirect(url_for("new_ticket"))

        conn = db()

        created = now()

        # IMPORTANT:
        # title + subject sont remplis pour compatibilité
        # avec les anciennes versions de la DB.

        cur = conn.execute("""
            INSERT INTO tickets
            (
                requester_id,
                title,
                subject,
                description,
                type,
                category,
                subcategory,
                department,
                service,
                priority,
                status,
                location,
                asset,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            subject,
            subject,
            description,
            ticket_type,
            category,
            subcategory,
            department,
            service,
            priority,
            "Nouveau",
            location,
            asset,
            created,
            created
        ))

        ticket_id = cur.lastrowid

        conn.execute("""
            INSERT INTO activity_logs
            (
                user_id,
                ticket_id,
                action,
                details,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            ticket_id,
            "Création du ticket",
            f"Ticket créé : {subject}",
            created
        ))

        conn.commit()
        conn.close()

        # Notification aux administrateurs et techniciens IT
        create_ticket_notifications(
            ticket_id,
            subject,
            session["user_id"]
        )

        flash(
            f"Ticket #{ticket_id} créé avec succès.",
            "success"
        )

        return redirect(
            url_for(
                "ticket_detail",
                ticket_id=ticket_id
            )
        )

    departments = list(DEPARTMENTS.keys())
    categories = list(CATEGORIES.keys())

    department_options = ""

    for item in departments:

        department_options += f"""
        <option value="{item}">
            {item}
        </option>
        """

    category_options = ""

    for item in categories:

        category_options += f"""
        <option value="{item}">
            {item}
        </option>
        """

    content = f"""

    <div class="card">

        <form method="POST">

            <div class="form-grid">

                <div class="form-group">

                    <label>Type de demande</label>

                    <select name="type">

                        <option>Incident</option>
                        <option>Demande de service</option>
                        <option>Demande d'accès</option>
                        <option>Matériel</option>

                    </select>

                </div>


                <div class="form-group">

                    <label>Priorité</label>

                    <select name="priority">

                        <option>Basse</option>
                        <option selected>Moyenne</option>
                        <option>Haute</option>
                        <option>Critique</option>

                    </select>

                </div>


                <div class="form-group full">

                    <label>Objet du ticket *</label>

                    <input
                        type="text"
                        name="subject"
                        placeholder="Ex : Problème VPN utilisateur"
                        required>

                </div>


                <div class="form-group">

                    <label>Département *</label>

                    <select
                        name="department"
                        id="department"
                        onchange="updateServices()"
                        required>

                        <option value="">
                            Sélectionner
                        </option>

                        {department_options}

                    </select>

                </div>


                <div class="form-group">

                    <label>Service</label>

                    <select
                        name="service"
                        id="service">

                        <option value="">
                            Sélectionner
                        </option>

                    </select>

                </div>


                <div class="form-group">

                    <label>Catégorie</label>

                    <select
                        name="category"
                        id="category"
                        onchange="updateSubcategories()">

                        <option value="">
                            Sélectionner
                        </option>

                        {category_options}

                    </select>

                </div>


                <div class="form-group">

                    <label>Sous-catégorie</label>

                    <select
                        name="subcategory"
                        id="subcategory">

                        <option value="">
                            Sélectionner
                        </option>

                    </select>

                </div>


                <div class="form-group">

                    <label>Localisation</label>

                    <input
                        name="location"
                        placeholder="Ex : Bureau Finance / Étage 2">

                </div>


                <div class="form-group">

                    <label>Matériel / Asset</label>

                    <input
                        name="asset"
                        placeholder="Ex : Dell Vostro / PC-025">

                </div>


                <div class="form-group full">

                    <label>Description du problème *</label>

                    <textarea
                        name="description"
                        placeholder="Décrivez le problème ou la demande..."
                        required></textarea>

                </div>

            </div>


            <div style="
                display:flex;
                justify-content:flex-end;
                gap:10px;
                margin-top:20px">

                <a
                    href="{url_for('tickets')}"
                    class="btn btn-secondary">

                    Annuler

                </a>

                <button
                    class="btn btn-primary">

                    Créer le ticket

                </button>

            </div>

        </form>

    </div>

    """

    return render_page(
        content,
        "Nouveau ticket",
        "Créer une nouvelle demande au service IT"
    )


# ============================================================
# TICKET DETAIL
# ============================================================

@app.route("/ticket/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):

    user = current_user()

    conn = db()

    ticket = conn.execute("""
        SELECT
            t.*,
            u.full_name requester,
            u.email requester_email,
            u.department requester_department,
            u.service requester_service,
            tech.full_name technician
        FROM tickets t
        LEFT JOIN users u
            ON u.id = t.requester_id
        LEFT JOIN users tech
            ON tech.id = t.technician_id
        WHERE t.id = ?
    """, (ticket_id,)).fetchone()

    if not ticket:

        conn.close()

        flash(
            "Ticket introuvable.",
            "danger"
        )

        return redirect(url_for("tickets"))

    # User ne voit que ses tickets
    if user["role"] not in ("admin", "technician"):

        if ticket["requester_id"] != user["id"]:

            conn.close()

            flash(
                "Accès non autorisé.",
                "danger"
            )

            return redirect(url_for("tickets"))

    comments = conn.execute("""
        SELECT
            c.*,
            u.full_name
        FROM comments c
        LEFT JOIN users u
            ON u.id = c.user_id
        WHERE c.ticket_id = ?
        ORDER BY c.id ASC
    """, (ticket_id,)).fetchall()

    logs = conn.execute("""
        SELECT
            l.*,
            u.full_name
        FROM activity_logs l
        LEFT JOIN users u
            ON u.id = l.user_id
        WHERE l.ticket_id = ?
        ORDER BY l.id ASC
    """, (ticket_id,)).fetchall()

    technicians = conn.execute("""
        SELECT id, full_name, role
        FROM users
        WHERE role IN ('admin','technician')
        ORDER BY full_name
    """).fetchall()

    conn.close()

    timeline = ""

    # logs
    for log in logs:

        timeline += f"""

        <div class="timeline-item">

            <div class="timeline-dot"></div>

            <div class="timeline-content">

                <strong>
                    {log['action']}
                </strong>

                <p>
                    {log['details'] or ''}
                </p>

                <div class="timeline-date">
                    {log['full_name'] or 'Système'}
                    ·
                    {log['created_at']}
                </div>

            </div>

        </div>

        """

    # comments
    comments_html = ""

    for c in comments:

        internal = ""

        if c["is_internal"]:

            internal = """
            <span class="badge priority-high">
                INTERNE
            </span>
            """

        comments_html += f"""

        <div class="timeline-item">

            <div class="timeline-dot"></div>

            <div class="timeline-content">

                <strong>
                    {c['full_name'] or 'Utilisateur'}
                    {internal}
                </strong>

                <p>
                    {c['comment'] or ''}
                </p>

                <div class="timeline-date">
                    {c['created_at']}
                </div>

            </div>

        </div>

        """

    tech_options = """

    <option value="">
        Non assigné
    </option>

    """

    for tech in technicians:

        selected = ""

        if ticket["technician_id"] == tech["id"]:
            selected = "selected"

        tech_options += f"""

        <option
            value="{tech['id']}"
            {selected}>

            {tech['full_name']}

        </option>

        """

    admin_panel = ""

    if user["role"] in ("admin", "technician"):

        admin_panel = f"""

        <div class="card" style="margin-top:18px">

            <strong>
                Gestion IT
            </strong>

            <form
                method="POST"
                action="{url_for('update_ticket', ticket_id=ticket_id)}"
                style="margin-top:15px">

                <div class="form-grid">

                    <div class="form-group">

                        <label>Statut</label>

                        <select name="status">

                            <option {'selected' if ticket['status']=='Nouveau' else ''}>
                                Nouveau
                            </option>

                            <option {'selected' if ticket['status']=='En cours' else ''}>
                                En cours
                            </option>

                            <option {'selected' if ticket['status']=='En attente' else ''}>
                                En attente
                            </option>

                            <option {'selected' if ticket['status']=='Résolu' else ''}>
                                Résolu
                            </option>

                            <option {'selected' if ticket['status']=='Fermé' else ''}>
                                Fermé
                            </option>

                        </select>

                    </div>


                    <div class="form-group">

                        <label>Technicien responsable</label>

                        <select name="technician_id">

                            {tech_options}

                        </select>

                    </div>


                    <div class="form-group full">

                        <label>
                            Résolution / Intervention
                        </label>

                        <textarea
                            name="resolution"
                            placeholder="Décrire ce qui a été fait pour résoudre le problème...">{ticket['resolution'] or ''}</textarea>

                    </div>

                </div>

                <button
                    class="btn btn-primary"
                    style="margin-top:15px">

                    Enregistrer l'intervention

                </button>

            </form>

        </div>

        """

    content = f"""

    <div class="detail-grid">

        <div>

            <div class="card">

                <div class="ticket-header">

                    <div>

                        <div class="ticket-id">
                            TICKET #{ticket['id']}
                        </div>

                        <h2 style="margin-top:7px">
                            {ticket['subject'] or ticket['title'] or 'Sans objet'}
                        </h2>

                        <p>
                            Créé le {ticket['created_at']}
                        </p>

                    </div>

                    <span class="badge {status_class(ticket['status'])}">
                        {ticket['status']}
                    </span>

                </div>


                <div class="meta-grid">

                    <div class="meta">

                        <small>
                            DEMANDEUR
                        </small>

                        <strong>
                            {ticket['requester'] or '-'}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            PRIORITÉ
                        </small>

                        <strong class="{priority_class(ticket['priority'])}">
                            {ticket['priority']}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            DÉPARTEMENT
                        </small>

                        <strong>
                            {ticket['department'] or '-'}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            SERVICE
                        </small>

                        <strong>
                            {ticket['service'] or '-'}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            CATÉGORIE
                        </small>

                        <strong>
                            {ticket['category'] or '-'}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            SOUS-CATÉGORIE
                        </small>

                        <strong>
                            {ticket['subcategory'] or '-'}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            LOCALISATION
                        </small>

                        <strong>
                            {ticket['location'] or '-'}
                        </strong>

                    </div>


                    <div class="meta">

                        <small>
                            ASSET / MATÉRIEL
                        </small>

                        <strong>
                            {ticket['asset'] or '-'}
                        </strong>

                    </div>

                </div>


                <div class="description">

                    <strong style="color:white">
                        Description
                    </strong>

                    <br><br>

                    {ticket['description'] or 'Aucune description.'}

                </div>

            </div>


            {admin_panel}


            <div class="card" style="margin-top:18px">

                <strong>
                    Ajouter un commentaire
                </strong>

                <form
                    method="POST"
                    action="{url_for('add_comment', ticket_id=ticket_id)}"
                    style="margin-top:15px">

                    <textarea
                        name="comment"
                        placeholder="Écrire un commentaire ou une mise à jour..."
                        required></textarea>

                    <button
                        class="btn btn-primary"
                        style="margin-top:10px">

                        Ajouter

                    </button>

                </form>

            </div>


            <div class="card" style="margin-top:18px">

                <strong>
                    Activité & interventions
                </strong>

                <div class="timeline">

                    {timeline}

                    {comments_html}

                    {'''
                    <div class="empty">
                        Aucune activité.
                    </div>
                    ''' if not timeline and not comments_html else ''}

                </div>

            </div>

        </div>


        <div>

            <div class="card">

                <strong>
                    Informations demandeur
                </strong>

                <div style="margin-top:18px">

                    <div class="meta">

                        <small>
                            NOM
                        </small>

                        <strong>
                            {ticket['requester'] or '-'}
                        </strong>

                    </div>

                    <div class="meta" style="margin-top:10px">

                        <small>
                            EMAIL
                        </small>

                        <strong>
                            {ticket['requester_email'] or '-'}
                        </strong>

                    </div>

                    <div class="meta" style="margin-top:10px">

                        <small>
                            DÉPARTEMENT
                        </small>

                        <strong>
                            {ticket['requester_department'] or '-'}
                        </strong>

                    </div>

                    <div class="meta" style="margin-top:10px">

                        <small>
                            SERVICE
                        </small>

                        <strong>
                            {ticket['requester_service'] or '-'}
                        </strong>

                    </div>

                </div>

            </div>


            <div class="card" style="margin-top:18px">

                <strong>
                    Technicien
                </strong>

                <div style="
                    margin-top:15px;
                    padding:14px;
                    background:rgba(255,255,255,.03);
                    border-radius:12px">

                    {ticket['technician'] or 'Non assigné'}

                </div>

            </div>

        </div>

    </div>

    """

    return render_page(
        content,
        f"Ticket #{ticket_id}",
        "Détails et suivi de l'intervention"
    )


# ============================================================
# UPDATE TICKET
# ============================================================

@app.route("/ticket/<int:ticket_id>/update", methods=["POST"])
@admin_required
def update_ticket(ticket_id):

    status = request.form.get(
        "status",
        "Nouveau"
    )

    technician_id = request.form.get(
        "technician_id"
    )

    resolution = request.form.get(
        "resolution",
        ""
    ).strip()

    if technician_id == "":
        technician_id = None

    conn = db()

    old = conn.execute("""
        SELECT *
        FROM tickets
        WHERE id = ?
    """, (ticket_id,)).fetchone()

    if not old:

        conn.close()

        flash(
            "Ticket introuvable.",
            "danger"
        )

        return redirect(url_for("tickets"))

    conn.execute("""
        UPDATE tickets
        SET
            status = ?,
            technician_id = ?,
            resolution = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        status,
        technician_id,
        resolution,
        now(),
        ticket_id
    ))

    current = current_user()

    details = f"Statut: {status}"

    if technician_id:
        tech = conn.execute("""
            SELECT full_name
            FROM users
            WHERE id = ?
        """, (technician_id,)).fetchone()

        if tech:
            details += f" | Technicien: {tech['full_name']}"

    if resolution:
        details += " | Intervention / résolution mise à jour"

    conn.execute("""
        INSERT INTO activity_logs
        (
            user_id,
            ticket_id,
            action,
            details,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        current["id"],
        ticket_id,
        "Mise à jour du ticket",
        details,
        now()
    ))

    conn.commit()
    conn.close()

    flash(
        "Ticket mis à jour.",
        "success"
    )

    return redirect(
        url_for(
            "ticket_detail",
            ticket_id=ticket_id
        )
    )


# ============================================================
# TAKE TICKET IN CHARGE
# ============================================================

@app.route("/ticket/<int:ticket_id>/take", methods=["POST"])
@admin_required
def take_ticket(ticket_id):

    user = current_user()

    conn = db()

    ticket = conn.execute("""
        SELECT id
        FROM tickets
        WHERE id = ?
    """, (ticket_id,)).fetchone()

    if not ticket:

        conn.close()

        flash(
            "Ticket introuvable.",
            "danger"
        )

        return redirect(url_for("tickets"))

    conn.execute("""
        UPDATE tickets
        SET
            technician_id = ?,
            status = 'En cours',
            updated_at = ?
        WHERE id = ?
    """, (
        user["id"],
        now(),
        ticket_id
    ))

    conn.execute("""
        INSERT INTO activity_logs
        (
            user_id,
            ticket_id,
            action,
            details,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user["id"],
        ticket_id,
        "Prise en charge",
        f"Ticket pris en charge par {user['full_name']}",
        now()
    ))

    conn.commit()
    conn.close()

    flash(
        "Ticket pris en charge.",
        "success"
    )

    return redirect(
        url_for(
            "ticket_detail",
            ticket_id=ticket_id
        )
    )


# ============================================================
# COMMENT
# ============================================================

@app.route("/ticket/<int:ticket_id>/comment", methods=["POST"])
@login_required
def add_comment(ticket_id):

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    if not comment:

        flash(
            "Commentaire vide.",
            "warning"
        )

        return redirect(
            url_for(
                "ticket_detail",
                ticket_id=ticket_id
            )
        )

    user = current_user()

    conn = db()

    ticket = conn.execute("""
        SELECT *
        FROM tickets
        WHERE id = ?
    """, (ticket_id,)).fetchone()

    if not ticket:

        conn.close()

        flash(
            "Ticket introuvable.",
            "danger"
        )

        return redirect(url_for("tickets"))

    if user["role"] not in ("admin", "technician"):

        if ticket["requester_id"] != user["id"]:

            conn.close()

            flash(
                "Accès non autorisé.",
                "danger"
            )

            return redirect(url_for("tickets"))

    conn.execute("""
        INSERT INTO comments
        (
            ticket_id,
            user_id,
            comment,
            is_internal,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        ticket_id,
        user["id"],
        comment,
        0,
        now()
    ))

    conn.execute("""
        INSERT INTO activity_logs
        (
            user_id,
            ticket_id,
            action,
            details,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user["id"],
        ticket_id,
        "Commentaire ajouté",
        comment[:250],
        now()
    ))

    conn.execute("""
        UPDATE tickets
        SET updated_at = ?
        WHERE id = ?
    """, (
        now(),
        ticket_id
    ))

    conn.commit()
    conn.close()

    flash(
        "Commentaire ajouté.",
        "success"
    )

    return redirect(
        url_for(
            "ticket_detail",
            ticket_id=ticket_id
        )
    )


# ============================================================
# USERS
# ============================================================

@app.route("/users")
@admin_only_required
def users():
    conn = db()
    users_rows = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    conn.close()

    rows = ""
    for u in users_rows:
        role_label = {"admin":"Administrateur","technician":"Technicien IT","user":"Utilisateur"}.get(u["role"], u["role"])
        enabled = bool(u["notifications_enabled"] if "notifications_enabled" in u.keys() else 1)
        badge = "status-resolved" if enabled else "status-closed"
        nlabel = "Activées" if enabled else "Désactivées"
        tlabel = "Désactiver" if enabled else "Activer"
        delete_html = ""
        if u["id"] != session.get("user_id"):
            delete_html = (
                '<form method="POST" action="' + url_for("delete_user", user_id=u["id"]) + '" onsubmit="return confirm(\'Supprimer ce compte ? Les tickets seront conservés.\');">'
                '<button class="btn btn-danger" style="padding:7px 9px;font-size:10px">Supprimer</button></form>'
            )
        rows += f"""
        <tr>
            <td><div style="display:flex;align-items:center;gap:10px"><div class="avatar">{(u['full_name'] or 'U')[0].upper()}</div><div><strong>{u['full_name'] or '-'}</strong><div class="muted">@{u['username']}</div></div></div></td>
            <td>{u['email'] or '-'}</td><td>{u['department'] or '-'}</td><td>{u['service'] or '-'}</td>
            <td><span class="badge status-new">{role_label}</span></td>
            <td><span class="badge {badge}">{nlabel}</span></td>
            <td><div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                <form method="POST" action="{url_for('toggle_user_notifications', user_id=u['id'])}"><button class="btn btn-secondary" style="padding:7px 9px;font-size:10px">{tlabel}</button></form>
                <form method="POST" action="{url_for('reset_user_password', user_id=u['id'])}" style="display:flex;gap:5px"><input name="password" type="password" placeholder="Nouveau mot de passe" required style="width:145px;padding:7px 9px"><button class="btn btn-warning" style="padding:7px 9px;font-size:10px">Changer</button></form>
                {delete_html}
            </div></td>
            <td>{u['created_at'] or '-'}</td>
        </tr>
        """

    content = f"""
    <div class="card" style="margin-bottom:18px"><div style="display:flex;justify-content:space-between;align-items:center;gap:15px;flex-wrap:wrap"><div><strong>Administration des comptes</strong><div class="muted" style="margin-top:5px">Créer, supprimer, changer les mots de passe et gérer les notifications.</div></div><span class="badge status-resolved">Accès Administrateur</span></div></div>
    <div class="grid grid-2">
        <div class="card"><strong>Créer un utilisateur</strong><form method="POST" action="{url_for('create_user')}" style="margin-top:18px">
            <div class="form-group"><label>Nom complet</label><input name="full_name" required></div>
            <div class="form-group"><label>Username</label><input name="username" required></div>
            <div class="form-group"><label>Email</label><input type="email" name="email"></div>
            <div class="form-group"><label>Mot de passe</label><input type="password" name="password" required></div>
            <div class="form-group"><label>Département</label><select name="department" id="department" onchange="updateServices()"><option value="">Sélectionner</option>{''.join(f'<option value="{d}">{d}</option>' for d in DEPARTMENTS)}</select></div>
            <div class="form-group"><label>Service</label><select name="service" id="service"><option value="">Sélectionner</option></select></div>
            <div class="form-group"><label>Rôle</label><select name="role"><option value="user">Utilisateur</option><option value="technician">Technicien IT</option><option value="admin">Administrateur</option></select></div>
            <button class="btn btn-primary" style="margin-top:10px">Créer le compte</button>
        </form></div>
        <div class="card"><strong>Utilisateurs</strong><div class="table-wrap" style="margin-top:15px"><table><thead><tr><th>Utilisateur</th><th>Email</th><th>Département</th><th>Service</th><th>Rôle</th><th>Notifications</th><th>Actions</th><th>Créé</th></tr></thead><tbody>{rows}</tbody></table></div></div>
    </div>
    """
    return render_page(content, "Utilisateurs", "Gestion des comptes et des accès")


@app.route("/users/create", methods=["POST"])
@admin_only_required
def create_user():

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    username = request.form.get(
        "username",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    department = request.form.get(
        "department",
        ""
    )

    service = request.form.get(
        "service",
        ""
    )

    role = request.form.get(
        "role",
        "user"
    )

    if not full_name or not username or not password:

        flash(
            "Nom, username et mot de passe obligatoires.",
            "danger"
        )

        return redirect(url_for("users"))

    conn = db()

    try:

        conn.execute("""
            INSERT INTO users
            (
                username,
                password,
                full_name,
                email,
                department,
                service,
                role,
                notifications_enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            username,
            generate_password_hash(password),
            full_name,
            email,
            department,
            service,
            role,
            1,
            now()
        ))

        conn.commit()

        flash(
            "Utilisateur créé avec succès.",
            "success"
        )

    except sqlite3.IntegrityError:

        flash(
            "Ce username existe déjà.",
            "danger"
        )

    finally:

        conn.close()

    return redirect(url_for("users"))


# ============================================================
# ADMIN USER MANAGEMENT ACTIONS
# ============================================================

@app.route("/users/<int:user_id>/notifications", methods=["POST"])
@admin_only_required
def toggle_user_notifications(user_id):
    conn = db()
    row = conn.execute("SELECT id, notifications_enabled FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        conn.close(); flash("Utilisateur introuvable.", "danger"); return redirect(url_for("users"))
    value = 0 if (row["notifications_enabled"] or 0) else 1
    conn.execute("UPDATE users SET notifications_enabled = ? WHERE id = ?", (value, user_id))
    conn.commit(); conn.close()
    flash("Notifications activées." if value else "Notifications désactivées.", "success")
    return redirect(url_for("users"))

@app.route("/users/<int:user_id>/password", methods=["POST"])
@admin_only_required
def reset_user_password(user_id):
    password = request.form.get("password", "")
    if len(password) < 6:
        flash("Le mot de passe doit contenir au moins 6 caractères.", "danger"); return redirect(url_for("users"))
    conn = db(); row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        conn.close(); flash("Utilisateur introuvable.", "danger"); return redirect(url_for("users"))
    conn.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(password), user_id))
    conn.commit(); conn.close(); flash("Mot de passe modifié avec succès.", "success")
    return redirect(url_for("users"))

@app.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_only_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("Vous ne pouvez pas supprimer votre propre compte administrateur.", "danger"); return redirect(url_for("users"))
    conn = db(); row = conn.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        conn.close(); flash("Utilisateur introuvable.", "danger"); return redirect(url_for("users"))
    if row["role"] == "admin" and conn.execute("SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()["c"] <= 1:
        conn.close(); flash("Impossible de supprimer le dernier administrateur.", "danger"); return redirect(url_for("users"))
    conn.execute("UPDATE tickets SET requester_id = NULL WHERE requester_id = ?", (user_id,))
    conn.execute("UPDATE tickets SET technician_id = NULL WHERE technician_id = ?", (user_id,))
    conn.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM comments WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM activity_logs WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit(); conn.close(); flash("Compte supprimé. Les tickets ont été conservés.", "success")
    return redirect(url_for("users"))


# ============================================================
# STATISTICS
# ============================================================

@app.route("/statistics")
@admin_required
def statistics():

    conn = db()

    total = conn.execute("""
        SELECT COUNT(*) c FROM tickets
    """).fetchone()["c"]

    status_rows = conn.execute("""
        SELECT status, COUNT(*) total
        FROM tickets
        GROUP BY status
        ORDER BY total DESC
    """).fetchall()

    category_rows = conn.execute("""
        SELECT category, COUNT(*) total
        FROM tickets
        GROUP BY category
        ORDER BY total DESC
        LIMIT 10
    """).fetchall()

    department_rows = conn.execute("""
        SELECT department, COUNT(*) total
        FROM tickets
        GROUP BY department
        ORDER BY total DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    status_labels = [
        r["status"] or "Autre"
        for r in status_rows
    ]

    status_values = [
        r["total"]
        for r in status_rows
    ]

    category_labels = [
        r["category"] or "Autre"
        for r in category_rows
    ]

    category_values = [
        r["total"]
        for r in category_rows
    ]

    department_labels = [
        r["department"] or "Autre"
        for r in department_rows
    ]

    department_values = [
        r["total"]
        for r in department_rows
    ]

    import json

    content = f"""

    <div class="grid grid-3">

        <div class="card kpi">

            <div class="kpi-label">
                Total tickets
            </div>

            <div class="kpi-number">
                {total}
            </div>

        </div>

        <div class="card">

            <div class="kpi-label">
                Catégories
            </div>

            <div class="kpi-number">
                {len(category_rows)}
            </div>

        </div>

        <div class="card">

            <div class="kpi-label">
                Départements concernés
            </div>

            <div class="kpi-number">
                {len(department_rows)}
            </div>

        </div>

    </div>


    <div class="grid grid-2" style="margin-top:18px">

        <div class="card">

            <strong>
                Tickets par statut
            </strong>

            <div style="margin-top:20px">

                <canvas id="statusChart"></canvas>

            </div>

        </div>


        <div class="card">

            <strong>
                Tickets par catégorie
            </strong>

            <div style="margin-top:20px">

                <canvas id="categoryChart"></canvas>

            </div>

        </div>

    </div>


    <div class="card" style="margin-top:18px">

        <strong>
            Tickets par département
        </strong>

        <div style="margin-top:20px">

            <canvas id="departmentChart"
                    height="100"></canvas>

        </div>

    </div>


    <script>

    new Chart(
        document.getElementById('statusChart'),
        {{
            type:'doughnut',

            data:{{
                labels:{json.dumps(status_labels, ensure_ascii=False)},
                datasets:[{{
                    data:{json.dumps(status_values)}
                }}]
            }},

            options:{{
                plugins:{{
                    legend:{{
                        position:'bottom'
                    }}
                }}
            }}
        }}
    );


    new Chart(
        document.getElementById('categoryChart'),
        {{
            type:'bar',

            data:{{
                labels:{json.dumps(category_labels, ensure_ascii=False)},
                datasets:[{{
                    data:{json.dumps(category_values)}
                }}]
            }},

            options:{{
                plugins:{{
                    legend:{{
                        display:false
                    }}
                }}
            }}
        }}
    );


    new Chart(
        document.getElementById('departmentChart'),
        {{
            type:'bar',

            data:{{
                labels:{json.dumps(department_labels, ensure_ascii=False)},
                datasets:[{{
                    data:{json.dumps(department_values)}
                }}]
            }},

            options:{{
                indexAxis:'y',
                plugins:{{
                    legend:{{
                        display:false
                    }}
                }}
            }}
        }}
    );

    </script>

    """

    return render_page(
        content,
        "Statistiques",
        "Analyse de l'activité du support IT"
    )


# ============================================================
# HISTORY
# ============================================================

@app.route("/history")
@admin_required
def history():

    conn = db()

    logs = conn.execute("""
        SELECT
            l.*,
            u.full_name,
            t.subject,
            t.title
        FROM activity_logs l
        LEFT JOIN users u
            ON u.id = l.user_id
        LEFT JOIN tickets t
            ON t.id = l.ticket_id
        ORDER BY l.id DESC
        LIMIT 200
    """).fetchall()

    conn.close()

    rows = ""

    for log in logs:

        subject = (
            log["subject"]
            or log["title"]
            or "-"
        )

        rows += f"""

        <tr>

            <td>
                {log['created_at']}
            </td>

            <td>
                {log['full_name'] or 'Système'}
            </td>

            <td>

                {(
                    f'<a class="ticket-id" href="{url_for("ticket_detail", ticket_id=log["ticket_id"])}">#{log["ticket_id"]}</a>'
                    if log["ticket_id"]
                    else "-"
                )}

            </td>

            <td>
                <strong>
                    {log['action']}
                </strong>

                <div class="muted">
                    {subject}
                </div>

            </td>

            <td>
                {log['details'] or '-'}
            </td>

        </tr>

        """

    content = f"""

    <div class="card">

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>Date</th>
                        <th>Utilisateur</th>
                        <th>Ticket</th>
                        <th>Action</th>
                        <th>Détails</th>
                    </tr>

                </thead>

                <tbody>

                    {rows if rows else '''
                    <tr>
                        <td colspan="5">
                            <div class="empty">
                                Aucun historique
                            </div>
                        </td>
                    </tr>
                    '''}

                </tbody>

            </table>

        </div>

    </div>

    """

    return render_page(
        content,
        "Historique",
        "Traçabilité des actions et interventions"
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    user = current_user()

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        department = request.form.get(
            "department",
            ""
        )

        service = request.form.get(
            "service",
            ""
        )

        new_password = request.form.get(
            "password",
            ""
        )

        conn = db()

        if new_password:

            conn.execute("""
                UPDATE users
                SET
                    full_name = ?,
                    email = ?,
                    department = ?,
                    service = ?,
                    password = ?
                WHERE id = ?
            """, (
                full_name,
                email,
                department,
                service,
                generate_password_hash(new_password),
                user["id"]
            ))

        else:

            conn.execute("""
                UPDATE users
                SET
                    full_name = ?,
                    email = ?,
                    department = ?,
                    service = ?
                WHERE id = ?
            """, (
                full_name,
                email,
                department,
                service,
                user["id"]
            ))

        conn.commit()
        conn.close()

        flash(
            "Profil mis à jour.",
            "success"
        )

        return redirect(url_for("profile"))

    department_options = ""

    for d in DEPARTMENTS:

        selected = ""

        if user["department"] == d:
            selected = "selected"

        department_options += f"""
        <option value="{d}" {selected}>
            {d}
        </option>
        """

    content = f"""

    <div class="card"
         style="max-width:800px">

        <form method="POST">

            <div class="form-grid">

                <div class="form-group">

                    <label>Username</label>

                    <input
                        value="{user['username']}"
                        disabled>

                </div>


                <div class="form-group">

                    <label>Rôle</label>

                    <input
                        value="{user['role']}"
                        disabled>

                </div>


                <div class="form-group">

                    <label>Nom complet</label>

                    <input
                        name="full_name"
                        value="{user['full_name'] or ''}"
                        required>

                </div>


                <div class="form-group">

                    <label>Email</label>

                    <input
                        type="email"
                        name="email"
                        value="{user['email'] or ''}">

                </div>


                <div class="form-group">

                    <label>Département</label>

                    <select
                        name="department"
                        id="department"
                        onchange="updateServices()">

                        <option value="">
                            Sélectionner
                        </option>

                        {department_options}

                    </select>

                </div>


                <div class="form-group">

                    <label>Service</label>

                    <select
                        name="service"
                        id="service">

                        <option value="">
                            {user['service'] or 'Sélectionner'}
                        </option>

                    </select>

                </div>


                <div class="form-group full">

                    <label>
                        Nouveau mot de passe
                    </label>

                    <input
                        type="password"
                        name="password"
                        placeholder="Laisser vide pour ne pas changer">

                </div>

            </div>


            <button
                class="btn btn-primary"
                style="margin-top:15px">

                Enregistrer

            </button>

        </form>

    </div>

    """

    return render_page(
        content,
        "Mon profil",
        "Gérer vos informations personnelles"
    )


# ============================================================
# NOTIFICATIONS API
# ============================================================

@app.route('/api/notifications')
@login_required
def api_notifications():
    user = current_user()
    if user['role'] not in ('admin', 'technician'):
        return {'notifications': [], 'unread_count': 0}

    conn = db()
    rows = conn.execute("""
        SELECT id, ticket_id, title, message, is_read, created_at
        FROM notifications
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 30
    """, (user['id'],)).fetchall()
    unread = conn.execute("""
        SELECT COUNT(*) c FROM notifications
        WHERE user_id = ? AND is_read = 0
    """, (user['id'],)).fetchone()['c']
    conn.close()

    return {
        'notifications': [dict(r) for r in rows],
        'unread_count': unread
    }


@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def notification_read(notification_id):
    conn = db()
    conn.execute("""
        UPDATE notifications SET is_read = 1
        WHERE id = ? AND user_id = ?
    """, (notification_id, session['user_id']))
    conn.commit()
    conn.close()
    return {'ok': True}


@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def notifications_read_all():
    conn = db()
    conn.execute("""
        UPDATE notifications SET is_read = 1
        WHERE user_id = ?
    """, (session['user_id'],))
    conn.commit()
    conn.close()
    return {'ok': True}


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    if "user_id" in session:

        content = """

        <div class="card">

            <div class="empty">

                <div class="empty-icon">
                    404
                </div>

                <strong>
                    Page introuvable
                </strong>

                <p>
                    La page demandée n'existe pas.
                </p>

                <a
                    href="/"
                    class="btn btn-primary">

                    Retour dashboard

                </a>

            </div>

        </div>

        """

        return render_page(
            content,
            "Page introuvable",
            "Erreur 404"
        ), 404

    return redirect(url_for("login"))


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    init_db()

    print("")
    print("==============================================")
    print(" ALMABAT IT HELPDESK")
    print("==============================================")
    print("")
    print(" Local : http://127.0.0.1:5000")
    print(" Réseau: http://0.0.0.0:5000")
    print("")
    print(" Authentification : utilisez votre compte Helpdesk")
    print("")
    print("==============================================")
    print("")

    # Désactive le reloader Flask pour éviter plusieurs processus
    # qui peuvent verrouiller SQLite.
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )