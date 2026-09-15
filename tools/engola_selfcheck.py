#!/usr/bin/env python3
"""Dependency-light structural self-check for a deployed Engola checkout."""
from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parents[1]
required = [
    "main.py", "core/config.py", "core/db.py", "core/security.py",
    "core/agent.py", "core/knowledge.py", "core/command_bridge.py",
    "routers/chat.py", "routers/device.py", "routers/device_commands.py",
    "routers/voice_natural.py", "routers/system_status.py",
    "tools/engola_agent.py",
]
missing = [p for p in required if not (ROOT / p).exists()]
if missing:
    print("MISSING:", ", ".join(missing))
    sys.exit(1)

errors = []
for rel in required:
    try:
        ast.parse((ROOT / rel).read_text(), filename=rel)
    except Exception as exc:
        errors.append(f"{rel}: {type(exc).__name__}: {exc}")

if errors:
    print("\n".join(errors))
    sys.exit(1)

main = (ROOT / "main.py").read_text()
for marker in ("device_commands.router", "system_status.router"):
    if marker not in main:
        errors.append(f"main.py missing router registration: {marker}")

if errors:
    print("\n".join(errors))
    sys.exit(1)

print("ENGOLA STRUCTURAL SELFCHECK OK")
