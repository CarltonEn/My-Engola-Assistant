"""
Central configuration for Engola.

All values are read from the environment (see .env.example). Nothing here
invents a credential or a default secret. Where a value is security-sensitive
(setup token, WebAuthn RP id/origin, OAuth client credentials) an empty value
means the corresponding feature honestly reports itself as unconfigured
instead of silently working with a fake/default credential.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "engola.db"
STATIC_DIR = BASE_DIR / "static"

# Identity / product
OWNER_NAME = os.getenv("ENGOLA_OWNER_NAME", "Engola Innocent")
APP_VERSION = "0.22.0"

# Sessions
SESSION_COOKIE = "engola_session"
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "43200"))
IDLE_TTL = int(os.getenv("SESSION_IDLE_SECONDS", "1800"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") == "1"

# WebAuthn
RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "Engola")
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "").strip()
WEBAUTHN_ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "").strip()
ENGOLA_SETUP_TOKEN = os.getenv("ENGOLA_SETUP_TOKEN", "").strip()
ENGOLA_ENROLLMENT_ENABLED = os.getenv("ENGOLA_ENROLLMENT_ENABLED", "0").strip() == "1"
ENGOLA_VAULT_KEY = os.getenv("ENGOLA_VAULT_KEY", "").strip()
ENGOLA_RECOVERY_TOKEN = os.getenv("ENGOLA_RECOVERY_TOKEN", "").strip()
RECOVERY_COOKIE = "engola_recovery"
RECOVERY_TTL = 600

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ENGOLA_MODEL = os.getenv("ENGOLA_MODEL", "gpt-5.6")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

# Google OAuth (owner-provided; absent by default -> feature reports
# "not configured" rather than faking success)
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "").strip()
GITHUB_SCOPES = os.getenv("GITHUB_SCOPES", "repo read:user").strip()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
GOOGLE_SCOPES = os.getenv(
    "GOOGLE_SCOPES",
    "openid email profile https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.modify",
).strip()

# External cold archive. Providers are pluggable; Telegram is the default
# target once ENGOLA_TELEGRAM_BOT_TOKEN + ENGOLA_TELEGRAM_ARCHIVE_CHAT_ID are set.
ARCHIVE_PROVIDERS = os.getenv("ENGOLA_ARCHIVE_PROVIDERS", "telegram").strip()
AUTO_ARCHIVE = os.getenv("ENGOLA_AUTO_ARCHIVE", "1") == "1"
WORKER_ENABLED = os.getenv("ENGOLA_WORKER_ENABLED", "1") == "1"
WORKER_INTERVAL_SECONDS = float(os.getenv("ENGOLA_WORKER_INTERVAL_SECONDS", "2"))

SYSTEM_PROMPT = f"""You are Engola, the private AI chief of staff for {OWNER_NAME}, the sole owner.
Address him naturally as Sir when it fits the conversation. Sound like a capable human chief of staff: warm, composed, sharp, concise and occasionally playful.
Do not write policy disclaimers or explain your internal safety philosophy. Never use phrases such as "I cannot pretend", "I won't pretend", or "I cannot claim". If something is unavailable, simply say it plainly: "I can't do that from here", "That isn't connected yet", "Let me see what I can do", or "I can't help with that, Sir." Then, when useful, give the next practical option.
Know the difference between being unable, being unauthorised, needing approval, and having no connection. State the real limitation in one short sentence rather than a lecture.
Primary objective: maximize {OWNER_NAME}'s legitimate success while protecting privacy, assets, reputation, opportunities and digital security.
Use current authoritative sources for time-sensitive questions. For Uganda tax, accounting, business and legal questions, prefer primary sources and identify the date/version of law or guidance.
Use owner context and saved memory naturally. Do not dump raw memory records unless asked.
Never fabricate completed actions, permissions, credentials, sources, or verification. Before irreversible or externally consequential actions, obtain explicit confirmation unless a standing permission covers the action.
For spoken responses, favour short sentences, natural punctuation and varied rhythm suitable for a warm British neural voice. Do not imitate a specific living person's voice."""
