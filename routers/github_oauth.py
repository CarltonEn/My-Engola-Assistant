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

router = APIRouter(prefix="/api/github", tags=["github"])
AUTH_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
_pending_states = {}

def _configured():
    return bool(getattr(config, "GITHUB_CLIENT_ID", "") and getattr(config, "GITHUB_CLIENT_SECRET", "") and getattr(config, "GITHUB_REDIRECT_URI", ""))

def _ensure():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS github_tokens (
            id INTEGER PRIMARY KEY CHECK(id=1),
            access_token TEXT NOT NULL,
            scope TEXT,
            updated_at REAL NOT NULL
        )""")

@router.get("/status")
def status(request: Request):
    denied = require_owner(request)
    if denied: return denied
    _ensure()
    with db() as conn:
        row = conn.execute("SELECT scope FROM github_tokens WHERE id=1").fetchone()
    return {"configured": _configured(), "connected": bool(row), "scope": row[0] if row else None}

@router.get("/authorize")
def authorize(request: Request):
    denied = require_owner(request)
    if denied: return denied
    if not _configured():
        return JSONResponse({"ok": False, "error": "GitHub OAuth is not configured on the server. Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET and GITHUB_REDIRECT_URI."}, status_code=503)
    state = secrets.token_urlsafe(24)
    _pending_states[state] = time.time()
    for s, ts in list(_pending_states.items()):
        if time.time() - ts > 600: _pending_states.pop(s, None)
    params = {"client_id": config.GITHUB_CLIENT_ID, "redirect_uri": config.GITHUB_REDIRECT_URI, "scope": getattr(config, "GITHUB_SCOPES", "repo read:user"), "state": state, "allow_signup": "false"}
    return RedirectResponse(AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params))

@router.get("/callback")
def callback(request: Request, code: str = None, state: str = None, error: str = None):
    denied = require_owner(request)
    if denied: return denied
    if error: return JSONResponse({"ok": False, "error": f"GitHub returned an error: {error}"}, status_code=400)
    if not _configured(): return JSONResponse({"ok": False, "error": "GitHub OAuth is not configured on the server."}, status_code=503)
    if not code or not state or state not in _pending_states:
        return JSONResponse({"ok": False, "error": "Missing or invalid OAuth state/code. Start the flow again."}, status_code=400)
    _pending_states.pop(state, None)
    payload = urllib.parse.urlencode({"client_id": config.GITHUB_CLIENT_ID, "client_secret": config.GITHUB_CLIENT_SECRET, "code": code, "redirect_uri": config.GITHUB_REDIRECT_URI}).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=payload, headers={"Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r: data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"GitHub token exchange failed: {type(e).__name__}: {e}"}, status_code=502)
    token = data.get("access_token")
    if not token: return JSONResponse({"ok": False, "error": "GitHub did not return an access token."}, status_code=502)
    _ensure()
    with db() as conn:
        conn.execute("INSERT INTO github_tokens(id,access_token,scope,updated_at) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET access_token=excluded.access_token,scope=excluded.scope,updated_at=excluded.updated_at", (token, data.get("scope", getattr(config, "GITHUB_SCOPES", "")), time.time()))
    return RedirectResponse("/?github=connected")

@router.post("/disconnect")
def disconnect(request: Request):
    denied = require_owner(request)
    if denied: return denied
    _ensure()
    with db() as conn: conn.execute("DELETE FROM github_tokens WHERE id=1")
    return {"ok": True, "connected": False}
