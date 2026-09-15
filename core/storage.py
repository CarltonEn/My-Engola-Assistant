"""
Content-addressable storage with hot/cold tiering and dedup.

Design goals (Termux/phone-constrained deployment):
  - Never store the same bytes twice. Every blob is addressed by its
    SHA-256 hash. If a hash already exists, the new write links to the
    existing row instead of writing a duplicate file.
  - Keep the on-device ("hot") footprint small. Large or stale blobs can
    be pushed to a "cold" archive (e.g. Telegram, S3, anything) and
    deleted locally, leaving only a metadata pointer behind. Nothing here
    implements a specific archive provider -- it defines the pointer
    fields (archive_provider / archive_identifier / archive_message_id /
    archive_file_id / archive_url) and the local side of the handoff.
    Wire an actual uploader in where noted below.
  - Never invent success. If a blob has no cold pointer, eviction refuses
    to delete it and says why.

This module is additive and self-contained: it manages its own table
(`blobs`) via `_ensure_schema`, called at the top of every public
function, exactly like the idempotent CREATE TABLE IF NOT EXISTS pattern
already used in core/db.py. No existing table or behavior is touched.
"""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.config import DATA_DIR
from core.db import db

BLOB_DIR = DATA_DIR / "blobs"
BLOB_DIR.mkdir(exist_ok=True, parents=True)

# Content-addressed local storage uses git-style sharding (first 2 hex
# chars as a subdirectory) so a single directory never holds too many
# files -- matters on phone filesystems more than on a server.
def _shard_path(sha256_hex: str) -> Path:
    return BLOB_DIR / sha256_hex[:2] / sha256_hex


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS blobs(
        hash TEXT PRIMARY KEY,
        filename TEXT,
        mime_type TEXT,
        category TEXT NOT NULL DEFAULT 'uncategorised',
        size_bytes INTEGER NOT NULL,
        tier TEXT NOT NULL DEFAULT 'hot',
        local_path TEXT,
        archive_provider TEXT,
        archive_identifier TEXT,
        archive_message_id TEXT,
        archive_file_id TEXT,
        archive_url TEXT,
        created_at REAL NOT NULL,
        last_accessed_at REAL NOT NULL,
        access_count INTEGER NOT NULL DEFAULT 0)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS archive_objects(
        id INTEGER PRIMARY KEY,
        blob_hash TEXT NOT NULL,
        provider TEXT NOT NULL,
        identifier TEXT,
        message_id TEXT,
        file_id TEXT,
        url TEXT,
        verified_at REAL NOT NULL,
        UNIQUE(blob_hash, provider, identifier, file_id, url),
        FOREIGN KEY(blob_hash) REFERENCES blobs(hash))"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_objects_blob ON archive_objects(blob_hash)")
    conn.commit()


