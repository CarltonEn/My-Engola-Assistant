"""Pluggable cold-archive providers for Engola.

The storage layer owns bytes and content identity; providers only know how to
put/get those bytes in an external durable system. A provider must return a
verified pointer before Engola is allowed to evict the local copy.

Implemented providers:
- Telegram Bot API: durable document messages in a configured archive chat.
- Gmail API: self-addressed archive emails with attachments (subject to Gmail
  message limits). This is intentionally a small archive adapter, not a
  replacement for Drive/object storage for very large files.

The provider registry is deliberately generic so Drive/S3/OneDrive/etc. can
be added without changing core/storage.py or the UI contract.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from core import config, storage
from core.db import db


class ArchiveError(RuntimeError):
    pass


@dataclass
class ArchivePointer:
    provider: str
    identifier: str = ""
    message_id: str = ""
    file_id: str = ""
    url: str = ""


class ArchiveProvider:
    name = "base"
    max_bytes: Optional[int] = None

    def configured(self) -> bool:
        return False

    def archive(self, blob_hash: str, data: bytes, filename: str, mime_type: str) -> ArchivePointer:
        raise NotImplementedError

    def restore(self, pointer: ArchivePointer) -> bytes:
        raise NotImplementedError


def _json_request(url: str, method: str = "GET", payload: Optional[dict] = None,
                  headers: Optional[dict] = None, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        **(headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
    except Exception as exc:
        raise ArchiveError(f"archive request failed: {type(exc).__name__}: {exc}") from exc
    try:
        result = json.loads(body) if body else {}
    except Exception as exc:
        raise ArchiveError("archive provider returned invalid JSON") from exc
    if isinstance(result, dict) and result.get("ok") is False:
        raise ArchiveError(str(result))
    return result


def _multipart(parts: list[tuple[str, bytes, str]], fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----EngolaArchive" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks += [f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                   value.encode(), b"\r\n"]
    for name, content, mime in parts:
        chunks += [f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="{name}"; filename="archive.bin"\r\n'.encode(),
                   f"Content-Type: {mime}\r\n\r\n".encode(), content, b"\r\n"]
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class TelegramProvider(ArchiveProvider):
    name = "telegram"

    def __init__(self) -> None:
        self.token = os.getenv("ENGOLA_TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("ENGOLA_TELEGRAM_ARCHIVE_CHAT_ID", "").strip()
        self.api_base = os.getenv("ENGOLA_TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")

    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _api(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    def archive(self, blob_hash: str, data: bytes, filename: str, mime_type: str) -> ArchivePointer:
        if not self.configured():
            raise ArchiveError("Telegram archive is not configured")
        # The public Bot API has a provider-side size limit; make it configurable
        # rather than pretending every Telegram deployment has the same limit.
        max_bytes = int(os.getenv("ENGOLA_TELEGRAM_MAX_BYTES", str(50 * 1024 * 1024)))
        if len(data) > max_bytes:
            raise ArchiveError(f"Telegram archive payload exceeds configured limit ({max_bytes} bytes)")
        caption = f"Engola archive | sha256={blob_hash}\nfilename={filename}\nsize={len(data)}"
        body, content_type = _multipart(
            [("document", data, mime_type or "application/octet-stream")],
            {"chat_id": self.chat_id, "caption": caption},
        )
        req = urllib.request.Request(
            self._api("sendDocument"), data=body, method="POST",
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                result = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            raise ArchiveError(f"Telegram upload failed: {type(exc).__name__}: {exc}") from exc
        if not result.get("ok"):
            raise ArchiveError(f"Telegram upload rejected: {result}")
        message = result.get("result") or {}
        document = message.get("document") or {}
        file_id = document.get("file_id")
        message_id = message.get("message_id")
        if not file_id or not message_id:
            raise ArchiveError("Telegram upload succeeded without a usable archive pointer")
        return ArchivePointer(
            provider=self.name,
            identifier=f"{self.chat_id}:{message_id}",
            message_id=str(message_id),
            file_id=str(file_id),
        )

    def restore(self, pointer: ArchivePointer) -> bytes:
        if not self.configured() or not pointer.file_id:
            raise ArchiveError("Telegram restore is not configured or pointer is incomplete")
        meta = _json_request(self._api("getFile"), "POST", {"file_id": pointer.file_id}, timeout=30)
        path = (meta.get("result") or {}).get("file_path")
        if not path:
            raise ArchiveError("Telegram did not return file_path")
        url = f"{self.api_base}/file/bot{self.token}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception as exc:
            raise ArchiveError(f"Telegram restore failed: {type(exc).__name__}: {exc}") from exc


class GmailProvider(ArchiveProvider):
    name = "gmail"
    # Gmail API messages have a practical raw-message ceiling around 35 MB;
    # attachments also consume base64 overhead. Keep a conservative default.
    max_bytes = 25 * 1024 * 1024

    def _token(self) -> str:
        c = db()
        row = c.execute("SELECT access_token, refresh_token, expires_at FROM google_tokens WHERE id=1").fetchone()
        c.close()
        if not row:
            raise ArchiveError("Google account is not connected")
        access_token, refresh_token, expires_at = row
        if access_token and expires_at and expires_at > time.time() + 60:
            return access_token
        if not refresh_token or not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
            raise ArchiveError("Google access token expired and refresh is not configured")
        data = urllib.parse.urlencode({
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                token_data = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            raise ArchiveError(f"Google token refresh failed: {type(exc).__name__}: {exc}") from exc
        token = token_data.get("access_token")
        if not token:
            raise ArchiveError("Google token refresh returned no access token")
        c = db()
        c.execute("UPDATE google_tokens SET access_token=?, expires_at=?, updated_at=? WHERE id=1",
                  (token, time.time() + int(token_data.get("expires_in", 3600)), time.time()))
        c.commit(); c.close()
        return token

    def configured(self) -> bool:
        c = db()
        row = c.execute("SELECT 1 FROM google_tokens WHERE id=1").fetchone()
        c.close()
        return bool(row and config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)

    def archive(self, blob_hash: str, data: bytes, filename: str, mime_type: str) -> ArchivePointer:
        if not self.configured():
            raise ArchiveError("Gmail archive requires a connected Google account")
        if len(data) > self.max_bytes:
            raise ArchiveError(f"Gmail archive payload exceeds conservative attachment limit ({self.max_bytes} bytes)")
        token = self._token()
        c = db(); row = c.execute("SELECT access_token FROM google_tokens WHERE id=1").fetchone(); c.close()
        # Build an RFC822 message addressed to the connected mailbox.
        profile = _json_request("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                                headers={"Authorization": f"Bearer {token}"})
        email = profile.get("emailAddress")
        if not email:
            raise ArchiveError("Gmail profile did not return an email address")
        msg = EmailMessage()
        msg["To"] = email
        msg["From"] = email
        msg["Subject"] = f"Engola Archive | {blob_hash} | {filename}"
        msg.set_content(f"Engola cold archive\nsha256: {blob_hash}\nfilename: {filename}\nsize: {len(data)} bytes")
        msg.add_attachment(data, maintype=(mime_type or "application/octet-stream").split("/", 1)[0],
                           subtype=(mime_type or "application/octet-stream").split("/", 1)[-1],
                           filename=filename or f"{blob_hash}.bin")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
        result = _json_request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                               "POST", {"raw": raw}, {"Authorization": f"Bearer {token}"}, timeout=60)
        message_id = result.get("id")
        if not message_id:
            raise ArchiveError("Gmail accepted the request without returning a message id")
        return ArchivePointer(provider=self.name, identifier=str(message_id), message_id=str(message_id))

    def restore(self, pointer: ArchivePointer) -> bytes:
        if not pointer.message_id and not pointer.identifier:
            raise ArchiveError("Gmail pointer has no message id")
        token = self._token()
        message_id = pointer.message_id or pointer.identifier
        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/" + urllib.parse.quote(message_id, safe="") + "?format=full"
        message = _json_request(url, headers={"Authorization": f"Bearer {token}"})

        def parts_of(node: dict):
            yield node
            for child in node.get("parts") or []:
                yield from parts_of(child)

        for part in parts_of(message.get("payload") or {}):
            body = part.get("body") or {}
            data = body.get("data")
            attachment_id = body.get("attachmentId")
            if attachment_id:
                attach_url = (
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                    + urllib.parse.quote(message_id, safe="") + "/attachments/"
                    + urllib.parse.quote(attachment_id, safe="")
                )
                attachment = _json_request(attach_url, headers={"Authorization": f"Bearer {token}"})
                data = attachment.get("data")
            if data:
                try:
                    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                except Exception as exc:
                    raise ArchiveError("Gmail attachment contained invalid base64") from exc
        raise ArchiveError("No attachment data found in Gmail archive message")


PROVIDERS = {
    "telegram": TelegramProvider,
    "gmail": GmailProvider,
}


def configured_provider_names() -> list[str]:
    names = [x.strip().lower() for x in os.getenv("ENGOLA_ARCHIVE_PROVIDERS", "telegram").split(",") if x.strip()]
    return [n for n in names if n in PROVIDERS and PROVIDERS[n]().configured()]


def get_provider(name: str) -> ArchiveProvider:
    cls = PROVIDERS.get(name.lower())
    if not cls:
        raise ArchiveError(f"unknown archive provider: {name}")
    return cls()


def _restore_from_existing_archive(blob_hash: str) -> bytes:
    record = storage.get_blob_record(blob_hash)
    if record is None:
        raise ArchiveError("blob metadata not found")
    for item in storage.archive_objects(blob_hash):
        try:
            pointer = ArchivePointer(
                provider=item["provider"], identifier=item.get("identifier", ""),
                message_id=item.get("message_id", ""), file_id=item.get("file_id", ""),
                url=item.get("url", ""),
            )
            return get_provider(pointer.provider).restore(pointer)
        except Exception:
            continue
    # Legacy single-pointer rows are still supported.
    if record.has_cold_pointer and record.archive_provider:
        pointer = ArchivePointer(record.archive_provider, record.archive_identifier or "",
                                 record.archive_message_id or "", record.archive_file_id or "",
                                 record.archive_url or "")
        return get_provider(pointer.provider).restore(pointer)
    raise ArchiveError("no usable archive pointer exists for cold blob")


def archive_blob(blob_hash: str, provider_names: Optional[list[str]] = None) -> list[ArchivePointer]:
    record = storage.get_blob_record(blob_hash)
    if record is None:
        raise ArchiveError("blob metadata not found")
    data = storage.get_blob_bytes(blob_hash)
    if data is None:
        data = _restore_from_existing_archive(blob_hash)
        if storage.hash_bytes(data) != blob_hash:
            raise ArchiveError("archive restore failed SHA-256 verification")
    names = provider_names or configured_provider_names()
    if not names:
        raise ArchiveError("no configured archive providers")
    pointers: list[ArchivePointer] = []
    existing_providers = {x["provider"] for x in storage.archive_objects(blob_hash)}
    for name in names:
        if name in existing_providers:
            continue
        pointer = get_provider(name).archive(blob_hash, data, record.filename or blob_hash, record.mime_type or "application/octet-stream")
        storage.register_archive_ref(blob_hash, pointer.provider, pointer.identifier,
                                     pointer.message_id, pointer.file_id, pointer.url)
        storage.register_archive_object(blob_hash, pointer.provider, pointer.identifier,
                                        pointer.message_id, pointer.file_id, pointer.url)
        pointers.append(pointer)
    return pointers


def status() -> list[dict]:
    result = []
    for name, cls in PROVIDERS.items():
        p = cls()
        result.append({"provider": name, "configured": p.configured()})
    return result
