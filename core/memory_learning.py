"""
Automatic memory learning.

After a real conversational exchange (i.e. one where an actual reasoning
provider produced the answer -- not a local command, not the honest
"unavailable" fallback), this asks the SAME provider that just answered to
look back at the exchange and pull out any durable facts worth remembering
long-term (preferences, decisions, ongoing projects, corrections), then
saves them to the existing `memories` table -- the same one the owner can
already see and delete from in the Memory tab.

Honesty rules, matching the rest of this codebase:
  * If no reasoning provider is available, this does nothing -- it never
    invents a memory.
  * The extraction prompt explicitly forbids inventing facts not actually
    present in the exchange, and forbids re-saving something already in
    memory (reduces, though does not perfectly eliminate, duplicate growth
    under a different key -- a known, acceptable limitation for v1).
  * This never raises -- a failure here must never break or delay the
    chat response the owner is waiting on. It is meant to be run via
    FastAPI's BackgroundTasks, after the response has already been sent.
"""
import json
import re

from core import ai
from core.db import memory_text, remember
from core.gemini import configured as gemini_configured, respond as gemini_respond
from core.brave import configured as brave_configured, answer as brave_answer

MAX_FACTS_PER_EXCHANGE = 5

EXTRACTION_PROMPT = """You are Engola's memory curator, not the conversational assistant.
Given one exchange between the owner and Engola, decide whether it contains any
NEW durable fact worth remembering long-term: a stated preference, a decision made,
an ongoing project detail, a correction the owner gave, or similar general knowledge
about the owner or their world.

Rules:
- Only include facts actually stated in this exchange. Never invent or infer beyond
  what was said.
- Do not include anything already covered by the existing memory listed below.
- Do not include small talk, the question itself, or anything transient (mood,
  today's weather, this single message's topic) that will not matter later.
- Return at most {max_facts} facts.
- Respond with ONLY a JSON array, no markdown fences, no commentary. Each item:
  {{"key": "short_snake_case_key", "value": "the fact, in a few words"}}
- If nothing durable was stated, return exactly: []

Existing memory (do not repeat these):
{existing}

Exchange:
Owner: {user_text}
Engola: {answer_text}
"""


def _parse_facts(raw: str):
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except Exception:
        # Best-effort recovery: pull the first [...] block out of a noisier reply.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    facts = []
    for item in data[:MAX_FACTS_PER_EXCHANGE]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            facts.append((key, value))
    return facts


def extract_and_remember(user_text: str, answer_text: str) -> None:
    """Best-effort. Never raises. Call via FastAPI BackgroundTasks."""
    try:
        if not (user_text or "").strip() or not (answer_text or "").strip():
            return

        prompt = EXTRACTION_PROMPT.format(
            max_facts=MAX_FACTS_PER_EXCHANGE,
            existing=memory_text(limit=200) or "(none yet)",
            user_text=user_text.strip()[:2000],
            answer_text=answer_text.strip()[:2000],
        )
        messages = [{"role": "user", "content": prompt}]

        raw = None
        if ai.is_configured():
            try:
                raw = ai.respond(messages, tools=[])
            except Exception:
                raw = None
        if raw is None and gemini_configured():
            try:
                raw = gemini_respond(messages)
            except Exception:
                raw = None
        if raw is None and brave_configured():
            try:
                raw = brave_answer(messages)
            except Exception:
                raw = None
        if raw is None:
            return

        for key, value in _parse_facts(raw):
            remember(key, value)
    except Exception:
        # Learning is additive and must never affect the conversation itself.
        return
