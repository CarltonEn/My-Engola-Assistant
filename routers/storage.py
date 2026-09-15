"""
/api/storage/* -- content-addressable storage, tiering, and the
background job queue. All owner-gated, matching the existing
require_owner() pattern used by every other router in this project.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import archive, jobs, ledger, storage
from core.config import AUTO_ARCHIVE
from core.security import require_owner

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.post("/upload")
async def upload(request: Request):
    """Raw-body upload -- deliberately not multipart/UploadFile, so a
    Termux `curl --data-binary` or a background download handler can call
    this with nothing but stdlib http, no client-side form-encoding
    needed. Pass filename/category/mime-type as query params or headers:
        curl -X POST '.../api/storage/upload?filename=x.pdf&category=knowledge' \
             -H 'Content-Type: application/pdf' --data-binary @x.pdf
    """
    denied = require_owner(request)
    if denied:
        return denied
    data = await request.body()
    if not data:
        return JSONResponse({"error": "empty body"}, status_code=400)
    filename = request.query_params.get("filename", "")
    category = request.query_params.get("category", "uncategorised")
    mime_type = request.headers.get("content-type", "")
    record = storage.store_blob(data, filename=filename, mime_type=mime_type, category=category)
    ledger.record(
        actor="owner", stage="REMEMBER", action="storage.upload",
        detail={"filename": filename, "category": category, "deduplicated": record.deduplicated},
        blob_hash=record.hash, result="ok",
    )
    archive_job_id = None
    providers = archive.configured_provider_names()
    if AUTO_ARCHIVE and providers and not storage.has_archive_pointer(record.hash):
        archive_job_id = jobs.enqueue("archive_blob", {"blob_hash": record.hash, "providers": providers})
        ledger.record(actor="engola", stage="PREPARE", action="storage.archive.queued",
                      detail={"providers": providers, "job_id": archive_job_id}, blob_hash=record.hash)
    return {
        "hash": record.hash,
        "filename": record.filename,
        "size_bytes": record.size_bytes,
        "category": record.category,
        "tier": record.tier,
        "deduplicated": record.deduplicated,
        "archive_job_id": archive_job_id,
        "archive_providers": providers,
    }


@router.get("/stats")
def stats(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    return storage.stats()


@router.get("/blobs")
def blobs(request: Request, category: str | None = None, tier: str | None = None, limit: int = 100):
    denied = require_owner(request)
    if denied:
        return denied
    records = storage.list_blobs(category=category, tier=tier, limit=limit)
    return {"blobs": [
        {
            "hash": r.hash, "filename": r.filename, "category": r.category,
            "size_bytes": r.size_bytes, "tier": r.tier,
            "has_cold_pointer": r.has_cold_pointer,
            "archives": storage.archive_objects(r.hash),
            "created_at": r.created_at, "last_accessed_at": r.last_accessed_at,
        } for r in records
    ]}


@router.post("/evict")
def evict(request: Request, max_age_days: float = 30.0, dry_run: bool = True):
    denied = require_owner(request)
    if denied:
        return denied
    results = storage.evict(max_age_days=max_age_days, dry_run=dry_run)
    if not dry_run:
        ledger.record(
            actor="owner", stage="ACT", action="storage.evict",
            detail={"max_age_days": max_age_days, "count": len(results)}, result="ok",
        )
    return {"dry_run": dry_run, "results": results}


@router.post("/budget")
def budget(request: Request, max_hot_bytes: int, min_free_bytes: int = 0, dry_run: bool = True):
    denied = require_owner(request)
    if denied:
        return denied
    result = storage.enforce_storage_budget(max_hot_bytes, min_free_bytes, dry_run=dry_run)
    return result


@router.get("/ledger")
def ledger_recent(request: Request, limit: int = 50, blob_hash: str | None = None):
    denied = require_owner(request)
    if denied:
        return denied
    entries = ledger.recent(limit=limit, blob_hash=blob_hash)
    return {"entries": [
        {
            "correlation_id": e.correlation_id, "ts": e.ts, "actor": e.actor,
            "stage": e.stage, "action": e.action, "detail": e.detail,
            "blob_hash": e.blob_hash, "result": e.result,
        } for e in entries
    ]}


@router.get("/providers")
def providers(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    return {"providers": archive.status(), "auto_archive": AUTO_ARCHIVE}


@router.get("/blobs/{sha256_hex}/archives")
def blob_archives(request: Request, sha256_hex: str):
    denied = require_owner(request)
    if denied:
        return denied
    if not storage.get_blob_record(sha256_hex):
        return JSONResponse({"error": "blob not found"}, status_code=404)
    return {"hash": sha256_hex, "archives": storage.archive_objects(sha256_hex)}


@router.post("/blobs/{sha256_hex}/archive")
def archive_now(request: Request, sha256_hex: str, provider: str | None = None):
    denied = require_owner(request)
    if denied:
        return denied
    if not storage.get_blob_record(sha256_hex):
        return JSONResponse({"error": "blob not found"}, status_code=404)
    providers = [provider] if provider else archive.configured_provider_names()
    if not providers:
        return JSONResponse({"error": "no configured archive providers"}, status_code=503)
    job_id = jobs.enqueue("archive_blob", {"blob_hash": sha256_hex, "providers": providers})
    ledger.record(actor="owner", stage="PREPARE", action="storage.archive.requested",
                  detail={"providers": providers, "job_id": job_id}, blob_hash=sha256_hex)
    return {"ok": True, "job_id": job_id, "providers": providers}


@router.post("/blobs/{sha256_hex}/restore")
def restore_blob(request: Request, sha256_hex: str):
    denied = require_owner(request)
    if denied:
        return denied
    if not storage.get_blob_record(sha256_hex):
        return JSONResponse({"error": "blob not found"}, status_code=404)
    job_id = jobs.enqueue("restore_blob", {"blob_hash": sha256_hex})
    return {"ok": True, "job_id": job_id}


@router.get("/jobs")
def jobs_list(request: Request, status: str | None = None, limit: int = 50):
    denied = require_owner(request)
    if denied:
        return denied
    job_list = jobs.list_jobs(status=status, limit=limit)
    return {"jobs": [
        {
            "id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts,
            "last_error": j.last_error, "created_at": j.created_at,
            "finished_at": j.finished_at,
        } for j in job_list
    ]}


@router.post("/jobs")
async def jobs_enqueue(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    body = await request.json()
    kind = (body.get("kind") or "").strip()
    if not kind:
        return JSONResponse({"error": "kind required"}, status_code=400)
    job_id = jobs.enqueue(kind, payload=body.get("payload") or {})
    return {"ok": True, "job_id": job_id}
