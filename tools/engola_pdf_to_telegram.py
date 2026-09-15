#!/usr/bin/env python3
"""Acquire PDFs locally and archive them to the Telegram storage linked to Engola.

Usage:
  python ~/Engola-master/tools/engola_pdf_to_telegram.py URL
  python ~/Engola-master/tools/engola_pdf_to_telegram.py URL --category "tax" --authority "primary_law"

Environment:
  ENGOLA_URL                  Engola Railway URL
  ENGOLA_INGEST_TOKEN         ingestion token configured on Railway
  ENGOLA_TELEGRAM_BOT_TOKEN   Telegram bot token
  ENGOLA_TELEGRAM_CHAT_ID     private archive chat/channel id

The script uploads the original PDF to Telegram (<=49 MB via the standard Bot API),
extracts text when pypdf is installed, hashes the original, and imports the extracted
text plus provenance into Engola. Credentials are read from the environment and are
never printed.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import urllib.error

MAX_BYTES = 49 * 1024 * 1024
UA = "Engola-Termux-Acquirer/0.15"

def download(url: str) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as r:
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise RuntimeError("PDF exceeds Telegram Bot API 49 MB upload limit.")
        return data, r.geturl()

def telegram_document(token: str, chat_id: str, path: Path, caption: str = ""):
    boundary = "----EngolaBoundary"
    body = bytearray()
    def field(name, value):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode()); body.extend(b"\r\n")
    field("chat_id", chat_id)
    if caption: field("caption", caption[:1024])
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'.encode())
    body.extend(b"Content-Type: application/pdf\r\n\r\n")
    body.extend(path.read_bytes()); body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    req = Request(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(req, timeout=60) as r:
        result = json.loads(r.read().decode())
    if not result.get("ok"):
        raise RuntimeError("Telegram upload failed.")
    return result["result"]

def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        try: parts.append(page.extract_text() or "")
        except Exception: parts.append("")
    return "\n\n".join(parts).strip()[:2_000_000]

def import_to_engola(url, final_url, title, text, sha256, category, authority):
    base = (os.getenv("ENGOLA_URL") or "").rstrip("/")
    token = os.getenv("ENGOLA_INGEST_TOKEN") or ""
    if not base or not token:
        raise RuntimeError("ENGOLA_URL and ENGOLA_INGEST_TOKEN must be configured in Termux.")
    payload = json.dumps({
        "url": final_url or url, "title": title, "kind": "pdf",
        "text": text, "category": category, "authority": authority,
        "sha256": sha256, "source_url": url
    }).encode()
    req = Request(
        base + "/api/knowledge/import", data=payload, method="POST",
        headers={"Content-Type":"application/json","X-Engola-Ingest-Token":token}
    )
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--category", default="general")
    ap.add_argument("--authority", default="reference")
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()
    if urlparse(args.url).scheme not in {"http", "https"}:
        raise SystemExit("Only HTTP/HTTPS URLs are supported.")
    data, final_url = download(args.url)
    sha = hashlib.sha256(data).hexdigest()
    name = Path(urlparse(final_url).path).name or "engola-source.pdf"
    if not name.lower().endswith(".pdf"): name += ".pdf"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / name
        path.write_bytes(data)
        tg = None
        if not args.no_telegram:
            token = os.getenv("ENGOLA_TELEGRAM_BOT_TOKEN") or ""
            chat = os.getenv("ENGOLA_TELEGRAM_CHAT_ID") or ""
            if not token or not chat:
                raise SystemExit("Telegram archive not configured: set ENGOLA_TELEGRAM_BOT_TOKEN and ENGOLA_TELEGRAM_CHAT_ID.")
            tg = telegram_document(token, chat, path, f"Engola archive | {args.category} | {args.authority} | sha256:{sha}")
        text = extract_pdf(path)
        if not text:
            print("WARNING: pypdf is not installed; original was archived but no text was imported.", file=sys.stderr)
        result = import_to_engola(args.url, final_url, name, text or "[Original archived to Telegram; text extraction unavailable.]", sha, args.category, args.authority)
    print(json.dumps({"ok": True, "title": name, "sha256": sha, "characters": len(text), "telegram_archived": bool(tg), "engola_import": result}, indent=2))

if __name__ == "__main__":
    main()
