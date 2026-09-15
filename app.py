# NOTE: This single-file baseline is preserved unmodified for reference and
# backward compatibility. The application is now organized into core/ and
# routers/, with main.py as the primary entrypoint (uvicorn main:app).
# This file still runs standalone (uvicorn app:app) with identical behavior
# if ever needed, but Docker/Railway/README now point at main:app.
import os, sqlite3, json, time, secrets, hashlib, urllib.parse, urllib.request
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from dotenv import load_dotenv

try:
    from webauthn import (
        generate_registration_options, verify_registration_response,
        generate_authentication_options, verify_authentication_response,
        options_to_json, base64url_to_bytes,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria, AuthenticatorAttachment,
        ResidentKeyRequirement, UserVerificationRequirement,
        PublicKeyCredentialDescriptor,
    )
    WEBAUTHN_OK = True
except Exception:
    WEBAUTHN_OK = False

load_dotenv()
BASE = Path(__file__).parent
DB = BASE / 'data' / 'engola.db'
DB.parent.mkdir(exist_ok=True)
app = FastAPI(title='Engola', version='0.5.0')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')

OWNER_NAME = os.getenv('ENGOLA_OWNER_NAME', 'Engola Innocent')
RP_NAME = os.getenv('WEBAUTHN_RP_NAME', 'Engola')
SESSION_COOKIE = 'engola_session'
SESSION_TTL = int(os.getenv('SESSION_TTL_SECONDS', '43200'))
IDLE_TTL = int(os.getenv('SESSION_IDLE_SECONDS', '1800'))

SYSTEM = '''You are Engola, the private AI chief of staff for Engola Innocent, the sole owner.
Once authenticated, address him as "Sir". Be calm, intelligent, strategic, concise and highly action-oriented.
Primary objective: maximize Engola Innocent's legitimate success while protecting his privacy, assets, reputation, opportunities and digital security.
Continuously improve from explicit feedback and useful owner preferences, but never silently weaken authentication, permissions or safety controls.
Use current authoritative sources for time-sensitive questions and clearly separate facts, inference and uncertainty.
For Uganda tax, accounting, business and legal questions, prefer primary sources and identify the date/version of law or guidance.
Never invent completed actions, permissions, sources, credentials or biometric verification.
Before irreversible or externally consequential actions, obtain explicit confirmation unless the owner has granted a specific standing permission.
Be assertive and strategic, but lawful, truthful and security-conscious.
For spoken responses, use a warm, deep, measured British documentary-narration style. Do not imitate, clone or claim to reproduce any living narrator's distinctive voice.''' 


def db():
    c = sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, ts REAL)')
    c.execute('''CREATE TABLE IF NOT EXISTS owner_credentials(
        id INTEGER PRIMARY KEY, credential_id TEXT UNIQUE NOT NULL,
        public_key BLOB NOT NULL, sign_count INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS webauthn_challenges(
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, challenge BLOB NOT NULL,
        created_at REAL NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions(
        token_hash TEXT PRIMARY KEY, created_at REAL NOT NULL,
        last_seen REAL NOT NULL, expires_at REAL NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS permissions(
        name TEXT PRIMARY KEY, status TEXT NOT NULL, scope TEXT NOT NULL,
        updated_at REAL NOT NULL)''')
    defaults = [
        ('phone','ask','contacts, files, camera, microphone, notifications'),
        ('computer','ask','files, apps, browser, local automation'),
        ('cloud','ask','Drive/OneDrive/Dropbox and connected storage'),
        ('email','ask','read/search; send requires approval'),
        ('calendar','ask','read/write after permission'),
        ('linkedin','ask','profile and approved job-search data'),
        ('github','ask','repositories and development workflows'),
        ('financial','deny','banking/payment actions remain locked by default'),
    ]
    for row in defaults:
        c.execute('INSERT OR IGNORE INTO permissions(name,status,scope,updated_at) VALUES(?,?,?,?)', (*row,time.time()))
    c.commit(); return c


