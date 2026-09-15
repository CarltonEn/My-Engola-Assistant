"""
Lightweight background job queue.

Phones on Termux choke if a chat response has to block on a YouTube
download, a transcription, or an embedding pass. This gives Engola a
"got it, working on it" path: enqueue a job, return immediately, process
it out-of-band, and let the caller poll or get notified when it's done.

Deliberately not Celery/Redis -- one more service to keep alive on a
phone is a cost, not a feature. This is a single SQLite table with an
atomic claim (`UPDATE ... WHERE status='queued' ... RETURNING`, with a
transaction fallback for older sqlite3 builds), a retry counter, and a
synchronous worker loop you can run in a background thread or an asyncio
task. Swap it for something heavier later if Engola ever needs multiple
worker processes across machines -- it won't on a single phone.
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Optional

from core.db import db

STATUSES = ("queued", "running", "done", "failed")


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        last_error TEXT,
        result_json TEXT,
        created_at REAL NOT NULL,
        started_at REAL,
        finished_at REAL)"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    conn.commit()


@dataclass
class Job:
    id: int
    kind: str
    payload: dict
    status: str
    attempts: int
    max_attempts: int
    last_error: Optional[str]
    result: Optional[dict]
    created_at: float
    started_at: Optional[float]
    finished_at: Optional[float]


def enqueue(kind: str, payload: Optional[dict] = None, max_attempts: int = 3) -> int:
    conn = db()
    _ensure_schema(conn)
    cur = conn.execute(
        """INSERT INTO jobs(kind, payload_json, status, max_attempts, created_at)
        VALUES (?,?, 'queued', ?, ?)""",
        (kind, json.dumps(payload or {}), max_attempts, time.time()),
    )
    conn.commit()
    return cur.lastrowid


def claim_next(kind: Optional[str] = None) -> Optional[Job]:
    """Atomically claim the oldest queued job (optionally filtered by
    kind) by flipping it to 'running'. Uses BEGIN IMMEDIATE so two
    workers polling at once can't claim the same row -- important the
    moment you have more than one asyncio task or thread pulling jobs."""
    conn = db()
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        query = "SELECT id FROM jobs WHERE status='queued'"
        params: list = []
        if kind:
            query += " AND kind=?"
            params.append(kind)
        query += " ORDER BY created_at ASC LIMIT 1"
        row = conn.execute(query, params).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        job_id = row[0]
        conn.execute(
            "UPDATE jobs SET status='running', started_at=?, attempts=attempts+1 WHERE id=?",
            (time.time(), job_id),
        )
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get(job_id)


def mark_done(job_id: int, result: Optional[dict] = None) -> None:
    conn = db()
    _ensure_schema(conn)
    conn.execute(
        "UPDATE jobs SET status='done', result_json=?, finished_at=? WHERE id=?",
        (json.dumps(result or {}), time.time(), job_id),
    )
    conn.commit()


def mark_failed(job_id: int, error: str) -> None:
    """Marks the job failed. If attempts remain under max_attempts, it is
    re-queued instead of left dead -- so a flaky mobile-data timeout
    doesn't require the owner to manually retry every ingest."""
    conn = db()
    _ensure_schema(conn)
    row = conn.execute("SELECT attempts, max_attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return
    attempts, max_attempts = row
    next_status = "queued" if attempts < max_attempts else "failed"
    conn.execute(
        "UPDATE jobs SET status=?, last_error=?, finished_at=? WHERE id=?",
        (next_status, error, time.time() if next_status == "failed" else None, job_id),
    )
    conn.commit()


def get(job_id: int) -> Optional[Job]:
    conn = db()
    _ensure_schema(conn)
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    return _row_to_job(conn, row)


def list_jobs(status: Optional[str] = None, limit: int = 50) -> list[Job]:
    conn = db()
    _ensure_schema(conn)
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [_row_to_job(conn, r) for r in rows]


def run_pending(handlers: dict[str, Callable[[dict], dict]], max_jobs: int = 10) -> list[dict]:
    """Synchronous worker pass: claim and process up to `max_jobs` queued
    jobs using the given kind -> handler map, then return. Call this from
    a background thread on a timer, or from an asyncio task via
    `loop.run_in_executor` -- it does blocking file/network I/O on
    purpose, so don't call it directly from an async request handler.

    `handlers[kind](payload) -> result_dict`. A handler that raises is
    caught, logged into `last_error`, and the job is retried or failed
    according to `max_attempts`.
    """
    processed = []
    for _ in range(max_jobs):
        job = claim_next()
        if not job:
            break
        handler = handlers.get(job.kind)
        if not handler:
            mark_failed(job.id, f"no handler registered for kind={job.kind!r}")
            processed.append({"id": job.id, "kind": job.kind, "status": "failed:no_handler"})
            continue
        try:
            result = handler(job.payload)
            mark_done(job.id, result)
            processed.append({"id": job.id, "kind": job.kind, "status": "done"})
        except Exception:
            err = traceback.format_exc(limit=5)
            mark_failed(job.id, err)
            processed.append({"id": job.id, "kind": job.kind, "status": "failed_or_requeued"})
    return processed


def _row_to_job(conn, row) -> Job:
    cols = [d[0] for d in conn.execute("SELECT * FROM jobs LIMIT 0").description]
    d = dict(zip(cols, row))
    return Job(
        id=d["id"], kind=d["kind"], payload=json.loads(d["payload_json"]),
        status=d["status"], attempts=d["attempts"], max_attempts=d["max_attempts"],
        last_error=d["last_error"],
        result=json.loads(d["result_json"]) if d["result_json"] else None,
        created_at=d["created_at"], started_at=d["started_at"], finished_at=d["finished_at"],
    )
