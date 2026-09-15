import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.db import db
from core.security import require_owner

router = APIRouter(prefix="/api/permissions", tags=["permissions"])

VALID_STATUSES = {"allow", "ask", "deny"}


@router.get("")
def permissions(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    c = db()
    rows = [
        {"name": r[0], "status": r[1], "scope": r[2]}
        for r in c.execute("SELECT name,status,scope FROM permissions ORDER BY name")
    ]
    c.close()
    return {"permissions": rows}


@router.post("")
async def update_permission(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    b = await request.json()
    name = (b.get("name") or "").strip()
    status = (b.get("status") or "").strip()
    if status not in VALID_STATUSES:
        return JSONResponse({"error": "status must be allow, ask or deny"}, status_code=400)
    c = db()
    row = c.execute("SELECT scope FROM permissions WHERE name=?", (name,)).fetchone()
    if not row:
        c.close()
        return JSONResponse({"error": "Unknown permission scope."}, status_code=404)
    c.execute(
        "UPDATE permissions SET status=?,updated_at=? WHERE name=?",
        (status, time.time(), name),
    )
    c.commit()
    c.close()
    return {"ok": True}
