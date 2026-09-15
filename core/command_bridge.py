"""Hardened outbound command/job bridge for Engola agents.

The server is the control plane; paired devices initiate all network traffic.
Jobs are owner-created and must be explicitly approved before an agent can
claim them. Claimed jobs are lease-based so a crashed agent does not strand
work forever.
"""
import hashlib
import json
import secrets
import time
from typing import Optional

from core.db import db

QUEUE_TTL = 900
CLAIM_LEASE = 180
MAX_COMMAND = 12000
MAX_RESULT = 24000
KINDS = {"shell", "download", "telegram_upload"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_schema() -> None:
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS device_commands(
            id INTEGER PRIMARY KEY,
            command_id TEXT UNIQUE NOT NULL,
            device_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            approved INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            claimed_at REAL,
            completed_at REAL,
            result TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            lease_until REAL,
            idempotency_key TEXT UNIQUE)"""
        )
        # Safe additive migrations for installations created by v0.18.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(device_commands)").fetchall()}
        if "attempt_count" not in cols:
            conn.execute("ALTER TABLE device_commands ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
        if "lease_until" not in cols:
            conn.execute("ALTER TABLE device_commands ADD COLUMN lease_until REAL")
        if "idempotency_key" not in cols:
            conn.execute("ALTER TABLE device_commands ADD COLUMN idempotency_key TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_commands_poll "
            "ON device_commands(device_id,status,created_at)"
        )
        conn.commit()


def _validate_payload(kind: str, payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Payload must be an object")
    if kind == "shell":
        command = str(payload.get("command") or "").strip()
        if not command:
            raise ValueError("shell requires a command")
        if len(command) > 10000:
            raise ValueError("shell command is too long")
        timeout = int(payload.get("timeout", 120))
        if timeout < 1 or timeout > 600:
            raise ValueError("shell timeout must be 1-600 seconds")
    elif kind == "download":
        url = str(payload.get("url") or "").strip()
        path = str(payload.get("path") or "").strip()
        if not (url.startswith("https://") or url.startswith("http://")):
            raise ValueError("download requires an http(s) URL")
        if not path:
            raise ValueError("download requires a destination path")
    elif kind == "telegram_upload":
        path = str(payload.get("path") or "").strip()
        if not path:
            raise ValueError("telegram_upload requires a file path")


def queue_command(
    device_id: str,
    kind: str,
    payload: dict,
    approved: bool,
    idempotency_key: Optional[str] = None,
) -> dict:
    ensure_schema()
    kind = str(kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError("Unsupported command type")
    _validate_payload(kind, payload)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(raw) > MAX_COMMAND:
        raise ValueError("Command payload is too large")
    # Every executable job crosses the same explicit approval gate.
    if not approved:
        return {"ok": True, "needs_approval": True, "queued": False, "kind": kind}

    now = time.time()
    with db() as conn:
        if not conn.execute("SELECT 1 FROM devices WHERE device_id=?", (device_id,)).fetchone():
            raise ValueError("Unknown device")
        if idempotency_key:
            existing = conn.execute(
                "SELECT command_id,status,expires_at FROM device_commands WHERE idempotency_key=?",
                (idempotency_key[:160],),
            ).fetchone()
            if existing:
                return {
                    "ok": True, "queued": existing[1] in ("queued", "claimed"),
                    "duplicate": True, "command_id": existing[0],
                    "status": existing[1], "expires_at": existing[2],
                }
        command_id = secrets.token_urlsafe(18)
        conn.execute(
            """INSERT INTO device_commands(
               command_id,device_id,kind,payload,status,approved,created_at,expires_at,
               attempt_count,lease_until,idempotency_key)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (command_id, device_id, kind, raw, "queued", 1, now, now + QUEUE_TTL,
             0, None, idempotency_key[:160] if idempotency_key else None),
        )
        conn.commit()
    return {"ok": True, "queued": True, "command_id": command_id, "expires_at": now + QUEUE_TTL}


def _device_for_token(token: str) -> Optional[str]:
    if not token:
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT device_id FROM devices WHERE token_hash=?", (_hash(token),)
        ).fetchone()
    return row[0] if row else None


def poll(token: str, limit: int = 3) -> Optional[list[dict]]:
    ensure_schema()
    device_id = _device_for_token(token)
    if not device_id:
        return None
    now = time.time()
    with db() as conn:
        conn.execute(
            "UPDATE device_commands SET status='expired', lease_until=NULL "
            "WHERE status IN ('queued','claimed') AND expires_at<=?",
            (now,),
        )
        # Requeue a job whose worker disappeared after its lease expired.
        conn.execute(
            "UPDATE device_commands SET status='queued', claimed_at=NULL, lease_until=NULL "
            "WHERE status='claimed' AND lease_until IS NOT NULL AND lease_until<=? AND expires_at>?",
            (now, now),
        )
        rows = conn.execute(
            """SELECT id,command_id,kind,payload,expires_at,attempt_count
               FROM device_commands
               WHERE device_id=? AND status='queued' AND approved=1 AND expires_at>?
               ORDER BY id LIMIT ?""",
            (device_id, now, max(1, min(int(limit), 5))),
        ).fetchall()
        out = []
        for row in rows:
            cur = conn.execute(
                """UPDATE device_commands
                   SET status='claimed',claimed_at=?,lease_until=?,attempt_count=attempt_count+1
                   WHERE id=? AND status='queued'""",
                (now, now + CLAIM_LEASE, row[0]),
            )
            if cur.rowcount == 1:
                out.append({
                    "command_id": row[1], "kind": row[2], "payload": json.loads(row[3]),
                    "expires_at": row[4], "attempt": row[5] + 1,
                })
        conn.commit()
    return out


def complete(token: str, command_id: str, status: str, result: dict) -> Optional[dict]:
    ensure_schema()
    device_id = _device_for_token(token)
    if not device_id:
        return None
    if status not in {"completed", "failed"}:
        raise ValueError("Invalid command status")
    if not isinstance(result, dict):
        raise ValueError("Result must be an object")
    safe = json.dumps(result, ensure_ascii=False, separators=(",", ":"))[:MAX_RESULT]
    now = time.time()
    with db() as conn:
        cur = conn.execute(
            """UPDATE device_commands
               SET status=?,completed_at=?,result=?,lease_until=NULL
               WHERE command_id=? AND device_id=? AND status='claimed' AND expires_at>?""",
            (status, now, safe, command_id, device_id, now),
        )
        conn.commit()
        if cur.rowcount != 1:
            return None
    return {"ok": True, "command_id": command_id, "status": status, "completed_at": now}


def recent(limit: int = 20) -> list[dict]:
    ensure_schema()
    with db() as conn:
        rows = conn.execute(
            """SELECT command_id,device_id,kind,status,approved,created_at,expires_at,
                      claimed_at,completed_at,result,attempt_count,lease_until
               FROM device_commands ORDER BY id DESC LIMIT ?""",
            (max(1, min(int(limit), 50)),),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "command_id": r[0], "device_id": r[1], "kind": r[2], "status": r[3],
            "approved": bool(r[4]), "created_at": r[5], "expires_at": r[6],
            "claimed_at": r[7], "completed_at": r[8],
            "result": json.loads(r[9]) if r[9] else None,
            "attempt_count": r[10], "lease_until": r[11],
        })
    return out
