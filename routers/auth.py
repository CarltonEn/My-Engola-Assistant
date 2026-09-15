"""
Owner authentication router (WebAuthn/passkey).

This is a direct migration of the auth endpoints from the v0.5 canonical
single-file app.py into its own router. The verification logic, error
messages and status codes are unchanged. No biometric template is ever
received or stored by the server -- only the WebAuthn public key credential
(a cryptographic assertion), consistent with OWNER-IDENTITY.md.
"""
import json
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config
from core.db import db, has_owner
from core.security import (
    create_session,
    hash_token,
    origin,
    rp_id,
    save_challenge,
    take_challenge,
)

try:
    from webauthn import (
        base64url_to_bytes,
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        AuthenticatorAttachment,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    WEBAUTHN_OK = True
except Exception:
    WEBAUTHN_OK = False

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(request: Request):
    from core.security import current_owner

    return {
        "authenticated": current_owner(request),
        "owner": config.OWNER_NAME,
        "setup_required": not has_owner(),
        "webauthn_available": WEBAUTHN_OK,
    }


@router.post("/setup/options")
async def setup_options(request: Request):
    if not WEBAUTHN_OK:
        return JSONResponse({"error": "WebAuthn server library is not installed."}, status_code=500)
    if has_owner():
        return JSONResponse({"error": "Owner passkey is already registered."}, status_code=409)
    body = await request.json()
    token = (body.get("setup_token") or "").strip()
    expected = config.ENGOLA_SETUP_TOKEN
    if not expected or not secrets.compare_digest(token, expected):
        return JSONResponse({"error": "Invalid owner setup authorization."}, status_code=403)
    options = generate_registration_options(
        rp_id=rp_id(request),
        rp_name=config.RP_NAME,
        user_id=secrets.token_bytes(32),
        user_name=config.OWNER_NAME,
        user_display_name=config.OWNER_NAME,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    save_challenge("registration", options.challenge)
    return json.loads(options_to_json(options))


@router.post("/setup/verify")
async def setup_verify(request: Request):
    if not WEBAUTHN_OK:
        return JSONResponse({"error": "WebAuthn server library is not installed."}, status_code=500)
    if has_owner():
        return JSONResponse({"error": "Owner passkey is already registered."}, status_code=409)
    body = await request.json()
    token = (body.pop("setup_token", "") or "").strip()
    expected = config.ENGOLA_SETUP_TOKEN
    if not expected or not secrets.compare_digest(token, expected):
        return JSONResponse({"error": "Invalid owner setup authorization."}, status_code=403)
    challenge = take_challenge("registration")
    if not challenge:
        return JSONResponse({"error": "Registration challenge expired. Start again."}, status_code=400)
    try:
        verification = verify_registration_response(
            credential=body,
            expected_challenge=challenge,
            expected_rp_id=rp_id(request),
            expected_origin=origin(request),
        )
        c = db()
        c.execute(
            "INSERT INTO owner_credentials(credential_id,public_key,sign_count,created_at) VALUES(?,?,?,?)",
            (
                verification.credential_id.hex(),
                verification.credential_public_key,
                verification.sign_count,
                __import__("time").time(),
            ),
        )
        c.commit()
        c.close()
        response = JSONResponse({"ok": True, "owner": config.OWNER_NAME})
        create_session(response)
        return response
    except Exception as e:
        return JSONResponse({"error": f"Passkey registration failed: {type(e).__name__}"}, status_code=400)


@router.post("/login/options")
def login_options(request: Request):
    if not WEBAUTHN_OK:
        return JSONResponse({"error": "WebAuthn server library is not installed."}, status_code=500)
    if not has_owner():
        return JSONResponse({"error": "Owner setup is required first."}, status_code=409)
    c = db()
    ids = [base64url_to_bytes(r[0]) for r in c.execute("SELECT credential_id FROM owner_credentials").fetchall()]
    c.close()
    options = generate_authentication_options(
        rp_id=rp_id(request),
        allow_credentials=[PublicKeyCredentialDescriptor(id=i) for i in ids],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    save_challenge("authentication", options.challenge)
    return json.loads(options_to_json(options))


@router.post("/login/verify")
async def login_verify(request: Request):
    if not WEBAUTHN_OK:
        return JSONResponse({"error": "WebAuthn server library is not installed."}, status_code=500)
    body = await request.json()
    challenge = take_challenge("authentication")
    if not challenge:
        return JSONResponse({"error": "Authentication challenge expired. Start again."}, status_code=400)
    try:
        credential_id = (body.get("id") or "").strip()
        c = db()
        row = c.execute(
            "SELECT public_key,sign_count FROM owner_credentials WHERE credential_id=?", (credential_id,)
        ).fetchone()
        c.close()
        if not row:
            return JSONResponse({"error": "Unknown owner credential."}, status_code=403)
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=challenge,
            expected_rp_id=rp_id(request),
            expected_origin=origin(request),
            credential_public_key=row[0],
            credential_current_sign_count=row[1],
        )
        c = db()
        c.execute(
            "UPDATE owner_credentials SET sign_count=? WHERE credential_id=?",
            (verification.new_sign_count, credential_id),
        )
        c.commit()
        c.close()
        response = JSONResponse({"ok": True, "owner": config.OWNER_NAME})
        create_session(response)
        return response
    except Exception as e:
        return JSONResponse({"error": f"Passkey authentication failed: {type(e).__name__}"}, status_code=403)




RECOVERY_WINDOW = 300
RECOVERY_MAX_ATTEMPTS = 5


def _recovery_rate_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hash_token("recovery-rate:" + host)


def _recovery_rate_limited(request: Request) -> bool:
    now = __import__("time").time()
    key = _recovery_rate_key(request)
    with db() as c:
        row = c.execute("SELECT window_started, attempts FROM recovery_attempts WHERE key_hash=?", (key,)).fetchone()
        if not row or now - row[0] >= RECOVERY_WINDOW:
            c.execute("INSERT OR REPLACE INTO recovery_attempts(key_hash,window_started,attempts) VALUES(?,?,0)", (key, now))
            c.commit()
            return False
        return row[1] >= RECOVERY_MAX_ATTEMPTS


def _record_recovery_attempt(request: Request) -> None:
    now = __import__("time").time()
    key = _recovery_rate_key(request)
    with db() as c:
        row = c.execute("SELECT window_started, attempts FROM recovery_attempts WHERE key_hash=?", (key,)).fetchone()
        if not row or now - row[0] >= RECOVERY_WINDOW:
            c.execute("INSERT OR REPLACE INTO recovery_attempts(key_hash,window_started,attempts) VALUES(?,?,1)", (key, now))
        else:
            c.execute("UPDATE recovery_attempts SET attempts=attempts+1 WHERE key_hash=?", (key,))
        c.commit()


def _recovery_state(request: Request):
    token = request.cookies.get(config.RECOVERY_COOKIE)
    if not token:
        return None
    now = __import__("time").time()
    with db() as c:
        row = c.execute("SELECT id, expires_at, attempts, used_at FROM recovery_state WHERE recovery_cookie_hash=?", (hash_token(token),)).fetchone()
    if not row or row[1] < now or row[3] is not None:
        return None
    return row


def _recovery_challenge_kind(request: Request) -> str | None:
    token = request.cookies.get(config.RECOVERY_COOKIE)
    return "recovery:" + hash_token(token) if token else None


@router.post("/recovery/start")
async def recovery_start(request: Request):
    if not has_owner():
        return JSONResponse({"error": "Owner setup is required before recovery is available."}, status_code=409)
    if _recovery_rate_limited(request):
        return JSONResponse({"error": "Recovery is rate-limited. Try again later."}, status_code=429)
    body = await request.json()
    supplied = (body.get("recovery_token") or "").strip()
    expected = config.ENGOLA_RECOVERY_TOKEN
    _record_recovery_attempt(request)
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        return JSONResponse({"error": "Invalid recovery authorization."}, status_code=403)
    now = __import__("time").time()
    recovery_secret = secrets.token_urlsafe(48)
    with db() as c:
        c.execute("DELETE FROM recovery_state WHERE used_at IS NOT NULL OR expires_at < ?", (now,))
        c.execute("INSERT INTO recovery_state(token_hash,recovery_cookie_hash,created_at,expires_at,attempts,last_attempt_at,used_at) VALUES(?,?,?,?,0,NULL,NULL)",
                  (hash_token(supplied), hash_token(recovery_secret), now, now + config.RECOVERY_TTL))
        c.commit()
    response = JSONResponse({"ok": True, "expires_in": config.RECOVERY_TTL})
    response.set_cookie(config.RECOVERY_COOKIE, recovery_secret, httponly=True, secure=config.COOKIE_SECURE, samesite="strict", max_age=config.RECOVERY_TTL, path="/")
    return response


@router.post("/recovery/register/options")
def recovery_register_options(request: Request):
    if not WEBAUTHN_OK:
        return JSONResponse({"error": "WebAuthn server library is not installed."}, status_code=500)
    state = _recovery_state(request)
    if not state:
        return JSONResponse({"error": "Recovery authorization is missing or expired. Start recovery again."}, status_code=403)
    options = generate_registration_options(
        rp_id=rp_id(request), rp_name=config.RP_NAME, user_id=secrets.token_bytes(32),
        user_name=config.OWNER_NAME, user_display_name=config.OWNER_NAME,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    kind = _recovery_challenge_kind(request)
    save_challenge(kind, options.challenge)
    return json.loads(options_to_json(options))


@router.post("/recovery/register/verify")
async def recovery_register_verify(request: Request):
    if not WEBAUTHN_OK:
        return JSONResponse({"error": "WebAuthn server library is not installed."}, status_code=500)
    state = _recovery_state(request)
    if not state:
        return JSONResponse({"error": "Recovery authorization is missing or expired. Start recovery again."}, status_code=403)
    if state[2] >= RECOVERY_MAX_ATTEMPTS:
        return JSONResponse({"error": "Too many recovery attempts. Start recovery again later."}, status_code=429)
    kind = _recovery_challenge_kind(request)
    challenge = take_challenge(kind) if kind else None
    if not challenge:
        return JSONResponse({"error": "Recovery registration challenge expired. Start again."}, status_code=400)
    with db() as c:
        c.execute("UPDATE recovery_state SET attempts=attempts+1,last_attempt_at=? WHERE id=?", (__import__("time").time(), state[0]))
        c.commit()
    body = await request.json()
    try:
        verification = verify_registration_response(
            credential=body, expected_challenge=challenge,
            expected_rp_id=rp_id(request), expected_origin=origin(request),
        )
        credential_id = verification.credential_id.hex()
        now = __import__("time").time()
        with db() as c:
            if c.execute("SELECT 1 FROM owner_credentials WHERE credential_id=?", (credential_id,)).fetchone():
                return JSONResponse({"error": "That credential is already registered."}, status_code=409)
            c.execute("INSERT INTO owner_credentials(credential_id,public_key,sign_count,created_at) VALUES(?,?,?,?)",
                      (credential_id, verification.credential_public_key, verification.sign_count, now))
            c.execute("UPDATE recovery_state SET used_at=? WHERE id=?", (now, state[0]))
            c.commit()
        response = JSONResponse({"ok": True, "owner": config.OWNER_NAME})
        response.delete_cookie(config.RECOVERY_COOKIE, path="/")
        create_session(response)
        return response
    except Exception as exc:
        return JSONResponse({"error": f"Recovery registration failed: {type(exc).__name__}"}, status_code=400)

@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(config.SESSION_COOKIE)
    if token:
        c = db()
        c.execute("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))
        c.commit()
        c.close()
    response = JSONResponse({"ok": True})
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return response
