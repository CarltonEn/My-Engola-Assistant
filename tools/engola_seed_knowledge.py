#!/usr/bin/env python3
"""Acquire Engola's starter knowledge set from a checked-in manifest.

Uses the existing engola_knowledge.py helper when present, so originals can be
archived to Telegram and extracted text can be imported into the vault.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "knowledge" / "seed_sources.json"
HELPER = ROOT / "tools" / "engola_knowledge.py"


def main():
    if not HELPER.exists():
        raise SystemExit(f"Missing helper: {HELPER}")
    items = json.loads(MANIFEST.read_text())
    selected = sys.argv[1:]
    for item in items:
        if selected and item["category"] not in selected:
            continue
        cmd = [
            sys.executable, str(HELPER), item["url"],
            "--title", item["title"],
            "--category", item["category"],
            "--authority", item["authority"],
        ]
        if os.getenv("ENGOLA_TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("ENGOLA_TELEGRAM_CHAT_ID", "").strip():
            cmd.append("--archive")
        env = os.environ.copy()
        print(f"[engola] acquiring: {item['title']}")
        subprocess.run(cmd, env=env, check=False)


if __name__ == "__main__":
    main()