def recent():
    c=db(); rows=c.execute('SELECT role,content FROM messages ORDER BY id DESC LIMIT 30').fetchall(); c.close(); return list(reversed(rows))

def memory_text():
    c=db(); rows=c.execute('SELECT key,value FROM memories ORDER BY id DESC LIMIT 150').fetchall(); c.close()
    return '\n'.join(f'- {k}: {v}' for k,v in rows)

def save(role, content):
    c=db(); c.execute('INSERT INTO messages(role,content,ts) VALUES(?,?,?)',(role,content,time.time())); c.commit(); c.close()

def remember(key,value):
    c=db(); c.execute('INSERT INTO memories(key,value,ts) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,ts=excluded.ts',(key,value,time.time())); c.commit(); c.close()

def rp_id(request: Request):
    configured=os.getenv('WEBAUTHN_RP_ID','').strip()
    if configured: return configured
    host=request.headers.get('host','').split(':')[0]
    return 'localhost' if host in ('','localhost','127.0.0.1') else host

def origin(request: Request):
    configured=os.getenv('WEBAUTHN_ORIGIN','').strip()
    if configured: return configured.rstrip('/')
    scheme=request.headers.get('x-forwarded-proto',request.url.scheme).split(',')[0].strip()
    return f"{scheme}://{request.headers.get('host',request.url.hostname)}"

def hash_token(token): return hashlib.sha256(token.encode()).hexdigest()

def has_owner():
    c=db(); n=c.execute('SELECT COUNT(*) FROM owner_credentials').fetchone()[0]; c.close(); return n>0

def current_owner(request):
    token=request.cookies.get(SESSION_COOKIE)
    if not token: return False
    now=time.time(); h=hash_token(token)
    c=db(); row=c.execute('SELECT last_seen,expires_at FROM sessions WHERE token_hash=?',(h,)).fetchone()
    if not row or row[1] < now or row[0] + IDLE_TTL < now:
        if row: c.execute('DELETE FROM sessions WHERE token_hash=?',(h,)); c.commit()
        c.close(); return False
    c.execute('UPDATE sessions SET last_seen=? WHERE token_hash=?',(now,h)); c.commit(); c.close(); return True

def require_owner(request):
    if not current_owner(request): return JSONResponse({'error':'Owner authentication required.'},401)
    return None

def save_challenge(kind, challenge):
    c=db(); c.execute('INSERT INTO webauthn_challenges(kind,challenge,created_at) VALUES(?,?,?)',(kind,challenge,time.time())); c.commit(); c.close()

def take_challenge(kind):
    c=db(); row=c.execute('SELECT id,challenge,created_at FROM webauthn_challenges WHERE kind=? ORDER BY id DESC LIMIT 1',(kind,)).fetchone()
    if not row: c.close(); return None
    c.execute('DELETE FROM webauthn_challenges WHERE id=?',(row[0],)); c.commit(); c.close()
    if time.time() - row[2] > 600: return None
    return row[1]

def create_session(response):
    token=secrets.token_urlsafe(48); now=time.time()
    c=db(); c.execute('INSERT INTO sessions(token_hash,created_at,last_seen,expires_at) VALUES(?,?,?,?)',(hash_token(token),now,now,now+SESSION_TTL)); c.commit(); c.close()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=os.getenv('COOKIE_SECURE','1')=='1', samesite='lax', max_age=SESSION_TTL, path='/')



def youtube_video_id(url):
    try:
        u=urllib.parse.urlparse(url.strip())
        host=u.netloc.lower().split(':')[0]
        if host in {'youtu.be','www.youtu.be'}:
            return u.path.strip('/').split('/')[0] or None
        if 'youtube.com' in host:
            if u.path == '/watch': return urllib.parse.parse_qs(u.query).get('v',[None])[0]
            parts=u.path.strip('/').split('/')
            if len(parts)>=2 and parts[0] in {'shorts','embed'}: return parts[1]
    except Exception:
        pass
    return None

