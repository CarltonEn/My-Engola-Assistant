from fastapi import APIRouter

from core import ai, config
from core.db import has_owner
from routers.auth import WEBAUTHN_OK

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/health")
def health():
    return {
        "ok": True,
        "engola": "ready",
        "version": config.APP_VERSION,
        "owner_only": True,
        "owner_registered": has_owner(),
        "openai_configured": ai.is_configured(),
        "webauthn_available": WEBAUTHN_OK,
    }