@dataclass
class BlobRecord:
    hash: str
    filename: Optional[str]
    mime_type: Optional[str]
    category: str
    size_bytes: int
    tier: str
    local_path: Optional[str]
    archive_provider: Optional[str]
    archive_identifier: Optional[str]
    archive_message_id: Optional[str]
    archive_file_id: Optional[str]
    archive_url: Optional[str]
    created_at: float
    last_accessed_at: float
    access_count: int
    deduplicated: bool = False

    @property
    def has_cold_pointer(self) -> bool:
        return bool(self.archive_provider and (
            self.archive_identifier or self.archive_file_id or self.archive_url
        )) or has_archive_pointer(self.hash)


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_blob(
    data: bytes,
    filename: str = "",
    mime_type: str = "",
    category: str = "uncategorised",
) -> BlobRecord:
    """Store `data` in the hot tier, deduplicating by content hash.

    Returns the resulting BlobRecord. `deduplicated=True` means the bytes
    already existed and no new file was written -- only the access
    metadata was refreshed.
    """
    conn = db()
    _ensure_schema(conn)
    digest = hash_bytes(data)
    now = time.time()

    existing = conn.execute("SELECT * FROM blobs WHERE hash=?", (digest,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE blobs SET last_accessed_at=?, access_count=access_count+1 WHERE hash=?",
            (now, digest),
        )
        conn.commit()
        record = _row_to_record(conn, digest)
        record.deduplicated = True
        return record

    if not mime_type:
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    path = _shard_path(digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    conn.execute(
        """INSERT INTO blobs(
            hash, filename, mime_type, category, size_bytes, tier, local_path,
            created_at, last_accessed_at, access_count
        ) VALUES (?,?,?,?,?,?,?,?,?,0)""",
        (digest, filename, mime_type, category, len(data), "hot", str(path), now, now),
    )
    conn.commit()
    return _row_to_record(conn, digest)


def get_blob_record(sha256_hex: str) -> Optional[BlobRecord]:
    conn = db()
    _ensure_schema(conn)
    row = conn.execute("SELECT hash FROM blobs WHERE hash=?", (sha256_hex,)).fetchone()
    if not row:
        return None
    return _row_to_record(conn, sha256_hex)


def get_blob_bytes(sha256_hex: str) -> Optional[bytes]:
    """Read blob bytes from the hot tier. Returns None if evicted to cold
    or not found -- caller is responsible for fetching from the archive
    provider using the pointer fields if `has_cold_pointer` is True."""
    conn = db()
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT local_path, tier FROM blobs WHERE hash=?", (sha256_hex,)
    ).fetchone()
    if not row or row[1] != "hot" or not row[0]:
        return None
    path = Path(row[0])
    if not path.exists():
        return None
    conn.execute(
        "UPDATE blobs SET last_accessed_at=?, access_count=access_count+1 WHERE hash=?",
        (time.time(), sha256_hex),
    )
    conn.commit()
    return path.read_bytes()


def register_archive_object(
    sha256_hex: str,
    provider: str,
    identifier: str = "",
    message_id: str = "",
    file_id: str = "",
    url: str = "",
) -> bool:
    """Record a verified external archive object. Multiple providers may
    hold replicas of the same blob. This is called only after the provider
    confirms that the bytes were accepted and a stable pointer was returned."""
    conn = db()
    _ensure_schema(conn)
    row = conn.execute("SELECT hash FROM blobs WHERE hash=?", (sha256_hex,)).fetchone()
    if not row:
        return False
    conn.execute(
        """INSERT OR IGNORE INTO archive_objects(
            blob_hash, provider, identifier, message_id, file_id, url, verified_at
        ) VALUES (?,?,?,?,?,?,?)""",
        (sha256_hex, provider, identifier, message_id, file_id, url, time.time()),
    )
    conn.commit()
    return True


def has_archive_pointer(sha256_hex: str) -> bool:
    conn = db()
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT 1 FROM archive_objects WHERE blob_hash=? LIMIT 1", (sha256_hex,)
    ).fetchone()
    if row:
        return True
    row = conn.execute(
        "SELECT archive_provider, archive_identifier, archive_file_id, archive_url FROM blobs WHERE hash=?",
        (sha256_hex,),
    ).fetchone()
    return bool(row and row[0] and (row[1] or row[2] or row[3]))


def archive_objects(sha256_hex: str) -> list[dict]:
    conn = db()
    _ensure_schema(conn)
    rows = conn.execute(
        "SELECT provider, identifier, message_id, file_id, url, verified_at "
        "FROM archive_objects WHERE blob_hash=? ORDER BY verified_at ASC", (sha256_hex,)
    ).fetchall()
    return [
        {"provider": r[0], "identifier": r[1], "message_id": r[2],
         "file_id": r[3], "url": r[4], "verified_at": r[5]}
        for r in rows
    ]


def register_archive_ref(
    sha256_hex: str,
    provider: str,
    identifier: str = "",
    message_id: str = "",
    file_id: str = "",
    url: str = "",
) -> bool:
    """Backward-compatible primary pointer registration plus the new
    multi-provider archive manifest."""
    conn = db()
    _ensure_schema(conn)
    row = conn.execute("SELECT hash FROM blobs WHERE hash=?", (sha256_hex,)).fetchone()
    if not row:
        return False
    conn.execute(
        """UPDATE blobs SET archive_provider=?, archive_identifier=?,
        archive_message_id=?, archive_file_id=?, archive_url=? WHERE hash=?""",
        (provider, identifier, message_id, file_id, url, sha256_hex),
    )
    conn.execute(
        """INSERT OR IGNORE INTO archive_objects(
            blob_hash, provider, identifier, message_id, file_id, url, verified_at
        ) VALUES (?,?,?,?,?,?,?)""",
        (sha256_hex, provider, identifier, message_id, file_id, url, time.time()),
    )
    conn.commit()
    return True

def evict(
    max_age_days: float = 30.0,
    min_access_count: int = 0,
    dry_run: bool = True,
) -> list[dict]:
    """Move hot-tier blobs older than `max_age_days` (by last access) to
    the cold tier by deleting the local file -- but ONLY for blobs that
    already have a cold-archive pointer registered. A blob with no
    archive pointer is never deleted; it is reported as 'skipped:
    no_archive_pointer' instead, because deleting it would be silent data
    loss, which this project's own rules forbid.

    Returns a list of {hash, filename, size_bytes, action} describing
    what happened (or would happen, if dry_run=True) to each candidate.
    """
    conn = db()
    _ensure_schema(conn)
    cutoff = time.time() - (max_age_days * 86400)
    candidates = conn.execute(
        """SELECT hash, filename, size_bytes, local_path, archive_provider,
        archive_identifier, archive_file_id, archive_url
        FROM blobs WHERE tier='hot' AND last_accessed_at < ? AND access_count >= ?""",
        (cutoff, min_access_count),
    ).fetchall()

    results = []
    for (h, filename, size_bytes, local_path, provider, identifier, file_id, url) in candidates:
        has_pointer = has_archive_pointer(h)
        if not has_pointer:
            results.append({
                "hash": h, "filename": filename, "size_bytes": size_bytes,
                "action": "skipped:no_archive_pointer",
            })
            continue
        if dry_run:
            results.append({
                "hash": h, "filename": filename, "size_bytes": size_bytes,
                "action": "would_evict",
            })
            continue
        if local_path and Path(local_path).exists():
            Path(local_path).unlink()
        conn.execute("UPDATE blobs SET tier='cold', local_path=NULL WHERE hash=?", (h,))
        results.append({
            "hash": h, "filename": filename, "size_bytes": size_bytes,
            "action": "evicted",
        })
    if not dry_run:
        conn.commit()
    return results


