import json,secrets,time,urllib.parse,urllib.request
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse,RedirectResponse
from core import config
from core.db import db
from core.security import require_owner
from core.integration_clients import ensure_tables,save_state,take_state,google_api,github_api
router=APIRouter(prefix='/api/integrations',tags=['integrations'])
def _cg():return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET and config.GOOGLE_REDIRECT_URI)
def _ch():return bool(config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET and config.GITHUB_REDIRECT_URI)
def _ok(request):return str(request.query_params.get('confirm','')).lower() in {'1','true','yes'}
@router.get('/status')
def status(request:Request):
    d=require_owner(request)
    if d:return d
    ensure_tables()
    with db() as c:g=c.execute('SELECT scope,expires_at FROM google_tokens WHERE id=1').fetchone();h=c.execute('SELECT scope FROM github_tokens WHERE id=1').fetchone()
    return {'ok':True,'google':{'configured':_cg(),'connected':bool(g),'token_valid':bool(g and g[1] and g[1]>time.time()),'scope':g[0] if g else None,'redirect_uri':config.GOOGLE_REDIRECT_URI or None},'github':{'configured':_ch(),'connected':bool(h),'scope':h[0] if h else None,'redirect_uri':config.GITHUB_REDIRECT_URI or None},'archive':__import__('core.archive',fromlist=['status']).status()}
@router.get('/google/authorize')
def google_authorize(request:Request):
    d=require_owner(request)
    if d:return d
    if not _cg():return JSONResponse({'ok':False,'error':'Google OAuth is not configured on the server.'},503)
    state=secrets.token_urlsafe(32);save_state('google',state)
    q=urllib.parse.urlencode({'client_id':config.GOOGLE_CLIENT_ID,'redirect_uri':config.GOOGLE_REDIRECT_URI,'response_type':'code','scope':(config.GOOGLE_SCOPES + ' https://www.googleapis.com/auth/gmail.readonly') if 'https://www.googleapis.com/auth/gmail.readonly' not in config.GOOGLE_SCOPES else config.GOOGLE_SCOPES,'access_type':'offline','prompt':'consent','state':state})
    return RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+q)
@router.get('/google/callback')
def google_callback(request:Request,code:str=None,state:str=None,error:str=None):
    d=require_owner(request)
    if d:return d
    if error:return RedirectResponse('/?integration_error='+urllib.parse.quote('Google: '+error))
    if not code or not state or not take_state('google',state):return RedirectResponse('/?integration_error=Google%20OAuth%20state%20expired')
    data=urllib.parse.urlencode({'code':code,'client_id':config.GOOGLE_CLIENT_ID,'client_secret':config.GOOGLE_CLIENT_SECRET,'redirect_uri':config.GOOGLE_REDIRECT_URI,'grant_type':'authorization_code'}).encode()
    try:
        req=urllib.request.Request('https://oauth2.googleapis.com/token',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with urllib.request.urlopen(req,timeout=15) as r:tok=json.loads(r.read().decode())
    except Exception as e:return RedirectResponse('/?integration_error='+urllib.parse.quote('Google token exchange failed: '+str(e)))
    if 'access_token' not in tok:return RedirectResponse('/?integration_error=Google%20did%20not%20return%20an%20access%20token')
    ensure_tables()
    with db() as c:c.execute('INSERT INTO google_tokens(id,access_token,refresh_token,scope,expires_at,updated_at) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET access_token=excluded.access_token,refresh_token=COALESCE(excluded.refresh_token,google_tokens.refresh_token),scope=excluded.scope,expires_at=excluded.expires_at,updated_at=excluded.updated_at',(tok['access_token'],tok.get('refresh_token'),tok.get('scope',config.GOOGLE_SCOPES),time.time()+int(tok.get('expires_in',3600)),time.time()));c.commit()
    return RedirectResponse('/?google=connected')
@router.get('/github/authorize')
def github_authorize(request:Request):
    d=require_owner(request)
    if d:return d
    if not _ch():return JSONResponse({'ok':False,'error':'GitHub OAuth is not configured on the server.'},503)
    state=secrets.token_urlsafe(32);save_state('github',state)
    q=urllib.parse.urlencode({'client_id':config.GITHUB_CLIENT_ID,'redirect_uri':config.GITHUB_REDIRECT_URI,'scope':config.GITHUB_SCOPES,'state':state})
    return RedirectResponse('https://github.com/login/oauth/authorize?'+q)
@router.get('/github/callback')
def github_callback(request:Request,code:str=None,state:str=None,error:str=None):
    d=require_owner(request)
    if d:return d
    if error:return RedirectResponse('/?integration_error='+urllib.parse.quote('GitHub: '+error))
    if not code or not state or not take_state('github',state):return RedirectResponse('/?integration_error=GitHub%20OAuth%20state%20expired')
    data=urllib.parse.urlencode({'client_id':config.GITHUB_CLIENT_ID,'client_secret':config.GITHUB_CLIENT_SECRET,'code':code,'redirect_uri':config.GITHUB_REDIRECT_URI}).encode()
    try:
        req=urllib.request.Request('https://github.com/login/oauth/access_token',data=data,headers={'Accept':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=15) as r:tok=json.loads(r.read().decode())
    except Exception as e:return RedirectResponse('/?integration_error='+urllib.parse.quote('GitHub token exchange failed: '+str(e)))
    if 'access_token' not in tok:return RedirectResponse('/?integration_error=GitHub%20did%20not%20return%20an%20access%20token')
    ensure_tables()
    with db() as c:c.execute('INSERT INTO github_tokens(id,access_token,scope,updated_at) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET access_token=excluded.access_token,scope=excluded.scope,updated_at=excluded.updated_at',(tok['access_token'],tok.get('scope',config.GITHUB_SCOPES),time.time()));c.commit()
    return RedirectResponse('/?github=connected')
@router.api_route('/google/disconnect', methods=['GET', 'POST'])
def google_disconnect(request:Request):
    d=require_owner(request)
    if d:return d
    ensure_tables()
    with db() as c:
        c.execute('DELETE FROM google_tokens WHERE id=1'); c.commit()
    return RedirectResponse('/?google=disconnected')

@router.api_route('/github/disconnect', methods=['GET', 'POST'])
def github_disconnect(request:Request):
    d=require_owner(request)
    if d:return d
    ensure_tables()
    with db() as c:
        c.execute('DELETE FROM github_tokens WHERE id=1'); c.commit()
    return RedirectResponse('/?github=disconnected')

@router.get('/diagnostics')
def diagnostics(request:Request):
    d=require_owner(request)
    if d:return d
    ensure_tables()
    with db() as c:
        g=c.execute('SELECT scope,expires_at FROM google_tokens WHERE id=1').fetchone()
        h=c.execute('SELECT scope FROM github_tokens WHERE id=1').fetchone()
    return {'ok':True,'google':{'configured':_cg(),'connected':bool(g),'token_valid':bool(g and g[1] and g[1]>time.time()),'redirect_uri':config.GOOGLE_REDIRECT_URI or None,'scope':g[0] if g else None,'required_scopes':config.GOOGLE_SCOPES},'github':{'configured':_ch(),'connected':bool(h),'redirect_uri':config.GITHUB_REDIRECT_URI or None,'scope':h[0] if h else None,'required_scopes':config.GITHUB_SCOPES}}

@router.get('/google/calendar')
def calendar(request:Request,days:int=7):
    d=require_owner(request)
    if d:return d
    try:
        now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());end=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()+max(1,min(days,31))*86400))
        return {'ok':True,'events':google_api('calendar/v3/calendars/primary/events',{'timeMin':now,'timeMax':end,'singleEvents':'true','orderBy':'startTime','maxResults':'50'}).get('items',[])}
    except Exception as e:return JSONResponse({'ok':False,'error':str(e)},502)
