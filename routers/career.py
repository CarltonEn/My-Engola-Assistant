"""
Career Intelligence router.

Design goals (per MASTER-HANDOFF / BUILD-CONVERSATION requirements):
  * Match scoring is a deterministic, explainable keyword/skill-overlap
    algorithm, not an opaque black box -- the full breakdown is always
    returned alongside the score.
  * There is a hard approval gate before anything can be treated as
    ready to submit: an opportunity must be explicitly approved by the
    authenticated owner, and the 'career_submission' permission must be
    'allow', before it can move past draft/scored state.
  * Engola never claims to have actually submitted an application to an
    external site. No such integration exists yet, so /submit is honest
    about that and only marks the opportunity ready for the owner's own
    manual action.
"""
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.db import db
from core.security import require_owner

router = APIRouter(prefix="/api/career", tags=["career"])

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.#]{1,}")

# Lightweight seniority signal words used only to flag a mismatch for the
# owner to review -- never to silently filter anything out.
_SENIORITY_WORDS = {
    "intern": 0,
    "junior": 1,
    "associate": 2,
    "mid": 3,
    "senior": 4,
    "lead": 5,
    "principal": 6,
    "staff": 6,
    "director": 7,
    "head": 7,
    "chief": 8,
    "vp": 8,
}


def _tokenize(text: str):
    # The word regex allows '.', '+', '#' inside a token so things like
    # "node.js", "c++" and "c#" survive intact, but that means a token at
    # the end of a sentence can pick up a trailing full stop (e.g.
    # "SQLite." -> "sqlite."). Strip trailing punctuation that isn't part
    # of a meaningful suffix.
    tokens = set()
    for w in _WORD_RE.findall(text or ""):
        tokens.add(w.lower().rstrip("."))
    return tokens


def _owner_skill_tokens():
    """Pull skill/profile signal out of owner memory (keys like 'skill:*' or
    'career_profile'). Reads memory rows directly (rather than re-parsing
    the human-readable memory_text() string) so that a colon inside the
    key itself can never be mistaken for part of the value."""
    c = db()
    rows = c.execute(
        "SELECT key,value FROM memories WHERE key='career_profile' OR key LIKE 'skill:%' OR key='skill'"
    ).fetchall()
    c.close()
    tokens = set()
    for _key, value in rows:
        tokens |= _tokenize(value)
    return tokens


def score_opportunity(description: str):
    """Deterministic, explainable scoring. Returns (score_0_100, breakdown)."""
    owner_tokens = _owner_skill_tokens()
    jd_tokens = _tokenize(description)
    if not owner_tokens:
        return 0.0, {
            "reason": "No owner skills found in memory (add entries like 'skill: python, fastapi, tax law').",
            "matched_skills": [],
            "missing_context": True,
        }
    matched = sorted(owner_tokens & jd_tokens)
    overlap_ratio = len(matched) / max(1, len(jd_tokens & owner_tokens | jd_tokens.intersection(owner_tokens)) or 1)
    # Score = fraction of the owner's known skills that appear in the JD,
    # scaled to 0-100. Simple and auditable on purpose.
    coverage = len(matched) / len(owner_tokens) if owner_tokens else 0.0
    score = round(min(coverage, 1.0) * 100, 1)
    seniority_hits = [w for w in _SENIORITY_WORDS if w in jd_tokens]
    breakdown = {
        "matched_skills": matched,
        "owner_skill_count": len(owner_tokens),
        "matched_skill_count": len(matched),
        "coverage_formula": "matched_skill_count / owner_skill_count * 100",
        "seniority_signals_in_description": seniority_hits,
        "missing_context": False,
    }
    return score, breakdown


