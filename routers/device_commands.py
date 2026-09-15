from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.command_bridge import complete, poll, queue_command, recent
from core.security import require_owner

router = APIRouter(prefix="/api/device/commands", tags=["device-commands"])


def _token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-engola-device-token", "").strip()


@router.post("")
async def create(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    body = await request.json()
    try:
        return queue_command(
            str(body.get("device_id") or ""),
            str(body.get("kind") or ""),
            body.get("payload") if isinstance(body.get("payload"), dict) else {},
            bool(body.get("confirm")),
            str(body.get("idempotency_key") or "").strip() or None,
        )
    except (ValueError, TypeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.get("")
def list_commands(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    return {"ok": True, "commands": recent()}


@router.post("/poll")
async def device_poll(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "Device authentication required."}, status_code=401)
    body = await request.json()
    try:
        result = poll(token, int(body.get("limit", 3)))
    except Exception as exc:
        return JSONResponse({"error": f"Command polling failed: {type(exc).__name__}: {exc}"}, status_code=500)
    if result is None:
        return JSONResponse({"error": "Unknown device token."}, status_code=401)
    return {"ok": True, "commands": result}


@router.post("/complete")
async def device_complete(request: Request):
    token = _token(request)
    if not token:
        return JSONResponse({"error": "Device authentication required."}, status_code=401)
    body = await request.json()
    try:
        result = complete(
            token,
            str(body.get("command_id") or ""),
            str(body.get("status") or ""),
            body.get("result") if isinstance(body.get("result"), dict) else {},
        )
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if result is None:
        return JSONResponse({"error": "Unknown device token or command."}, status_code=401)
    return result
