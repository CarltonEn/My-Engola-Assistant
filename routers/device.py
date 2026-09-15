import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.device import claim_pairing, create_pairing, heartbeat, list_devices
from core.security import require_owner

router = APIRouter(prefix="/api/device", tags=["device"])


def _token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return request.headers.get("x-engola-device-token", "").strip()


@router.post("/pair")
def pair(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    return create_pairing()


@router.post("/pair/claim")
async def pair_claim(request: Request):
    body = await request.json()
    code = str(body.get("code") or "")
    name = str(body.get("name") or "Android device")
    platform = str(body.get("platform") or "android")
    if len(code) != 8:
        return JSONResponse({"error": "Invalid pairing code."}, status_code=400)
    result = claim_pairing(code, name, platform)
    if not result:
        return JSONResponse({"error": "Pairing code is invalid or expired."}, status_code=401)
    return result


@router.post("/heartbeat")
async def device_heartbeat(request: Request):
    token = _token(request)
    if not token or len(token) < 20:
        return JSONResponse({"error": "Device authentication required."}, status_code=401)
    body = await request.json()
    result = heartbeat(token, body if isinstance(body, dict) else {})
    if not result:
        return JSONResponse({"error": "Unknown device token."}, status_code=401)
    return result


@router.get("")
def devices(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    return {"devices": list_devices()}