def youtube_oembed(video_id):
    try:
        target='https://www.youtube.com/watch?v='+video_id
        url='https://www.youtube.com/oembed?url='+urllib.parse.quote(target,safe='')+'&format=json'
        req=urllib.request.Request(url,headers={'User-Agent':'Engola/0.5'})
        with urllib.request.urlopen(req,timeout=8) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return {}

def credential_count():
    c=db(); n=c.execute('SELECT COUNT(*) FROM owner_credentials').fetchone()[0]; c.close(); return n

@app.on_event('startup')
def startup(): db().close()

@app.get('/', response_class=HTMLResponse)
def home(): return (BASE/'static'/'index.html').read_text()

@app.get('/api/auth/status')
def auth_status(request: Request):
    return {'authenticated':current_owner(request),'owner':OWNER_NAME,'setup_required':not has_owner(),'webauthn_available':WEBAUTHN_OK}

@app.post('/api/auth/setup/options')
async def setup_options(request: Request):
    if not WEBAUTHN_OK: return JSONResponse({'error':'WebAuthn server library is not installed.'},500)
    if has_owner(): return JSONResponse({'error':'Owner passkey is already registered.'},409)
    body=await request.json(); token=(body.get('setup_token') or '').strip(); expected=os.getenv('ENGOLA_SETUP_TOKEN','').strip()
    if not expected or not secrets.compare_digest(token,expected): return JSONResponse({'error':'Invalid owner setup authorization.'},403)
    options=generate_registration_options(rp_id=rp_id(request),rp_name=RP_NAME,user_id=secrets.token_bytes(32),user_name=OWNER_NAME,user_display_name=OWNER_NAME,
        authenticator_selection=AuthenticatorSelectionCriteria(authenticator_attachment=AuthenticatorAttachment.PLATFORM,resident_key=ResidentKeyRequirement.REQUIRED,user_verification=UserVerificationRequirement.REQUIRED))
    save_challenge('registration',options.challenge); return json.loads(options_to_json(options))

@app.post('/api/auth/setup/verify')
async def setup_verify(request: Request):
    if not WEBAUTHN_OK: return JSONResponse({'error':'WebAuthn server library is not installed.'},500)
    if has_owner(): return JSONResponse({'error':'Owner passkey is already registered.'},409)
    body=await request.json(); token=(body.pop('setup_token','') or '').strip(); expected=os.getenv('ENGOLA_SETUP_TOKEN','').strip()
    if not expected or not secrets.compare_digest(token,expected): return JSONResponse({'error':'Invalid owner setup authorization.'},403)
    challenge=take_challenge('registration')
    if not challenge: return JSONResponse({'error':'Registration challenge expired. Start again.'},400)
    try:
        verification=verify_registration_response(credential=body,expected_challenge=challenge,expected_rp_id=rp_id(request),expected_origin=origin(request))
        c=db(); c.execute('INSERT INTO owner_credentials(credential_id,public_key,sign_count,created_at) VALUES(?,?,?,?)',(verification.credential_id.hex(),verification.credential_public_key,verification.sign_count,time.time())); c.commit(); c.close()
        response=JSONResponse({'ok':True,'owner':OWNER_NAME}); create_session(response); return response
    except Exception as e: return JSONResponse({'error':f'Passkey registration failed: {type(e).__name__}'},400)

@app.post('/api/auth/login/options')
def login_options(request: Request):
    if not WEBAUTHN_OK: return JSONResponse({'error':'WebAuthn server library is not installed.'},500)
    if not has_owner(): return JSONResponse({'error':'Owner setup is required first.'},409)
    c=db(); ids=[base64url_to_bytes(r[0]) for r in c.execute('SELECT credential_id FROM owner_credentials').fetchall()]; c.close()
    options=generate_authentication_options(rp_id=rp_id(request),allow_credentials=[PublicKeyCredentialDescriptor(id=i) for i in ids],user_verification=UserVerificationRequirement.REQUIRED)
    save_challenge('authentication',options.challenge); return json.loads(options_to_json(options))

