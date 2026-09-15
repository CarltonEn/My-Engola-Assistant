"""
Session and WebAuthn support helpers.

Behavior preserved exactly from the v0.5 canonical single-file app.py:
- rp_id()/origin() fall back to request host only when not explicitly
  configured via environment variables.
- Sessions are opaque random tokens; only a SHA-256 hash is stored.
- Idle timeout and absolute expiry are both enforced.
"""
import hashlib
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from core import config
from core.db import db

try:
    from webauthn import base64url_to_bytes  # noqa: F401 (re-exported for routers)

    WEBAUTHN_OK = True
except Exception:
    WEBAUTHN_OK = False


def rp_id(request: Request) -> str:
    if config.WEBAUTHN_RP_ID:
        return config.WEBAUTHN_RP_ID
    host = request.headers.get("host", "").split(":")[0]
    return "localhost" if host in ("", "localhost", "127.0.0.1") else host


def origin(request: Request) -> str:
    if config.WEBAUTHN_ORIGIN:
        return config.WEBAUTHN_ORIGIN.rstrip("/")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    return f"{scheme}://{request.headers.get('host', request.url.hostname)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_owner(request: Request) -> bool:
    token = request.cookies.get(config.SESSION_COOKIE)
    if not token:
        return False
    now = time.time()
    h = hash_token(token)
    c = db()
    row = c.execute(
        "SELECT last_seen,expires_at FROM sessions WHERE token_hash=?", (h,)
    ).fetchone()
    if not row or row[1] < now or row[0] + config.IDLE_TTL < now:
        if row:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (h,))
            c.commit()
        c.close()
        return False
    c.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, h))
    c.commit()
    c.close()
    return True


def require_owner(request: Request):
    """Returns a JSONResponse (401) if not authenticated, else None."""
    if not current_owner(request):
        return JSONResponse({"error": "Owner authentication required."}, status_code=401)
    return None


def save_challenge(kind: str, challenge: bytes):
    c = db()
    c.execute(
        "INSERT INTO webauthn_challenges(kind,challenge,created_at) VALUES(?,?,?)",
        (kind, challenge, time.time()),
    )
    c.commit()
    c.close()


def take_challenge(kind: str):
    c = db()
    row = c.execute(
        "SELECT id,challenge,created_at FROM webauthn_challenges WHERE kind=? ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()
    if not row:
        c.close()
        return None
    c.execute("DELETE FROM webauthn_challenges WHERE id=?", (row[0],))
    c.commit()
    c.close()
    if time.time() - row[2] > 600:
        return None
    return row[1]


def create_session(response):
    token = secrets.token_urlsafe(48)
    now = time.time()
    c = db()
    c.execute(
        "INSERT INTO sessions(token_hash,created_at,last_seen,expires_at) VALUES(?,?,?,?)",
        (hash_token(token), now, now, now + config.SESSION_TTL),
    )
    c.commit()
    c.close()
    response.set_cookie(
        config.SESSION_COOKIE,
        token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        max_age=config.SESSION_TTL,
        path="/",
    )
