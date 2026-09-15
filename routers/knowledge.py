from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from core.knowledge import delete_source, get_source, ingest_url, list_sources, search_sources, import_text_source
from core.security import require_owner
from core import archive, jobs, ledger, storage
from core.config import AUTO_ARCHIVE
import json
import os
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

class IngestBody(BaseModel):
    url: str = Field(min_length=8, max_length=2048)

class SearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=300)

@router.get("")
def knowledge_list(request: Request):
    denied = require_owner(request)
    if denied: return denied
    return {"ok": True, "sources": list_sources()}

@router.post("/upload")
async def knowledge_upload(request: Request, file: UploadFile = File(...)):
    """Upload a real PDF/TXT/Markdown source into content-addressed storage and
    the knowledge vault. Large archive work is queued; no fake ingestion state."""
    denied = require_owner(request)
    if denied:
        return denied
    filename = (file.filename or "uploaded-source").strip()[:240]
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in {"pdf", "txt", "md", "markdown"}:
        raise HTTPException(400, "Only PDF, TXT, Markdown files are supported.")
    data = await file.read(15 * 1024 * 1024 + 1)
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Uploaded file exceeds Engola's 15 MB ingestion limit.")
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    try:
        if suffix == "pdf":
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(data))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
            metadata = {"pages": len(reader.pages)}
            kind = "pdf"
        else:
            text = data.decode("utf-8", errors="replace").strip()
            metadata = {}
            kind = "markdown" if suffix in {"md", "markdown"} else "text"
    except Exception as exc:
        raise HTTPException(400, f"Could not extract text: {type(exc).__name__}") from exc
    if not text:
        raise HTTPException(400, "No readable text was extracted from the file.")
    blob = storage.store_blob(data, filename=filename, mime_type=file.content_type or "", category="knowledge")
    metadata.update({"sha256": blob.hash, "size_bytes": blob.size_bytes})
    source = import_text_source(url=f"engola://blob/{blob.hash}", title=filename, kind=kind,
                                text=text[:2_000_000], metadata=metadata)
    ledger.record(actor="owner", stage="REMEMBER", action="knowledge.upload",
                  detail={"filename": filename, "kind": kind, "deduplicated": blob.deduplicated},
                  blob_hash=blob.hash, result="ok")
    archive_job_id = None
    providers = archive.configured_provider_names()
    if AUTO_ARCHIVE and providers and not storage.has_archive_pointer(blob.hash):
        archive_job_id = jobs.enqueue("archive_blob", {"blob_hash": blob.hash, "providers": providers})
    return {"ok": True, "source": source, "blob": {"hash": blob.hash, "size_bytes": blob.size_bytes,
            "tier": blob.tier, "deduplicated": blob.deduplicated}, "archive_job_id": archive_job_id}

@router.get("/wiki")
def wiki_search(request: Request, query: str = ""):
    denied = require_owner(request)
    if denied: return denied
    q = (query or "").strip()[:120]
    if not q:
        return {"ok": True, "results": []}
    url = "https://en.wikipedia.org/w/api.php?action=opensearch&search=" + quote(q) + "&limit=6&namespace=0&format=json"
    req = UrlRequest(url, headers={"User-Agent": "Engola/0.11 (Wikipedia research)"})
    try:
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        raise HTTPException(502, f"Wikipedia search failed: {exc}") from exc
    titles = data[1] if len(data) > 1 else []
    descriptions = data[2] if len(data) > 2 else []
    urls = data[3] if len(data) > 3 else []
    return {"ok": True, "results": [{"title": t, "description": descriptions[i] if i < len(descriptions) else "", "url": urls[i] if i < len(urls) else ""} for i, t in enumerate(titles)]}

@router.get("/{source_id}")
def knowledge_get(source_id: int, request: Request):
    denied = require_owner(request)
    if denied: return denied
    source = get_source(source_id)
    if not source:
        raise HTTPException(404, "Knowledge source not found")
    return {"ok": True, "source": source}

@router.post("/ingest")
def knowledge_ingest(body: IngestBody, request: Request):
    denied = require_owner(request)
    if denied: return denied
    try:
        return {"ok": True, "source": ingest_url(body.url)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Engola could not ingest that source: {exc}") from exc

@router.post("/search")
def knowledge_search(body: SearchBody, request: Request):
    denied = require_owner(request)
    if denied: return denied
    return {"ok": True, "results": search_sources(body.query)}

@router.delete("/{source_id}")
def knowledge_delete(source_id: int, request: Request):
    denied = require_owner(request)
    if denied: return denied
    if not delete_source(source_id):
        raise HTTPException(404, "Knowledge source not found")
    return {"ok": True, "deleted": source_id}


@router.post('/import')
def knowledge_import(body: dict, request: Request):
    # Termux acquisition uses a separate ingestion token so WebAuthn does not
    # need to be automated on the phone. Keep this token out of browser code.
    expected=(os.getenv('ENGOLA_INGEST_TOKEN') or '').strip()
    supplied=(request.headers.get('X-Engola-Ingest-Token') or '').strip()
    if not expected or not supplied or not __import__('secrets').compare_digest(expected,supplied):
        return JSONResponse({'error':'Invalid ingestion authorization.'},403)
    text=(body.get('text') or '').strip()
    url=(body.get('url') or body.get('final_url') or '').strip()
    if not text or not url:
        return JSONResponse({'error':'url and text are required.'},400)
    source=import_text_source(url=url,title=(body.get('title') or url).strip(),kind=(body.get('kind') or 'external').strip(),text=text,metadata=body.get('metadata') or {k:body[k] for k in ('category','authority','sha256','archive_provider','archive_message_id','archive_file_id') if k in body})
    return {'ok':True,'source':source}
