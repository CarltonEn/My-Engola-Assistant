from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.db import remember
from core.security import require_owner

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.post("")
async def add_memory(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    b = await request.json()
    key = (b.get("key") or "").strip()
    value = (b.get("value") or "").strip()
    if not key or not value:
        return JSONResponse({"error": "key and value required"}, status_code=400)
    remember(key, value)
    return {"ok": True}


@router.get("")
def list_memory(request: Request):
    denied = require_owner(request)
    if denied: return denied
    from core.db import db
    c=db(); rows=c.execute("SELECT id,key,value,ts FROM memories ORDER BY id DESC").fetchall(); c.close()
    return {"memories":[{"id":r[0],"key":r[1],"value":r[2],"ts":r[3]} for r in rows]}

@router.delete("/{memory_id}")
def delete_memory(memory_id:int, request: Request):
    denied = require_owner(request)
    if denied: return denied
    from core.db import db
    c=db(); cur=c.execute("DELETE FROM memories WHERE id=?",(memory_id,)); c.commit(); c.close()
    if not cur.rowcount: return JSONResponse({"error":"Memory not found"}, status_code=404)
    return {"ok":True}
