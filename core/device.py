"""Engola v0.12 device companion registry.

The companion is outbound-only: it authenticates with a short-lived pairing
code once, then receives a scoped device token that may only post heartbeats.
No device control endpoint is exposed in this version.
"""
import hashlib
import secrets
import time
from typing import Optional

from core.db import db

PAIR_TTL = 600
DEVICE_TOKEN_BYTES = 32


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def create_pairing() -> dict:
    now = time.time()
    code = _code()
    c = db()
    c.execute("DELETE FROM device_pairings WHERE expires_at < ? OR used_at IS NOT NULL", (now,))
    c.execute(
        "INSERT INTO device_pairings(code_hash,created_at,expires_at) VALUES(?,?,?)",
        (_hash(code), now, now + PAIR_TTL),
    )
    c.commit()
    c.close()
    return {"code": code, "expires_at": now + PAIR_TTL}


def claim_pairing(code: str, name: str, platform: str = "android") -> Optional[dict]:
    now = time.time()
    c = db()
    row = c.execute(
        "SELECT id FROM device_pairings WHERE code_hash=? AND used_at IS NULL AND expires_at>?",
        (_hash(code.strip().upper()), now),
    ).fetchone()
    if not row:
        c.close()
        return None
    token = secrets.token_urlsafe(DEVICE_TOKEN_BYTES)
    device_id = secrets.token_hex(8)
    c.execute(
        "UPDATE device_pairings SET used_at=? WHERE id=?",
        (now, row[0]),
    )
    c.execute(
        "INSERT INTO devices(device_id,name,platform,token_hash,created_at,last_seen,status) VALUES(?,?,?,?,?,?,?)",
        (device_id, name.strip()[:80] or "Android device", platform[:40], _hash(token), now, now, "online"),
    )
    c.commit()
    c.close()
    return {"device_id": device_id, "device_token": token}


def heartbeat(token: str, payload: dict) -> Optional[dict]:
    now = time.time()
    c = db()
    row = c.execute(
        "SELECT device_id FROM devices WHERE token_hash=?",
        (_hash(token),),
    ).fetchone()
    if not row:
        c.close()
        return None
    device_id = row[0]
    c.execute(
        """UPDATE devices SET name=?, platform=?, model=?, android_version=?, battery_pct=?,
           charging=?, network_type=?, network_name=?, storage_free=?, storage_total=?,
           capabilities=?, last_seen=?, status='online' WHERE device_id=?""",
        (
            str(payload.get("name") or "Android device")[:80],
            str(payload.get("platform") or "android")[:40],
            str(payload.get("model") or "")[:120],
            str(payload.get("android_version") or "")[:40],
            payload.get("battery_pct"),
            1 if payload.get("charging") else 0,
            str(payload.get("network_type") or "")[:40],
            str(payload.get("network_name") or "")[:120],
            payload.get("storage_free"),
            payload.get("storage_total"),
            str(payload.get("capabilities") or "")[:1000],
            now,
            device_id,
        ),
    )
    c.commit()
    c.close()
    return {"ok": True, "device_id": device_id, "last_seen": now}


def list_devices() -> list[dict]:
    now = time.time()
    c = db()
    rows = c.execute(
        """SELECT device_id,name,platform,model,android_version,battery_pct,charging,
           network_type,network_name,storage_free,storage_total,capabilities,last_seen,status
           FROM devices ORDER BY last_seen DESC"""
    ).fetchall()
    c.close()
    result = []
    for r in rows:
        item = {
            "device_id": r[0], "name": r[1], "platform": r[2], "model": r[3],
            "android_version": r[4], "battery_pct": r[5], "charging": bool(r[6]),
            "network_type": r[7], "network_name": r[8], "storage_free": r[9],
            "storage_total": r[10], "capabilities": r[11], "last_seen": r[12],
            "status": r[13],
        }
        if now - (r[12] or 0) > 120:
            item["status"] = "offline"
        result.append(item)
    return result
