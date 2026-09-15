"""Provider-neutral integration clients. Secrets never reach the browser."""
import json,time,urllib.parse,urllib.request
from core import config
from core.db import db

def _request(url,method='GET',data=None,headers=None,timeout=20):
    req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())
def ensure_tables():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS oauth_states (provider TEXT PRIMARY KEY,state TEXT NOT NULL,created_at REAL NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS github_tokens (id INTEGER PRIMARY KEY CHECK(id=1),access_token TEXT NOT NULL,scope TEXT,updated_at REAL NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS google_tokens (id INTEGER PRIMARY KEY CHECK(id=1),access_token TEXT NOT NULL,refresh_token TEXT,scope TEXT,expires_at REAL,updated_at REAL NOT NULL)")
        c.commit()
def save_state(provider,state):
    ensure_tables()
    with db() as c:c.execute("INSERT INTO oauth_states(provider,state,created_at) VALUES(?,?,?) ON CONFLICT(provider) DO UPDATE SET state=excluded.state,created_at=excluded.created_at",(provider,state,time.time()));c.commit()
def take_state(provider,state,max_age=600):
    ensure_tables()
    with db() as c:
        row=c.execute("SELECT state,created_at FROM oauth_states WHERE provider=?",(provider,)).fetchone()
        if not row or row[0]!=state or time.time()-row[1]>max_age:return False
        c.execute("DELETE FROM oauth_states WHERE provider=?",(provider,));c.commit();return True
def google_access_token():
    ensure_tables()
    with db() as c:row=c.execute("SELECT access_token,refresh_token,expires_at FROM google_tokens WHERE id=1").fetchone()
    if not row:return None
    access,refresh,exp=row
    if access and exp and exp>time.time()+90:return access
    if not refresh or not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:return None
    data=urllib.parse.urlencode({'client_id':config.GOOGLE_CLIENT_ID,'client_secret':config.GOOGLE_CLIENT_SECRET,'refresh_token':refresh,'grant_type':'refresh_token'}).encode()
    try:tok=_request('https://oauth2.googleapis.com/token','POST',data,{'Content-Type':'application/x-www-form-urlencoded'})
    except Exception:return None
    if 'access_token' not in tok:return None
    expires=time.time()+int(tok.get('expires_in',3600))
    with db() as c:c.execute('UPDATE google_tokens SET access_token=?,expires_at=?,updated_at=? WHERE id=1',(tok['access_token'],expires,time.time()));c.commit()
    return tok['access_token']
def google_api(path,params=None):
    token=google_access_token()
    if not token:raise RuntimeError('Google is not connected or its token cannot be refreshed.')
    url='https://www.googleapis.com/'+path.lstrip('/')
    if params:url+='?'+urllib.parse.urlencode(params)
    return _request(url,headers={'Authorization':'Bearer '+token})
def github_access_token():
    ensure_tables()
    with db() as c:row=c.execute('SELECT access_token FROM github_tokens WHERE id=1').fetchone()
    return row[0] if row else None
def github_api(path,params=None,method='GET',payload=None):
    token=github_access_token()
    if not token:raise RuntimeError('GitHub is not connected.')
    url='https://api.github.com/'+path.lstrip('/')
    if params:url+='?'+urllib.parse.urlencode(params)
    data=json.dumps(payload).encode() if payload is not None else None
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    if data:headers['Content-Type']='application/json'
    return _request(url,method,data,headers)
