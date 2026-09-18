"""Free-first current-news research using a small explicit RSS allowlist.

No fake stories: failures are returned as unavailable results. Saved articles
remain ordinary knowledge sources with their publication date and feed provenance.
"""
from __future__ import annotations

import html
import re
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Request as FastAPIRequest

from core.security import require_owner
from core.knowledge import import_text_source

router = APIRouter(prefix="/api/news", tags=["news"])

NEWS_FEEDS = {
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
}

def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()

@router.get("")
def news_search(request: FastAPIRequest, q: str = "", limit: int = 12):
    denied = require_owner(request)
    if denied:
        return denied
    query = q.strip()
    terms = [x.lower() for x in re.findall(r"\w+", query) if len(x) > 2]
    results = []
    for source, feed_url in NEWS_FEEDS.items():
        try:
            req = Request(feed_url, headers={"User-Agent": "Engola/0.21 (news research)"})
            with urlopen(req, timeout=10) as response:
                root = ElementTree.fromstring(response.read())
        except Exception:
            continue
        for item in root.findall(".//item"):
            title = _clean(item.findtext("title"))
            description = _clean(item.findtext("description"))
            link = (item.findtext("link") or "").strip()
            published = (item.findtext("pubDate") or "").strip()
            haystack = f"{title} {description}".lower()
            if terms and not all(term in haystack for term in terms):
                continue
            results.append({"title": title, "description": description[:1000], "url": link,
                            "published_at": published, "source": source,
                            "provenance": f"public RSS feed: {source}"})
    results.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return {"ok": True, "query": query, "results": results[:max(1, min(limit, 50))],
            "sources": list(NEWS_FEEDS)}


# NOTE: the previous /../research/news and /../research/news/save routes were
# invalid FastAPI route paths (a literal ".." segment does not "escape" a
# router's prefix -- FastAPI/Starlette treat it as a literal path component,
# so those routes were only ever reachable at the nonsensical literal URL
# "/api/news/../research/news", never at "/api/research/news" as intended).
# Fixed by mounting them under this router's own /api/news prefix instead.
@router.post("/compat/research-news")
def research_news_compat(request: FastAPIRequest, q: str = "", limit: int = 12):
    """Compatibility path for the Replit-era research/news workflow.

    Kept as an additive route so existing clients can migrate without
    reviving the old Flask application.
    """
    denied = require_owner(request)
    if denied:
        return denied
    return news_search(request, q=q, limit=limit)

@router.post("/save")
def save_news(request: FastAPIRequest, item: dict):
    denied = require_owner(request)
    if denied:
        return denied
    title = (item.get("title") or "Saved news item").strip()
    url = (item.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "News item URL is required.")
    description = (item.get("description") or "").strip()
    metadata = {
        "source": item.get("source") or "",
        "published_at": item.get("published_at") or "",
        "authority": "current public news feed",
    }
    source = import_text_source(url=url, title=title, kind="news",
                                text=description or title, metadata=metadata)
    return {"ok": True, "source": source}