def enforce_storage_budget(
    max_hot_bytes: int,
    min_free_bytes: int = 0,
    dry_run: bool = True,
) -> dict:
    """Evict oldest-accessed, already-archived hot blobs until the hot
    tier is under `max_hot_bytes`, or until disk free space is above
    `min_free_bytes` (whichever is stricter). Blobs without a cold
    pointer are never touched -- if the budget can't be met without them,
    this returns still-over-budget honestly instead of deleting data.
    """
    conn = db()
    _ensure_schema(conn)
    rows = conn.execute(
        """SELECT hash, size_bytes, archive_provider, archive_identifier,
        archive_file_id, archive_url, local_path
        FROM blobs WHERE tier='hot' ORDER BY last_accessed_at ASC"""
    ).fetchall()
    total_hot = sum(r[1] for r in rows)
    disk_free = shutil.disk_usage(DATA_DIR).free

    evicted = []
    for (h, size_bytes, provider, identifier, file_id, url, local_path) in rows:
        if total_hot <= max_hot_bytes and disk_free >= min_free_bytes:
            break
        has_pointer = has_archive_pointer(h)
        if not has_pointer:
            continue
        if not dry_run:
            if local_path and Path(local_path).exists():
                Path(local_path).unlink()
            conn.execute("UPDATE blobs SET tier='cold', local_path=NULL WHERE hash=?", (h,))
        evicted.append(h)
        total_hot -= size_bytes
        disk_free += size_bytes

    if not dry_run:
        conn.commit()

    return {
        "dry_run": dry_run,
        "evicted_count": len(evicted),
        "evicted_hashes": evicted,
        "hot_bytes_after": total_hot,
        "disk_free_after_estimate": disk_free,
        "still_over_budget": total_hot > max_hot_bytes,
    }


def stats() -> dict:
    conn = db()
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM blobs WHERE tier='hot'"
    ).fetchone()
    cold_row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM blobs WHERE tier='cold'"
    ).fetchone()
    by_category = conn.execute(
        "SELECT category, COUNT(*), COALESCE(SUM(size_bytes),0) FROM blobs GROUP BY category"
    ).fetchall()
    return {
        "hot_count": row[0],
        "hot_bytes": row[1],
        "cold_count": cold_row[0],
        "cold_bytes_logical": cold_row[1],  # bytes freed locally, not disk usage elsewhere
        "by_category": [
            {"category": c, "count": n, "size_bytes": s} for (c, n, s) in by_category
        ],
        "disk_free_bytes": shutil.disk_usage(DATA_DIR).free,
    }


def list_blobs(category: Optional[str] = None, tier: Optional[str] = None, limit: int = 100) -> list[BlobRecord]:
    conn = db()
    _ensure_schema(conn)
    query = "SELECT hash FROM blobs WHERE 1=1"
    params: list = []
    if category:
        query += " AND category=?"
        params.append(category)
    if tier:
        query += " AND tier=?"
        params.append(tier)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [_row_to_record(conn, r[0]) for r in rows]


def _row_to_record(conn, sha256_hex: str) -> BlobRecord:
    row = conn.execute("SELECT * FROM blobs WHERE hash=?", (sha256_hex,)).fetchone()
    cols = [d[0] for d in conn.execute("SELECT * FROM blobs LIMIT 0").description]
    d = dict(zip(cols, row))
    return BlobRecord(
        hash=d["hash"], filename=d["filename"], mime_type=d["mime_type"],
        category=d["category"], size_bytes=d["size_bytes"], tier=d["tier"],
        local_path=d["local_path"], archive_provider=d["archive_provider"],
        archive_identifier=d["archive_identifier"], archive_message_id=d["archive_message_id"],
        archive_file_id=d["archive_file_id"], archive_url=d["archive_url"],
        created_at=d["created_at"], last_accessed_at=d["last_accessed_at"],
        access_count=d["access_count"],
    )
