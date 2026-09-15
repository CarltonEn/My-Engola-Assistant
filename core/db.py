"""
SQLite persistence layer.

This preserves the exact schema and helper behavior from the v0.5 canonical
single-file app.py, plus additive tables for the career module and Uganda
knowledge registry. No existing table, column or behavior was removed or
changed.
"""
import sqlite3
import time

from core.config import DB_PATH


def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.execute(
        "CREATE TABLE IF NOT EXISTS messages("
        "id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts REAL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS memories("
        "id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, ts REAL)"
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS owner_credentials(
        id INTEGER PRIMARY KEY, credential_id TEXT UNIQUE NOT NULL,
        public_key BLOB NOT NULL, sign_count INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS webauthn_challenges(
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, challenge BLOB NOT NULL,
        created_at REAL NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS sessions(
        token_hash TEXT PRIMARY KEY, created_at REAL NOT NULL,
        last_seen REAL NOT NULL, expires_at REAL NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS permissions(
        name TEXT PRIMARY KEY, status TEXT NOT NULL, scope TEXT NOT NULL,
        updated_at REAL NOT NULL)"""
    )
    # Additive: career module
    c.execute(
        """CREATE TABLE IF NOT EXISTS career_opportunities(
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, company TEXT,
        url TEXT, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
        score REAL, score_breakdown TEXT, created_at REAL NOT NULL,
        updated_at REAL NOT NULL)"""
    )
    # Additive: lightweight work/task system
    c.execute(
        """CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, notes TEXT,
        status TEXT NOT NULL DEFAULT 'todo', priority TEXT NOT NULL DEFAULT 'normal',
        due_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL)"""
    )

    # Additive: v0.11 private knowledge vault
    c.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_sources(
        id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
        kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
        metadata TEXT NOT NULL DEFAULT '{}', text TEXT NOT NULL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL)"""
    )

    # Additive: Google OAuth token storage (owner-only, single row)
    c.execute(
        """CREATE TABLE IF NOT EXISTS google_tokens(
        id INTEGER PRIMARY KEY CHECK (id = 1), access_token TEXT,
        refresh_token TEXT, scope TEXT, expires_at REAL, updated_at REAL)"""
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS device_pairings(
        id INTEGER PRIMARY KEY, code_hash TEXT UNIQUE NOT NULL,
        created_at REAL NOT NULL, expires_at REAL NOT NULL, used_at REAL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS devices(
        device_id TEXT PRIMARY KEY, name TEXT NOT NULL, platform TEXT NOT NULL,
        model TEXT, android_version TEXT, battery_pct REAL, charging INTEGER DEFAULT 0,
        network_type TEXT, network_name TEXT, storage_free INTEGER, storage_total INTEGER,
        capabilities TEXT, token_hash TEXT UNIQUE NOT NULL, created_at REAL NOT NULL,
        last_seen REAL, status TEXT NOT NULL DEFAULT 'offline')"""
    )

    # Additive: chief-of-staff project / decision / reminder state.
    c.execute(
        """CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, goal TEXT,
        status TEXT NOT NULL DEFAULT 'active', priority TEXT NOT NULL DEFAULT 'normal',
        created_at REAL NOT NULL, updated_at REAL NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS decisions(
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, rationale TEXT,
        status TEXT NOT NULL DEFAULT 'active', created_at REAL NOT NULL, updated_at REAL NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS reminders(
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_at REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL, updated_at REAL NOT NULL)"""
    )
    # Additive: safe owner recovery state. Tokens are never stored in plaintext.
    c.execute(
        """CREATE TABLE IF NOT EXISTS recovery_attempts(
        key_hash TEXT PRIMARY KEY, window_started REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS recovery_state(
        id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL, recovery_cookie_hash TEXT UNIQUE NOT NULL,
        created_at REAL NOT NULL, expires_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        last_attempt_at REAL, used_at REAL)"""
    )
    defaults = [
        ("phone", "ask", "contacts, files, camera, microphone, notifications"),
        ("computer", "ask", "files, apps, browser, local automation"),
        ("cloud", "ask", "Drive/OneDrive/Dropbox and connected storage"),
        ("email", "ask", "read/search; send requires approval"),
        ("calendar", "ask", "read/write after permission"),
        ("linkedin", "ask", "profile and approved job-search data"),
        ("github", "ask", "repositories and development workflows"),
        ("financial", "deny", "banking/payment actions remain locked by default"),
        ("career_submission", "deny", "submitting applications on the owner's behalf"),
    ]
    for row in defaults:
        c.execute(
            "INSERT OR IGNORE INTO permissions(name,status,scope,updated_at) VALUES(?,?,?,?)",
            (*row, time.time()),
        )
    c.commit()
    return c


def recent(limit: int = 30):
    c = db()
    rows = c.execute(
        "SELECT role,content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return list(reversed(rows))


def memory_text(limit: int = 150) -> str:
    c = db()
    rows = c.execute(
        "SELECT key,value FROM memories ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return "\n".join(f"- {k}: {v}" for k, v in rows)


def save_message(role: str, content: str):
    c = db()
    c.execute(
        "INSERT INTO messages(role,content,ts) VALUES(?,?,?)",
        (role, content, time.time()),
    )
    c.commit()
    c.close()


def remember(key: str, value: str):
    c = db()
    c.execute(
        "INSERT INTO memories(key,value,ts) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,ts=excluded.ts",
        (key, value, time.time()),
    )
    c.commit()
    c.close()


def has_owner() -> bool:
    c = db()
    n = c.execute("SELECT COUNT(*) FROM owner_credentials").fetchone()[0]
    c.close()
    return n > 0


def credential_count() -> int:
    c = db()
    n = c.execute("SELECT COUNT(*) FROM owner_credentials").fetchone()[0]
    c.close()
    return n
