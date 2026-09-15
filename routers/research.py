import html,re,urllib.parse,urllib.request
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from core.security import require_owner
router=APIRouter(prefix='/api/research',tags=['research'])
@router.get('/search')
def search(request:Request,q:str=''):
 d=require_owner(request)
 if d:return d
 if not q.strip():return JSONResponse({'ok':False,'error':'q is required'},400)
 try:
  req=urllib.request.Request('https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':q.strip()}),headers={'User-Agent':'Engola/1.0'})
  with urllib.request.urlopen(req,timeout=15) as r:t=r.read().decode('utf-8','replace')
  out=[]
  for block in re.findall(r'<div class="result__body".*?</div>\s*</div>',t,re.S):
   a=re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',block,re.S);sn=re.search(r'class="result__snippet"[^>]*>(.*?)</a?>',block,re.S)
   if a:out.append({'title':html.unescape(re.sub('<.*?>','',a.group(2))),'url':html.unescape(a.group(1)),'snippet':html.unescape(re.sub(r'\s+',' ',re.sub('<.*?>','',sn.group(1) if sn else '')))})
  return {'ok':True,'query':q,'results':out[:10]}
 except Exception as e:return JSONResponse({'ok':False,'error':f'Research failed: {e}'},502)
