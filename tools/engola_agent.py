#!/usr/bin/env python3
"""Cross-platform outbound Engola worker.

Works on Termux/Android, Linux and Windows with Python's standard library.
The worker opens only outbound HTTPS connections. It executes only approved
jobs received from Engola and reports a bounded result.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CONFIG = Path(os.getenv("ENGOLA_AGENT_CONFIG", str(Path.home() / ".engola-agent.json")))
MAX_OUTPUT = 18000
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_TELEGRAM = 49 * 1024 * 1024


def load():
    data = {}
    if CONFIG.exists():
        data = json.loads(CONFIG.read_text())
    data.update({k: v for k, v in {
        "url": os.getenv("ENGOLA_URL"),
        "token": os.getenv("ENGOLA_DEVICE_TOKEN"),
        "poll_seconds": os.getenv("ENGOLA_AGENT_POLL_SECONDS"),
        "workdir": os.getenv("ENGOLA_AGENT_WORKDIR"),
    }.items() if v})
    if not data.get("url") or not data.get("token"):
        raise SystemExit("Set ENGOLA_URL and ENGOLA_DEVICE_TOKEN or create ~/.engola-agent.json")
    parsed = urlparse(str(data["url"]))
    if parsed.scheme != "https":
        raise SystemExit("ENGOLA_URL must use HTTPS")
    data["poll_seconds"] = max(5, int(data.get("poll_seconds", 8)))
    data["workdir"] = data.get("workdir") or str(Path.home())
    return data


def post(cfg, path, payload):
    req = Request(
        cfg["url"].rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Engola-Device-Token": cfg["token"],
            "User-Agent": "Engola-Agent/0.19",
        },
        method="POST",
    )
    with urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def heartbeat(cfg):
    payload = {
        "name": platform.node() or "Engola agent",
        "platform": sys.platform,
        "model": platform.machine(),
        "android_version": "",
        "capabilities": "shell,download,telegram_upload",
    }
    try:
        return post(cfg, "/api/device/heartbeat", payload)
    except Exception:
        return None


def execute(cfg, command):
    kind = command["kind"]
    payload = command.get("payload") or {}
    if kind == "shell":
        cmd = str(payload.get("command") or "").strip()
        if not cmd:
            raise ValueError("empty shell command")
        timeout = max(1, min(int(payload.get("timeout", 120)), 600))
        p = subprocess.run(
            cmd, shell=True, cwd=payload.get("cwd") or cfg["workdir"],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "exit_code": p.returncode,
            "stdout": p.stdout[-MAX_OUTPUT:],
            "stderr": p.stderr[-MAX_OUTPUT:],
            "host": platform.node(),
            "platform": platform.platform(),
        }

    if kind == "download":
        url = str(payload.get("url") or "").strip()
        dest = Path(str(payload.get("path") or "")).expanduser()
        if urlparse(url).scheme not in {"http", "https"} or not str(dest):
            raise ValueError("download requires http(s) URL and path")
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with urlopen(Request(url, headers={"User-Agent": "Engola-Agent/0.19"}), timeout=60) as r, dest.open("wb") as f:
            declared = int(r.headers.get("Content-Length") or 0)
            if declared > MAX_DOWNLOAD:
                raise ValueError("download exceeds 100MB limit")
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError("download exceeds 100MB limit")
                f.write(chunk)
        return {"path": str(dest), "bytes": total}

    if kind == "telegram_upload":
        path = Path(str(payload.get("path") or "")).expanduser()
        token = os.getenv("ENGOLA_TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("ENGOLA_TELEGRAM_ARCHIVE_CHAT_ID")
        if not token or not chat_id:
            raise ValueError("Telegram archive is not configured on this agent")
        if not path.exists() or not path.is_file():
            raise ValueError("file missing")
        size = path.stat().st_size
        if size > MAX_TELEGRAM:
            raise ValueError("file exceeds Telegram Bot API limit")
        # Stream multipart data directly to the HTTPS connection instead of
        # loading the whole file into memory.
        import http.client
        from urllib.parse import urlsplit
        boundary = "----EngolaBoundary" + os.urandom(8).hex()
        prefix = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
            f"{chat_id}\r\n--{boundary}\r\nContent-Disposition: form-data; "
            f"name=\"document\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()
        target = urlsplit(f"https://api.telegram.org/bot{token}/sendDocument")
        conn = http.client.HTTPSConnection(target.netloc, timeout=90)
        conn.putrequest("POST", target.path)
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(len(prefix) + size + len(suffix)))
        conn.endheaders()
        conn.send(prefix)
        with path.open("rb") as f:
            while True:
                chunk = f.read(256 * 1024)
                if not chunk:
                    break
                conn.send(chunk)
        conn.send(suffix)
        response = conn.getresponse()
        raw = response.read().decode(errors="replace")
        conn.close()
        result = json.loads(raw)
        if response.status >= 400 or not result.get("ok"):
            raise RuntimeError("Telegram upload failed")
        return {"telegram_ok": True, "file": str(path), "bytes": size}

    raise ValueError("unsupported command type")


def run_once(cfg):
    heartbeat(cfg)
    response = post(cfg, "/api/device/commands/poll", {"limit": 3})
    for command in response.get("commands", []):
        try:
            result = execute(cfg, command)
            status = "completed"
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
            status = "failed"
        try:
            post(cfg, "/api/device/commands/complete", {
                "command_id": command["command_id"],
                "status": status,
                "result": result,
            })
        except Exception as exc:
            print(f"Engola agent completion report failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    args = parser.parse_args()
    cfg = load()
    while True:
        try:
            run_once(cfg)
        except Exception as exc:
            print(f"Engola agent: {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.once:
            return
        time.sleep(cfg["poll_seconds"])


if __name__ == "__main__":
    main()
