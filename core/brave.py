"""Brave Search provider for web-grounded Engola answers."""

import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = "https://api.search.brave.com/res/v1"


def _key() -> str:
    return os.getenv("BRAVE_SEARCH_API_KEY", "").strip()


def configured() -> bool:
    return bool(_key())


def _get(path: str, params: str) -> dict:
    key = _key()
    if not key:
        raise RuntimeError("Brave Search is not configured")

    req = Request(
        f"{BASE_URL}/{path}?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
        },
        method="GET",
    )

    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def llm_context(query: str, count: int = 5) -> dict:
    """Return Brave's pre-extracted web context for LLM grounding."""

    query = (query or "").strip()

    if not query:
        return {}

    count = max(1, min(int(count), 20))

    return _get(
        "llm/context",
        f"q={quote(query)}&count={count}&country=UG&search_lang=en",
    )


def search(query: str, count: int = 5) -> list[dict]:
    """Return normalized Brave web results."""

    query = (query or "").strip()

    if not query:
        return []

    count = max(1, min(int(count), 20))

    data = _get(
        "web/search",
        f"q={quote(query)}&count={count}&country=UG&search_lang=en&extra_snippets=true",
    )

    results = data.get("web", {}).get("results", [])

    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "extra_snippets": item.get("extra_snippets", []),
        }
        for item in results
    ]


def answer(messages: list[dict]) -> str:
    """Use Brave's AI-grounded answer endpoint."""

    key = _key()

    if not key:
        raise RuntimeError("Brave Search is not configured")

    payload = json.dumps(
        {
            "messages": messages,
            "model": "brave",
            "stream": False,
        }
    ).encode("utf-8")

    req = Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Subscription-Token": key,
        },
        method="POST",
    )

    with urlopen(req, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))

    choices = data.get("choices") or []

    if not choices:
        raise RuntimeError("Brave returned no answer")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if not content:
        raise RuntimeError("Brave returned an empty answer")

    return str(content).strip()
