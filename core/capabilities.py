"""Engola capability registry.

One source of truth for what Engola can actually execute. Integrations may be
configured later; the registry never reports an integration as connected merely
because UI exists.
"""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Capability:
    key: str
    name: str
    description: str
    state: str
    auth: str
    risk: str
    executable: bool = False

CAPABILITIES = [
    Capability("workspace", "Local workspace", "Tasks, memory, history and briefing.", "available", "none", "low", True),
    Capability("web", "Web / browser", "Public web research and source acquisition.", "available", "none", "low", True),
    Capability("termux", "Termux / device", "Authenticated local device bridge.", "not_connected", "pairing", "medium", False),
    Capability("email", "Email", "Read/search mail and prepare messages; sending requires approval.", "not_connected", "oauth", "high", False),
    Capability("calendar", "Calendar", "Read calendar data through an authorized account.", "not_connected", "oauth", "medium", False),
    Capability("github", "GitHub", "Repository, issue, PR and CI operations.", "not_connected", "oauth", "high", False),
    Capability("knowledge", "Knowledge vault", "Store and retrieve owner-approved sources.", "available", "none", "low", True),
    Capability("media", "Media intelligence", "Acquire public media metadata/text where available.", "available", "none", "low", True),
    Capability("external_ai", "External AI", "Optional reasoning provider.", "not_connected", "api_key", "medium", False),
]

def list_capabilities() -> list[dict[str, Any]]:
    return [c.__dict__ for c in CAPABILITIES]

def get_capability(key: str) -> Capability | None:
    return next((c for c in CAPABILITIES if c.key == key), None)
