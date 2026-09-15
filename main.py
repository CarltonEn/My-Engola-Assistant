from routers.capabilities import router as capabilities_router
from routers.preferences import router as preferences_router
from routers.media import router as media_router
"""
Engola application entrypoint.

Router-split successor to the v0.5 canonical single-file app.py. Every
route that existed in app.py is preserved with identical behavior (see
core/ and routers/ for the migrated logic); new modules (career, uganda,
voice, google_oauth) are additive.

Run locally:
    uvicorn main:app --reload --port 8000

Run in Docker/Railway: see Dockerfile / railway.json (CMD now points at
main:app instead of app:app).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import APP_VERSION, STATIC_DIR, WORKER_ENABLED
from core.db import db
from routers import device_commands, system_status
from routers.news import router as news_router
from core.worker import Worker
from routers import auth, career, chat, device, executive, github_oauth, google_oauth, health, integration_actions, knowledge, media, memory, permissions, research, storage, uganda, voice, voice_natural, work

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), usb=()")
        return response


worker = Worker()

@asynccontextmanager
async def lifespan(app):
    db().close()
    if WORKER_ENABLED:
        worker.start()
    try:
        yield
    finally:
        if WORKER_ENABLED:
            worker.stop()

app = FastAPI(title="Engola", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth.router)
app.include_router(device.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(knowledge.router)
app.include_router(permissions.router)
app.include_router(media.router)
app.include_router(career.router)
app.include_router(uganda.router)
app.include_router(voice.router)
app.include_router(voice_natural.router)
app.include_router(work.router)
app.include_router(google_oauth.router)
app.include_router(github_oauth.router)
app.include_router(storage.router)
app.include_router(device_commands.router)
app.include_router(system_status.router)
app.include_router(integration_actions.router)
app.include_router(research.router)
app.include_router(news_router)
app.include_router(executive.router)
app.include_router(health.router)
app.include_router(capabilities_router)
app.include_router(preferences_router)



@app.get("/", response_class=HTMLResponse)
def home():
    html = (STATIC_DIR / "index.html").read_text()
    marker = '</head>'
    addons = '<link rel="stylesheet" href="/static/engola-v11.css"><script defer src="/static/engola-v11.js"></script><link rel="stylesheet" href="/static/engola-v12.css"><script defer src="/static/engola-v12.js"></script><link rel="stylesheet" href="/static/engola-v16.css"><script defer src="/static/engola-v16.js"></script><link rel="stylesheet" href="/static/engola-v17.css"><script defer src="/static/engola-v17.js"></script><link rel="stylesheet" href="/static/engola-v18.css"><script defer src="/static/engola-v18.js"></script><link rel="stylesheet" href="/static/engola-v1.1.css"><script defer src="/static/engola-v1.1.js"></script>'
    return HTMLResponse(html.replace(marker, addons + marker, 1))
