"""
Google OAuth 2.0 scaffolding.

Implements the real authorization-code flow (via stdlib urllib, no extra
dependency) so that it actually works once the owner supplies real
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI values --
but every endpoint fails honestly and explicitly (503, clear message) when
those are not configured, rather than pretending to succeed. Per
GOOGLE-INTEGRATION.md and the security rules: no fake integrations, no
default/placeholder client secret is ever accepted as real.
"""
import json
import secrets
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core import config
from core.db import db
from core.security import require_owner

router = APIRouter(prefix="/api/google", tags=["google"])

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

_pending_states = {}  # in-memory CSRF state -> created_at (short-lived, single process)


def _configured() -> bool:
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET and config.GOOGLE_REDIRECT_URI)


@router.get("/status")
def google_status(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    c = db()
    row = c.execute("SELECT expires_at FROM google_tokens WHERE id=1").fetchone()
    c.close()
    connected = bool(row and row[0] and row[0] > time.time())
    return {
        "configured": _configured(),
        "connected": connected,
        "scopes": config.GOOGLE_SCOPES if _configured() else None,
    }


@router.get("/authorize")
def google_authorize(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    if not _configured():
        return JSONResponse(
            {
                "error": "Google OAuth is not configured on the server. Set GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI to enable this."
            },
            status_code=503,
        )
    state = secrets.token_urlsafe(24)
    _pending_states[state] = time.time()
    # prune old states (10 min)
    for s, ts in list(_pending_states.items()):
        if time.time() - ts > 600:
            _pending_states.pop(s, None)
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": config.GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params))


@router.get("/callback")
def google_callback(request: Request, code: str = None, state: str = None, error: str = None):
    denied = require_owner(request)
    if denied:
        return denied
    if error:
        return JSONResponse({"error": f"Google returned an error: {error}"}, status_code=400)
    if not _configured():
        return JSONResponse({"error": "Google OAuth is not configured on the server."}, status_code=503)
    if not code or not state or state not in _pending_states:
        return JSONResponse({"error": "Missing or invalid state/code. Start the flow again at /api/google/authorize."}, status_code=400)
    _pending_states.pop(state, None)

    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            token_data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return JSONResponse({"error": f"Token exchange failed: {type(e).__name__}: {e}"}, status_code=502)

    if "access_token" not in token_data:
        return JSONResponse({"error": "Google did not return an access token.", "details": token_data}, status_code=502)

    expires_at = time.time() + int(token_data.get("expires_in", 3600))
    c = db()
    c.execute(
        "INSERT INTO google_tokens(id,access_token,refresh_token,scope,expires_at,updated_at) "
        "VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "access_token=excluded.access_token,"
        "refresh_token=COALESCE(excluded.refresh_token, google_tokens.refresh_token),"
        "scope=excluded.scope, expires_at=excluded.expires_at, updated_at=excluded.updated_at",
        (
            token_data.get("access_token"),
            token_data.get("refresh_token"),
            token_data.get("scope", config.GOOGLE_SCOPES),
            expires_at,
            time.time(),
        ),
    )
    c.commit()
    c.close()
    return {"ok": True, "connected": True}


@router.post("/disconnect")
def google_disconnect(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    c = db()
    c.execute("DELETE FROM google_tokens WHERE id=1")
    c.commit()
    c.close()
    return {"ok": True, "connected": False}