@app.post('/api/auth/login/verify')
async def login_verify(request: Request):
    if not WEBAUTHN_OK: return JSONResponse({'error':'WebAuthn server library is not installed.'},500)
    body=await request.json(); challenge=take_challenge('authentication')
    if not challenge: return JSONResponse({'error':'Authentication challenge expired. Start again.'},400)
    try:
        credential_id=(body.get('id') or '').strip(); c=db(); row=c.execute('SELECT public_key,sign_count FROM owner_credentials WHERE credential_id=?',(credential_id,)).fetchone(); c.close()
        if not row: return JSONResponse({'error':'Unknown owner credential.'},403)
        verification=verify_authentication_response(credential=body,expected_challenge=challenge,expected_rp_id=rp_id(request),expected_origin=origin(request),credential_public_key=row[0],credential_current_sign_count=row[1])
        c=db(); c.execute('UPDATE owner_credentials SET sign_count=? WHERE credential_id=?',(verification.new_sign_count,credential_id)); c.commit(); c.close()
        response=JSONResponse({'ok':True,'owner':OWNER_NAME}); create_session(response); return response
    except Exception as e: return JSONResponse({'error':f'Passkey authentication failed: {type(e).__name__}'},403)

@app.post('/api/auth/logout')
def logout(request: Request):
    token=request.cookies.get(SESSION_COOKIE)
    if token:
        c=db(); c.execute('DELETE FROM sessions WHERE token_hash=?',(hash_token(token),)); c.commit(); c.close()
    response=JSONResponse({'ok':True}); response.delete_cookie(SESSION_COOKIE,path='/'); return response

@app.get('/api/history')
def history(request: Request):
    denied=require_owner(request)
    if denied: return denied
    c=db(); perms=[{'name':r[0],'status':r[1],'scope':r[2]} for r in c.execute('SELECT name,status,scope FROM permissions ORDER BY name')]; c.close()
    return {'messages':[{'role':r,'content':c} for r,c in recent()],'memories':memory_text(),'permissions':perms}

@app.get('/api/permissions')
def permissions(request: Request):
    denied=require_owner(request)
    if denied: return denied
    c=db(); rows=[{'name':r[0],'status':r[1],'scope':r[2]} for r in c.execute('SELECT name,status,scope FROM permissions ORDER BY name')]; c.close(); return {'permissions':rows}

@app.post('/api/permissions')
async def update_permission(request: Request):
    denied=require_owner(request)
    if denied: return denied
    b=await request.json(); name=(b.get('name') or '').strip(); status=(b.get('status') or '').strip()
    if status not in {'allow','ask','deny'}: return JSONResponse({'error':'status must be allow, ask or deny'},400)
    c=db(); row=c.execute('SELECT scope FROM permissions WHERE name=?',(name,)).fetchone()
    if not row: c.close(); return JSONResponse({'error':'Unknown permission scope.'},404)
    c.execute('UPDATE permissions SET status=?,updated_at=? WHERE name=?',(status,time.time(),name)); c.commit(); c.close(); return {'ok':True}


@app.post('/api/media/youtube')
async def youtube_media(request: Request):
    denied=require_owner(request)
    if denied: return denied
    body=await request.json(); url=(body.get('url') or '').strip()
    if not url: return JSONResponse({'error':'YouTube URL required.'},400)
    vid=youtube_video_id(url)
    if not vid: return JSONResponse({'error':'I could not identify a YouTube video from that URL.'},400)
    meta=youtube_oembed(vid)
    emb_origin=urllib.parse.quote(origin(request),safe='')
    return {'video_id':vid,'embed_url':f'https://www.youtube-nocookie.com/embed/{vid}?enablejsapi=1&origin={emb_origin}','watch_url':f'https://www.youtube.com/watch?v={vid}','title':meta.get('title','YouTube video'),'author':meta.get('author_name',''),'thumbnail':meta.get('thumbnail_url','')}

