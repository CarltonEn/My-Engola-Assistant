"""
Uganda authoritative knowledge-source registry.

A curated, static list of primary Ugandan government/regulatory sources for
tax, legal, business and financial questions, per the SYSTEM prompt's
instruction to "prefer primary sources and identify the date/version of
law or guidance" for Uganda-related questions.

This is deliberately a transparent lookup table, not an AI-generated or
scraped list -- entries should only be added/edited by the owner or a
maintainer who has verified the domain. It does not claim to be exhaustive
or to reflect real-time legal status; last_verified is left for the owner
to maintain.
"""
from fastapi import APIRouter, Request

from core.security import require_owner

router = APIRouter(prefix="/api/uganda", tags=["uganda"])

SOURCES = [
    {
        "name": "Uganda Revenue Authority (URA)",
        "domain": "ura.go.ug",
        "category": "tax",
        "description": "Primary source for tax law, PAYE, VAT, e-filing, and tax practice notes.",
    },
    {
        "name": "Uganda Registration Services Bureau (URSB)",
        "domain": "ursb.go.ug",
        "category": "business_registration",
        "description": "Company registration, business names, intellectual property, chattels.",
    },
    {
        "name": "Bank of Uganda (BoU)",
        "domain": "bou.or.ug",
        "category": "finance",
        "description": "Monetary policy, exchange rates, financial institution regulation.",
    },
    {
        "name": "Ministry of Finance, Planning and Economic Development (MoFPED)",
        "domain": "finance.go.ug",
        "category": "finance",
        "description": "National budget, fiscal policy, public finance management.",
    },
    {
        "name": "Judiciary of Uganda",
        "domain": "judiciary.go.ug",
        "category": "legal",
        "description": "Court judgments, court structure, judicial notices.",
    },
    {
        "name": "Parliament of Uganda",
        "domain": "parliament.go.ug",
        "category": "legal",
        "description": "Bills, Acts of Parliament, Hansard, committee reports.",
    },
    {
        "name": "Uganda Law Reform Commission (ULRC)",
        "domain": "ulrc.go.ug",
        "category": "legal",
        "description": "Law reform reports and consolidated legislation references.",
    },
    {
        "name": "Uganda Investment Authority (UIA)",
        "domain": "ugandainvest.go.ug",
        "category": "business",
        "description": "Investment licensing, incentives, and sector guides for investors.",
    },
    {
        "name": "National Social Security Fund (NSSF Uganda)",
        "domain": "nssfug.org",
        "category": "labour",
        "description": "Social security contributions and benefits for employees/employers.",
    },
    {
        "name": "Uganda National Bureau of Standards (UNBS)",
        "domain": "unbs.go.ug",
        "category": "standards",
        "description": "Product/service standards, certification and compliance.",
    },
]

# Keywords used only to decide whether a chat/study prompt should be told
# to consider these sources -- a transparent heuristic, not a claim that
# the model actually browsed them.
TRIGGER_KEYWORDS = {
    "uganda", "ugandan", "ura", "ursb", "kampala", "shilling", "ugx",
    "paye", "nssf", "bou",
}


def relevant_sources(text: str, category: str = None):
    text_l = (text or "").lower()
    triggered = any(k in text_l for k in TRIGGER_KEYWORDS)
    results = SOURCES
    if category:
        results = [s for s in results if s["category"] == category]
    return triggered, results


@router.get("/sources")
def list_sources(request: Request, category: str = None):
    denied = require_owner(request)
    if denied:
        return denied
    results = SOURCES if not category else [s for s in SOURCES if s["category"] == category]
    categories = sorted({s["category"] for s in SOURCES})
    return {"sources": results, "categories": categories}


@router.get("/relevant")
def check_relevant(request: Request, text: str = ""):
    denied = require_owner(request)
    if denied:
        return denied
    triggered, results = relevant_sources(text)
    return {"uganda_relevant": triggered, "suggested_sources": results if triggered else []}
