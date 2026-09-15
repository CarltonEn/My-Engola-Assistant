#!/usr/bin/env python3
"""Engola Android/Termux companion.

Pair once using the 8-character code shown by Engola, then run this script.
It sends only device telemetry; it does not execute remote commands.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path.home() / ".engola-companion.json"
INTERVAL = 30


def run_json(command):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if p.returncode != 0:
            return None
        return json.loads(p.stdout)
    except Exception:
        return None


def run_text(command):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def device_model():
    return run_text(["getprop", "ro.product.model"]) or "Android device"


def android_version():
    return run_text(["getprop", "ro.build.version.release"])


def telemetry():
    battery = run_json(["termux-battery-status"]) or {}
    wifi = run_json(["termux-wifi-connectioninfo"]) or {}
    usage = shutil.disk_usage(str(Path.home()))
    charging = str(battery.get("status", "")).upper() in {"CHARGING", "FULL"} or str(battery.get("plugged", "")).upper() not in {"", "UNPLUGGED", "NONE"}
    return {
        "name": CONFIG.read_text().strip() if False else os.environ.get("ENGOLA_DEVICE_NAME", "Android device"),
        "platform": "android",
        "model": device_model(),
        "android_version": android_version(),
        "battery_pct": battery.get("percentage"),
        "charging": charging,
        "network_type": "wifi" if wifi.get("supplicant_state") == "COMPLETED" or wifi.get("connection_state") == "COMPLETED" else "",
        "network_name": wifi.get("ssid") or "",
        "storage_free": usage.free,
        "storage_total": usage.total,
        "capabilities": ",".join(x for x in [
            "battery" if battery else "",
            "wifi" if wifi else "",
            "storage",
            "termux-api" if shutil.which("termux-battery-status") else "",
        ] if x),
    }


def request(url, payload, token=None):
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Engola-Android-Companion/0.12"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2))
    try:
        os.chmod(CONFIG, 0o600)
    except OSError:
        pass


def main():
    base = (os.environ.get("ENGOLA_URL") or "").rstrip("/")
    if not base:
        print("Set ENGOLA_URL first, e.g. https://your-engola.up.railway.app")
        return 2

    cfg = None
    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text())
        except Exception:
            cfg = None

    if not cfg:
        code = (os.environ.get("ENGOLA_PAIR_CODE") or "").strip().upper()
        if not code:
            print("Set ENGOLA_PAIR_CODE to the 8-character code shown in Engola.")
            return 2
        name = os.environ.get("ENGOLA_DEVICE_NAME") or device_model()
        result = request(base + "/api/device/pair/claim", {"code": code, "name": name, "platform": "android"})
        cfg = {"device_id": result["device_id"], "device_token": result["device_token"], "name": name}
        save_config(cfg)
        print("Engola companion paired. Token saved in ~/.engola-companion.json")

    token = cfg["device_token"]
    print("Engola companion running. Ctrl+C to stop.")
    while True:
        try:
            payload = telemetry()
            payload["name"] = cfg.get("name") or payload["name"]
            result = request(base + "/api/device/heartbeat", payload, token)
            print("heartbeat", result.get("last_seen"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            print("heartbeat failed:", exc)
        except KeyboardInterrupt:
            print("Stopped.")
            return 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
