"""Small in-process worker for Engola's phone/Termux deployment.

It intentionally uses the existing SQLite job queue instead of adding Redis,
Celery, or another daemon. Network/file work is performed outside request
handlers and failures are retried by core.jobs.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from core import archive, jobs, ledger, storage


def handle_archive(payload: dict) -> dict:
    blob_hash = (payload.get("blob_hash") or "").strip()
    if not blob_hash:
        raise ValueError("archive job requires blob_hash")
    providers = payload.get("providers")
    if providers is not None and not isinstance(providers, list):
        raise ValueError("providers must be a list")
    cid = ledger.record(actor="engola", stage="ACT", action="storage.archive",
                        detail={"blob_hash": blob_hash, "providers": providers})
    pointers = archive.archive_blob(blob_hash, provider_names=providers)
    for pointer in pointers:
        ledger.record(actor="engola", stage="VERIFY", action="storage.archive.verified",
                      detail={"provider": pointer.provider, "identifier": pointer.identifier},
                      blob_hash=blob_hash, result="ok", correlation_id=cid)
    return {"blob_hash": blob_hash, "providers": [p.provider for p in pointers],
            "pointers": [p.__dict__ for p in pointers]}


def handle_restore(payload: dict) -> dict:
    blob_hash = (payload.get("blob_hash") or "").strip()
    if not blob_hash:
        raise ValueError("restore job requires blob_hash")
    data = archive._restore_from_existing_archive(blob_hash)
    if storage.hash_bytes(data) != blob_hash:
        raise ValueError("restored bytes failed SHA-256 verification")
    record = storage.get_blob_record(blob_hash)
    # Rehydrate into hot storage without changing its content identity.
    storage.store_blob(data, filename=record.filename or blob_hash,
                       mime_type=record.mime_type or "application/octet-stream",
                       category=record.category)
    return {"blob_hash": blob_hash, "restored": True, "size_bytes": len(data)}


HANDLERS = {"archive_blob": handle_archive, "restore_blob": handle_restore}


class Worker:
    def __init__(self, interval: float = 2.0, max_jobs: int = 3) -> None:
        self.interval = interval
        self.max_jobs = max_jobs
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="engola-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                jobs.run_pending(HANDLERS, max_jobs=self.max_jobs)
            except Exception:
                # The job itself is responsible for retry state; a worker-loop
                # failure must never take down the web process.
                pass
            self._stop.wait(self.interval)