@app.post('/api/media/study')
async def study_media(request: Request):
    denied=require_owner(request)
    if denied: return denied
    body=await request.json(); title=(body.get('title') or '').strip(); url=(body.get('url') or '').strip(); note=(body.get('note') or '').strip()
    if not url: return JSONResponse({'error':'Media URL required.'},400)
    key=os.getenv('OPENAI_API_KEY')
    if not key: return JSONResponse({'error':'OPENAI_API_KEY is not configured on the server.'},503)
    context='''Media item for private study:\nTitle: {title}\nURL: {url}\nOwner note: {note}\n\nDo not claim to have watched or heard the video unless its actual contents are available. Use web search to verify the title/topic, identify authoritative related sources, extract useful public facts, and clearly label anything that is inference. Return: 1) verified takeaways, 2) useful sources, 3) uncertainties, 4) how this connects to Engola Innocent's existing knowledge.'''.format(title=title or 'Unknown',url=url,note=note or 'None')
    client=OpenAI(api_key=key)
    try:
        resp=client.responses.create(model=os.getenv('ENGOLA_MODEL','gpt-5.6'),input=[{'role':'system','content':SYSTEM},{'role':'user','content':context}],tools=[{'type':'web_search_preview'}])
        answer=resp.output_text
    except Exception as e:
        return JSONResponse({'error':f'AI study request failed: {type(e).__name__}: {e}'},502)
    remember('media:'+hashlib.sha256(url.encode()).hexdigest()[:16], f'{title or url}\n{answer[:6000]}')
    save('assistant',f'Media study — {title or url}\n{answer}')
    return {'answer':answer,'stored':True}

@app.post('/api/chat')
async def chat(request: Request):
    denied=require_owner(request)
    if denied: return denied
    body=await request.json(); text=(body.get('message') or '').strip()
    if not text: return JSONResponse({'error':'Empty message'},400)
    key=os.getenv('OPENAI_API_KEY')
    if not key: return JSONResponse({'error':'OPENAI_API_KEY is not configured on the server.'},503)
    save('user',text)
    client=OpenAI(api_key=key)
    prompt=SYSTEM+'\n\nKnown owner memory:\n'+(memory_text() or '(none)')
    msgs=[{'role':'system','content':prompt}]+[{'role':r,'content':c} for r,c in recent()]
    try:
        resp=client.responses.create(model=os.getenv('ENGOLA_MODEL','gpt-5.6'),input=msgs,tools=[{'type':'web_search_preview'}])
        answer=resp.output_text
    except Exception as e: return JSONResponse({'error':f'AI request failed: {type(e).__name__}: {e}'},502)
    save('assistant',answer); return {'answer':answer}

@app.post('/api/memory')
async def add_memory(request: Request):
    denied=require_owner(request)
    if denied: return denied
    b=await request.json(); key=(b.get('key') or '').strip(); value=(b.get('value') or '').strip()
    if not key or not value: return JSONResponse({'error':'key and value required'},400)
    remember(key,value); return {'ok':True}

@app.post('/api/clear')
def clear(request: Request):
    denied=require_owner(request)
    if denied: return denied
    c=db(); c.execute('DELETE FROM messages'); c.commit(); c.close(); return {'ok':True}

@app.get('/health')
def health():
    return {'ok':True,'engola':'ready','version':'0.3.0','owner_only':True,'owner_registered':has_owner(),'openai_configured':bool(os.getenv('OPENAI_API_KEY')),'webauthn_available':WEBAUTHN_OK}
