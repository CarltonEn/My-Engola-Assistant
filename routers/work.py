import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from core.db import db
from core.security import require_owner

router = APIRouter(prefix="/api/work", tags=["work"])
VALID_STATUS = {"todo", "doing", "done"}
VALID_PRIORITY = {"low", "normal", "high"}

def _task(r):
    return {"id":r[0],"title":r[1],"notes":r[2],"status":r[3],"priority":r[4],"due_at":r[5],"created_at":r[6],"updated_at":r[7]}

@router.get("/tasks")
def list_tasks(request: Request):
    denied=require_owner(request)
    if denied:return denied
    c=db(); rows=c.execute("SELECT id,title,notes,status,priority,due_at,created_at,updated_at FROM tasks ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, COALESCE(due_at,9999999999), id DESC").fetchall(); c.close()
    return {"tasks":[_task(r) for r in rows]}

@router.post("/tasks")
async def create_task(request: Request):
    denied=require_owner(request)
    if denied:return denied
    b=await request.json(); title=(b.get("title") or "").strip()
    if not title:return JSONResponse({"error":"title is required"},status_code=400)
    status=(b.get("status") or "todo").strip(); priority=(b.get("priority") or "normal").strip()
    if status not in VALID_STATUS:return JSONResponse({"error":"invalid status"},status_code=400)
    if priority not in VALID_PRIORITY:return JSONResponse({"error":"invalid priority"},status_code=400)
    notes=(b.get("notes") or "").strip(); due=b.get("due_at")
    try: due=float(due) if due not in (None,"") else None
    except: return JSONResponse({"error":"due_at must be a timestamp or null"},status_code=400)
    now=time.time(); c=db(); cur=c.execute("INSERT INTO tasks(title,notes,status,priority,due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(title,notes,status,priority,due,now,now)); tid=cur.lastrowid; c.commit(); c.close()
    return {"task":{"id":tid,"title":title,"notes":notes,"status":status,"priority":priority,"due_at":due,"created_at":now,"updated_at":now}}

@router.patch("/tasks/{task_id}")
async def update_task(task_id:int, request:Request):
    denied=require_owner(request)
    if denied:return denied
    b=await request.json(); fields=[]; vals=[]
    for k in ("title","notes","status","priority","due_at"):
        if k in b:
            v=b[k]
            if k in ("title","notes","status","priority"): v=(v or "").strip()
            if k=="status" and v not in VALID_STATUS:return JSONResponse({"error":"invalid status"},status_code=400)
            if k=="priority" and v not in VALID_PRIORITY:return JSONResponse({"error":"invalid priority"},status_code=400)
            if k=="title" and not v:return JSONResponse({"error":"title cannot be empty"},status_code=400)
            if k=="due_at":
                try:v=float(v) if v not in (None,"") else None
                except:return JSONResponse({"error":"due_at must be a timestamp or null"},status_code=400)
            fields.append(f"{k}=?"); vals.append(v)
    if not fields:return JSONResponse({"error":"no changes supplied"},status_code=400)
    fields.append("updated_at=?"); vals.append(time.time()); vals.append(task_id)
    c=db(); cur=c.execute(f"UPDATE tasks SET {','.join(fields)} WHERE id=?",vals); c.commit(); row=c.execute("SELECT id,title,notes,status,priority,due_at,created_at,updated_at FROM tasks WHERE id=?",(task_id,)).fetchone(); c.close()
    if not row:return JSONResponse({"error":"Task not found"},status_code=404)
    return {"task":_task(row)}

@router.delete("/tasks/{task_id}")
def delete_task(task_id:int, request:Request):
    denied=require_owner(request)
    if denied:return denied
    c=db(); cur=c.execute("DELETE FROM tasks WHERE id=?",(task_id,)); c.commit(); c.close()
    if not cur.rowcount:return JSONResponse({"error":"Task not found"},status_code=404)
    return {"ok":True}
