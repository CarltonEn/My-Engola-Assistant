"""
Append-only action ledger.

Every consequential thing Engola does -- a download, an upload, an
external API call, a permission check, an approval -- writes exactly one
row here. This is both the audit trail the project's own security rules
already require, and (via `blob_hash`) the storage manifest: at any
point you can answer "what does Engola have, where does it physically
live, and why did it get there" by reading this table joined with
`blobs`.

Rows are never updated or deleted by normal operation -- "append-only" is
the point. If a later stage of the same logical action happens (e.g.
PREPARE -> APPROVE -> ACT), record a new row with the same `correlation_id`
rather than mutating the old one.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from core.db import db

# The stages are deliberately a closed set matching the project's own
# security spec. Using anything else is a bug, not a style choice.
STAGES = ("KNOW", "THINK", "PREPARE", "APPROVE", "ACT", "VERIFY", "REMEMBER", "BLOCKED")


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS action_ledger(
        id INTEGER PRIMARY KEY,
        correlation_id TEXT NOT NULL,
        ts REAL NOT NULL,
        actor TEXT NOT NULL,
        stage TEXT NOT NULL,
        action TEXT NOT NULL,
        detail_json TEXT,
        blob_hash TEXT,
        approved_by TEXT,
        result TEXT)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_correlation ON action_ledger(correlation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_blob ON action_ledger(blob_hash)"
    )
    conn.commit()


@dataclass
class LedgerEntry:
    id: int
    correlation_id: str
    ts: float
    actor: str
    stage: str
    action: str
    detail: dict
    blob_hash: Optional[str]
    approved_by: Optional[str]
    result: Optional[str]


def record(
    actor: str,
    stage: str,
    action: str,
    detail: Optional[dict] = None,
    blob_hash: Optional[str] = None,
    approved_by: Optional[str] = None,
    result: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> str:
    """Append one ledger row. Returns the correlation_id -- pass the same
    value back in for subsequent stages of the same logical action so
    they can be reconstructed as one timeline later."""
    if stage not in STAGES:
        raise ValueError(f"unknown ledger stage {stage!r}, must be one of {STAGES}")
    conn = db()
    _ensure_schema(conn)
    cid = correlation_id or uuid.uuid4().hex
    conn.execute(
        """INSERT INTO action_ledger(
            correlation_id, ts, actor, stage, action, detail_json,
            blob_hash, approved_by, result
        ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (cid, time.time(), actor, stage, action, json.dumps(detail or {}),
         blob_hash, approved_by, result),
    )
    conn.commit()
    return cid


def timeline(correlation_id: str) -> list[LedgerEntry]:
    conn = db()
    _ensure_schema(conn)
    rows = conn.execute(
        "SELECT * FROM action_ledger WHERE correlation_id=? ORDER BY ts ASC",
        (correlation_id,),
    ).fetchall()
    return [_row_to_entry(conn, r) for r in rows]


def recent(limit: int = 50, actor: Optional[str] = None, blob_hash: Optional[str] = None) -> list[LedgerEntry]:
    conn = db()
    _ensure_schema(conn)
    query = "SELECT * FROM action_ledger WHERE 1=1"
    params: list = []
    if actor:
        query += " AND actor=?"
        params.append(actor)
    if blob_hash:
        query += " AND blob_hash=?"
        params.append(blob_hash)
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [_row_to_entry(conn, r) for r in rows]


def _row_to_entry(conn, row) -> LedgerEntry:
    cols = [d[0] for d in conn.execute("SELECT * FROM action_ledger LIMIT 0").description]
    d = dict(zip(cols, row))
    return LedgerEntry(
        id=d["id"], correlation_id=d["correlation_id"], ts=d["ts"], actor=d["actor"],
        stage=d["stage"], action=d["action"], detail=json.loads(d["detail_json"] or "{}"),
        blob_hash=d["blob_hash"], approved_by=d["approved_by"], result=d["result"],
    )