@router.get("/opportunities")
def list_opportunities(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    c = db()
    rows = c.execute(
        "SELECT id,title,company,url,description,status,score,score_breakdown,created_at,updated_at "
        "FROM career_opportunities ORDER BY id DESC"
    ).fetchall()
    c.close()
    return {
        "opportunities": [
            {
                "id": r[0], "title": r[1], "company": r[2], "url": r[3],
                "description": r[4], "status": r[5], "score": r[6],
                "score_breakdown": r[7], "created_at": r[8], "updated_at": r[9],
            }
            for r in rows
        ]
    }


@router.post("/opportunities")
async def create_opportunity(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    b = await request.json()
    title = (b.get("title") or "").strip()
    description = (b.get("description") or "").strip()
    if not title or not description:
        return JSONResponse({"error": "title and description are required."}, status_code=400)
    company = (b.get("company") or "").strip()
    url = (b.get("url") or "").strip()
    score, breakdown = score_opportunity(description)
    now = time.time()
    c = db()
    cur = c.execute(
        "INSERT INTO career_opportunities(title,company,url,description,status,score,score_breakdown,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (title, company, url, description, "draft", score, str(breakdown), now, now),
    )
    opp_id = cur.lastrowid
    c.commit()
    c.close()
    return {"id": opp_id, "status": "draft", "score": score, "score_breakdown": breakdown}


@router.post("/opportunities/{opp_id}/rescore")
def rescore(opp_id: int, request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    c = db()
    row = c.execute("SELECT description FROM career_opportunities WHERE id=?", (opp_id,)).fetchone()
    if not row:
        c.close()
        return JSONResponse({"error": "Opportunity not found."}, status_code=404)
    score, breakdown = score_opportunity(row[0])
    c.execute(
        "UPDATE career_opportunities SET score=?,score_breakdown=?,updated_at=? WHERE id=?",
        (score, str(breakdown), time.time(), opp_id),
    )
    c.commit()
    c.close()
    return {"id": opp_id, "score": score, "score_breakdown": breakdown}


@router.post("/opportunities/{opp_id}/approve")
async def approve_opportunity(opp_id: int, request: Request):
    """Hard approval gate: requires an authenticated owner, an explicit
    confirm=true in the body, AND the 'career_submission' permission set
    to 'allow'. Any one of these missing blocks approval."""
    denied = require_owner(request)
    if denied:
        return denied
    b = await request.json()
    if b.get("confirm") is not True:
        return JSONResponse(
            {"error": "Explicit confirm:true is required to approve an opportunity for submission."},
            status_code=400,
        )
    c = db()
    perm = c.execute("SELECT status FROM permissions WHERE name='career_submission'").fetchone()
    if not perm or perm[0] != "allow":
        c.close()
        return JSONResponse(
            {
                "error": "The 'career_submission' permission is not set to 'allow'. "
                "Set it via /api/permissions before approving an opportunity."
            },
            status_code=403,
        )
    row = c.execute("SELECT id FROM career_opportunities WHERE id=?", (opp_id,)).fetchone()
    if not row:
        c.close()
        return JSONResponse({"error": "Opportunity not found."}, status_code=404)
    c.execute(
        "UPDATE career_opportunities SET status='approved',updated_at=? WHERE id=?",
        (time.time(), opp_id),
    )
    c.commit()
    c.close()
    return {"id": opp_id, "status": "approved"}


@router.post("/opportunities/{opp_id}/submit")
def submit_opportunity(opp_id: int, request: Request):
    """Never fabricates an external submission. Engola has no integration
    with any job board / ATS today, so this endpoint only validates the
    approval gate and honestly reports that manual action is required."""
    denied = require_owner(request)
    if denied:
        return denied
    c = db()
    row = c.execute("SELECT status FROM career_opportunities WHERE id=?", (opp_id,)).fetchone()
    if not row:
        c.close()
        return JSONResponse({"error": "Opportunity not found."}, status_code=404)
    if row[0] != "approved":
        c.close()
        return JSONResponse(
            {"error": f"Opportunity must be 'approved' first (current status: '{row[0]}')."},
            status_code=409,
        )
    c.execute(
        "UPDATE career_opportunities SET status='ready_for_manual_submission',updated_at=? WHERE id=?",
        (time.time(), opp_id),
    )
    c.commit()
    c.close()
    return {
        "id": opp_id,
        "status": "ready_for_manual_submission",
        "note": "Engola has no configured integration with any job board or ATS, so it cannot "
        "actually submit this application. It is approved and ready for you to submit manually.",
    }
