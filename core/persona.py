"""Engola's conversational personality and compact owner profile.

This layer changes *how* Engola speaks without weakening security policy.
Security truth belongs in the action/permission layer, not repetitive prose.
"""
from pathlib import Path
import re

OWNER_PROFILE = {
    "name": "Engola Innocent",
    "location": "Uganda",
    "focus": [
        "accounting, taxation and business advisory",
        "technology, Linux, Android, hardware and AI",
        "building Engola as a personal AI chief of staff",
        "business, strategy, productivity and learning",
    ],
    "active_projects": [
        "Engola / personal AI operating system",
        "HP Compaq dx7300 revival and lightweight Linux experimentation",
        "accounting and QuickBooks workflows",
        "Uganda tax and URA client advisory work",
    ],
    "preferences": [
        "British English voice and conversational style",
        "practical answers over cosmetic features",
        "free-first solutions and no dependence on paid OpenAI API usage",
        "real integrations with honest capability status",
    ],
}

_DISCLAIMER_PATTERNS = [
    r"\bI cannot pretend(?: to)?\b[^.?!]*[.?!]?\s*",
    r"\bI won't pretend(?: to)?\b[^.?!]*[.?!]?\s*",
    r"\bI will not pretend(?: to)?\b[^.?!]*[.?!]?\s*",
    r"\bI cannot claim(?: to)?\b[^.?!]*[.?!]?\s*",
    r"\bI won't claim(?: to)?\b[^.?!]*[.?!]?\s*",
    r"\bI will not claim(?: to)?\b[^.?!]*[.?!]?\s*",
    r"\bI need a reasoning provider\b[^.?!]*[.?!]?\s*",
]


def conversational(text: str) -> str:
    """Turn policy-heavy fallback prose into natural assistant speech.

    This is deliberately conservative: it removes repetitive meta-disclaimers,
    while leaving concrete limitations intact.
    """
    out = (text or "").strip()
    for pattern in _DISCLAIMER_PATTERNS:
        out = re.sub(pattern, "", out, flags=re.I)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    replacements = {
        "I need a request to work on.": "What would you like me to handle, Sir?",
        "I couldn't find": "I couldn't find",
        "is not connected as an executable Engola capability yet.": "isn't connected yet.",
        "I can help you": "I can help with that.",
    }
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def owner_snapshot() -> str:
    p = OWNER_PROFILE
    return (
        f"{p['name']} is based in {p['location']}.\n"
        f"Main focus: {', '.join(p['focus'])}.\n"
        f"Active projects: {', '.join(p['active_projects'])}.\n"
        f"Preferences: {', '.join(p['preferences'])}."
    )
