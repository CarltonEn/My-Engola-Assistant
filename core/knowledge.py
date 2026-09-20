"""Free-first knowledge ingestion for Engola v0.11.

Supports public web pages, PDFs and YouTube transcripts without paid AI APIs.
The extracted text is kept in Engola's private SQLite workspace. Fetching is
restricted to public HTTP(S) targets to reduce SSRF risk.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from io import BytesIO
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from typing import Any

from core.db import db
from core import archive, jobs, ledger, storage
from core.config import AUTO_ARCHIVE

MAX_BYTES = 15 * 1024 * 1024
MAX_TEXT = 2_000_000
USER_AGENT = "Engola/0.11 (private knowledge ingestion)"

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self.in_title = False
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True
    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            if self.in_title:
                self.title += (" " if self.title else "") + value
            self.parts.append(value)

def _public_url(url: str) -> str:
    p = urlparse((url or "").strip())
    if p.scheme not in {"http", "https"}:
        raise ValueError("Only public http(s) URLs can be ingested.")
    if p.username or p.password or not p.hostname:
        raise ValueError("Credentials or an invalid hostname are not allowed.")
    host = p.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local/private hosts are not allowed.")
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError("The host could not be resolved.") from exc
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Private or reserved network targets are not allowed.")
    return p.geturl()

def _fetch(url: str) -> tuple[bytes, str, str]:
    safe = _public_url(url)
    req = Request(safe, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain,*/*;q=0.5"})
    with urlopen(req, timeout=20) as response:
        ctype = (response.headers.get("Content-Type") or "").lower()
        chunks, total = [], 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("Source exceeds Engola's 15 MB ingestion limit.")
            chunks.append(chunk)
        return b"".join(chunks), ctype, response.geturl()

def _youtube_id(url: str) -> str | None:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        return p.path.strip("/").split("/")[0] or None
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return parse_qs(p.query).get("v", [None])[0]
    return None

def _youtube_transcript(url: str) -> tuple[str, str, dict[str, Any]]:
    video_id = _youtube_id(url)
    if not video_id:
        raise ValueError("Invalid YouTube URL.")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        data = YouTubeTranscriptApi().fetch(video_id, languages=["en"]).to_raw_data()
    except ImportError as exc:
        raise ValueError("YouTube transcript support is not installed.") from exc
    except Exception as exc:
        raise ValueError(f"YouTube transcript unavailable: {exc}") from exc
    text = "\n".join(str(x.get("text", "")).strip() for x in data if x.get("text"))
    if not text:
        raise ValueError("The video has no readable transcript.")
    return f"YouTube video {video_id}", text, {"video_id": video_id, "segments": len(data)}

def _pdf_text(data: bytes) -> tuple[str, dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("PDF support is not installed.") from exc
    reader = PdfReader(BytesIO(data))
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    return text, {"pages": len(reader.pages)}

def _web_text(data: bytes) -> tuple[str, str, dict[str, Any]]:
    parser = _TextExtractor()
    parser.feed(data.decode("utf-8", errors="replace"))
    return parser.title[:300] or "Web page", "\n".join(parser.parts), {"title": parser.title[:300]}

def _archive_bytes_if_possible(data: bytes, filename: str, mime_type: str) -> str | None:
    """Stores raw bytes in the local hot tier and, if auto-archive is enabled
    and a provider (Telegram/Gmail) is configured, enqueues the same real
    background job the /upload endpoint already uses. Never raises --
    losing the ability to archive must never break ingestion of the text."""
    try:
        record = storage.store_blob(data, filename=filename, mime_type=mime_type, category="knowledge")
        providers = archive.configured_provider_names()
        if AUTO_ARCHIVE and providers and not storage.has_archive_pointer(record.hash):
            jobs.enqueue("archive_blob", {"blob_hash": record.hash, "providers": providers})
        ledger.record(actor="owner", stage="REMEMBER", action="knowledge.ingest",
                      detail={"filename": filename, "deduplicated": record.deduplicated},
                      blob_hash=record.hash, result="ok")
        return record.hash
    except Exception:
        return None


def ingest_url(url: str) -> dict[str, Any]:
    url = _public_url(url)
    yt = _youtube_id(url)
    blob_hash = None
    if yt:
        title, text, meta = _youtube_transcript(url)
        kind = "youtube"
    else:
        data, ctype, final_url = _fetch(url)
        filename = final_url.rsplit("/", 1)[-1] or "source"
        if "pdf" in ctype or url.lower().split("?", 1)[0].endswith(".pdf"):
            text, meta = _pdf_text(data)
            title = filename or "PDF document"
            kind = "pdf"
        elif "text/plain" in ctype:
            text = data.decode("utf-8", errors="replace")
            title, meta, kind = (filename or "Text document"), {}, "text"
        elif ctype.startswith("image/"):
            # No text is extracted here (no vision model call is made, so
            # none is invented) -- the original image is still preserved
            # and archived rather than silently discarded.
            text, meta, kind = "", {"note": "Image ingested; no text extraction was performed."}, "image"
            title = filename or "Image"
        else:
            title, text, meta = _web_text(data)
            kind = "web"
        blob_hash = _archive_bytes_if_possible(data, filename, ctype or "application/octet-stream")

    text = text.strip()
    if not text:
        if kind == "image":
            text = f"[{title}] Image ingested and archived. No text was extracted (no vision analysis was performed on it)."
        else:
            raise ValueError("Engola could not extract readable text from that source.")
    text = text[:MAX_TEXT]
    now = time.time()
    conn = db()
    cur = conn.execute(
        "INSERT INTO knowledge_sources(url,title,kind,status,metadata,text,created_at,updated_at,blob_hash) VALUES(?,?,?,?,?,?,?,?,?)",
        (url, title, kind, "ready", json.dumps(meta, ensure_ascii=False), text, now, now, blob_hash),
    )
    source_id = cur.lastrowid
    conn.commit(); conn.close()
    return {"id": source_id, "url": url, "title": title, "kind": kind, "characters": len(text),
            "metadata": meta, "archived": bool(blob_hash)}

def list_sources(limit: int = 50) -> list[dict[str, Any]]:
    conn = db(); rows = conn.execute("SELECT id,url,title,kind,status,metadata,created_at,updated_at,LENGTH(text),blob_hash FROM knowledge_sources ORDER BY id DESC LIMIT ?", (limit,)).fetchall(); conn.close()
    return [{"id":r[0],"url":r[1],"title":r[2],"kind":r[3],"status":r[4],"metadata":json.loads(r[5] or "{}"),"created_at":r[6],"updated_at":r[7],"characters":r[8] or 0,"has_original":bool(r[9])} for r in rows]

def get_source(source_id: int) -> dict[str, Any] | None:
    conn = db(); r = conn.execute("SELECT id,url,title,kind,status,metadata,text,created_at,updated_at,blob_hash FROM knowledge_sources WHERE id=?", (source_id,)).fetchone(); conn.close()
    if not r: return None
    return {"id":r[0],"url":r[1],"title":r[2],"kind":r[3],"status":r[4],"metadata":json.loads(r[5] or "{}"),"text":r[6],"created_at":r[7],"updated_at":r[8],"blob_hash":r[9]}

def search_sources(query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = [x for x in re.findall(r"[\w'-]+", (query or "").lower()) if len(x) > 2][:10]
    if not terms: return []
    conn = db(); rows = conn.execute("SELECT id,url,title,kind,text FROM knowledge_sources WHERE status='ready' ORDER BY id DESC LIMIT 100").fetchall(); conn.close()
    scored = []
    for r in rows:
        hay = (r[2] + "\n" + r[4]).lower(); score = sum(hay.count(t) for t in terms)
        if score:
            pos = min((hay.find(t) for t in terms if hay.find(t) >= 0), default=0)
            excerpt = re.sub(r"\s+", " ", r[4][max(0,pos-220):pos+620]).strip()
            scored.append((score, {"id":r[0],"url":r[1],"title":r[2],"kind":r[3],"score":score,"excerpt":excerpt}))
    scored.sort(key=lambda x: (-x[0], -x[1]["id"]))
    return [x[1] for x in scored[:limit]]

def delete_source(source_id: int) -> bool:
    conn = db(); cur = conn.execute("DELETE FROM knowledge_sources WHERE id=?", (source_id,)); conn.commit(); conn.close(); return cur.rowcount > 0


def import_text_source(*, url: str, title: str, kind: str, text: str, metadata: dict | None = None) -> dict:
    """Import text acquired outside Railway (e.g. Termux) without storing the original binary."""
    import json as _json, time as _time
    clean=(text or '').strip()
    if not clean: raise ValueError('No readable text supplied.')
    clean=clean[:MAX_TEXT]
    metadata=metadata or {}
    conn=db()
    existing=conn.execute('SELECT id FROM knowledge_sources WHERE url=? AND status=\'ready\' ORDER BY id DESC LIMIT 1',(url,)).fetchone()
    if existing:
        conn.execute('UPDATE knowledge_sources SET title=?,kind=?,metadata=?,text=?,updated_at=? WHERE id=?',(title[:300],kind,_json.dumps(metadata,ensure_ascii=False),clean,_time.time(),existing[0]))
        source_id=existing[0]
    else:
        now=_time.time()
        cur=conn.execute('INSERT INTO knowledge_sources(url,title,kind,status,metadata,text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(url,title[:300],kind,'ready',_json.dumps(metadata,ensure_ascii=False),clean,now,now))
        source_id=cur.lastrowid
    conn.commit(); conn.close()
    return {'id':source_id,'url':url,'title':title[:300],'kind':kind,'characters':len(clean),'metadata':metadata}


def search_for_chat(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Return compact evidence records suitable for owner chat without an LLM."""
    rows = search_sources(query, limit=limit)
    out=[]
    q=(query or "").strip().lower()
    for row in rows:
        text=(row.get("text") or row.get("excerpt") or "").strip()
        if not text:
            continue
        pos=text.lower().find(q) if q else -1
        if pos < 0:
            pos=0
        start=max(0,pos-350); end=min(len(text),pos+1400)
        out.append({"id":row.get("id"),"title":row.get("title"),"url":row.get("url"),"kind":row.get("kind"),"excerpt":text[start:end]})
    return out