@router.get('/google/gmail')
def gmail(request:Request,q:str='',max_results:int=20):
    d=require_owner(request)
    if d:return d
    try:
        data=google_api('gmail/v1/users/me/messages',{'q':q,'maxResults':str(max(1,min(max_results,50)))})
        out=[]
        for m in data.get('messages',[])[:50]:
            try:out.append(google_api('gmail/v1/users/me/messages/'+m['id'],{'format':'metadata','metadataHeaders':['From','To','Subject','Date']}))
            except Exception:pass
        return {'ok':True,'messages':out,'next_page_token':data.get('nextPageToken')}
    except Exception as e:return JSONResponse({'ok':False,'error':str(e)},502)
@router.get('/github/me')
def github_me(request:Request):
    d=require_owner(request)
    if d:return d
    try:return {'ok':True,'user':github_api('user')}
    except Exception as e:return JSONResponse({'ok':False,'error':str(e)},502)
@router.get('/github/repos')
def github_repos(request:Request,per_page:int=30):
    d=require_owner(request)
    if d:return d
    try:return {'ok':True,'repos':github_api('user/repos',{'per_page':str(max(1,min(per_page,100))),'sort':'updated','direction':'desc'})}
    except Exception as e:return JSONResponse({'ok':False,'error':str(e)},502)
@router.get('/github/issues')
def github_issues(request:Request,repo:str,state:str='open'):
    d=require_owner(request)
    if d:return d
    try:return {'ok':True,'issues':github_api(f'repos/{repo}/issues',{'state':state,'per_page':'50'})}
    except Exception as e:return JSONResponse({'ok':False,'error':str(e)},502)
@router.post('/github/issues')
async def create_issue(request:Request):
    d=require_owner(request)
    if d:return d
    p=await request.json()
    if not p.get('repo') or not p.get('title'):return JSONResponse({'ok':False,'error':'repo and title are required'},400)
    if not p.get('confirm'):return JSONResponse({'ok':False,'needs_approval':True,'action':'github.issue.create','prepared':p,'error':'Creating a GitHub issue requires explicit confirmation.'},409)
    try:return {'ok':True,'verified':True,'issue':github_api(f"repos/{p['repo']}/issues",method='POST',payload={'title':p['title'],'body':p.get('body',''),'labels':p.get('labels',[])})}
    except Exception as e:return JSONResponse({'ok':False,'error':str(e)},502)
