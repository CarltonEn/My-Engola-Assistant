import time
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from core.db import db
from core.security import require_owner
router=APIRouter(prefix='/api/executive',tags=['executive'])
def has(c,n):return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())
@router.get('/overview')
def overview(request:Request):
 d=require_owner(request)
 if d:return d
 with db() as c:
  tasks=[];mem=[];msgs=[]
  if has(c,'tasks'):tasks=[dict(zip(['id','title','notes','status','priority','due_at','created_at','updated_at'],r)) for r in c.execute('SELECT id,title,notes,status,priority,due_at,created_at,updated_at FROM tasks ORDER BY created_at DESC').fetchall()]
  if has(c,'memories'):mem=[dict(zip(['id','key','value','ts'],r)) for r in c.execute('SELECT id,key,value,ts FROM memories ORDER BY id DESC LIMIT 100').fetchall()]
  if has(c,'messages'):msgs=[dict(zip(['role','content','ts'],r)) for r in reversed(c.execute('SELECT role,content,ts FROM messages ORDER BY id DESC LIMIT 30').fetchall())]
  kc=c.execute('SELECT COUNT(*) FROM knowledge_sources').fetchone()[0] if has(c,'knowledge_sources') else 0
  dc=c.execute('SELECT COUNT(*) FROM devices').fetchone()[0] if has(c,'devices') else 0
  cc={r[0]:r[1] for r in c.execute('SELECT status,COUNT(*) FROM device_commands GROUP BY status').fetchall()} if has(c,'device_commands') else {}
 out=[t for t in tasks if t['status']!='done'];hi=[t for t in out if t['priority']=='high'];act=[t for t in out if t['status']=='doing']
 return {'ok':True,'now':time.time(),'tasks':tasks,'memories':mem,'messages':msgs,'knowledge_count':kc,'device_count':dc,'command_counts':cc,'summary':{'outstanding':len(out),'high_priority':len(hi),'active':len(act)}}
@router.post('/tasks/{task_id}/complete')
def complete_task(task_id:int,request:Request):
 d=require_owner(request)
 if d:return d
 with db() as c:
  cur=c.execute("UPDATE tasks SET status='done',updated_at=? WHERE id=?",(time.time(),task_id));c.commit()
  if cur.rowcount==0:return JSONResponse({'ok':False,'error':'Task not found'},404)
 return {'ok':True,'task_id':task_id,'status':'done','verified':True}
