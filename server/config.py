"""Central configuration for IB Copilot.

Loads environment variables from the project root `.env`, or — to match the teaching
staff's layout — from one directory above the project root if the root file is missing.
Secrets live only here/on the server; they are never sent to the browser.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # the IB Copilot/ project root
DATA_DIR = ROOT / "data"
GUIDES_DIR = DATA_DIR / "guides"
INDEX_DIR = DATA_DIR / "index"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"
WEB_DIR = ROOT / "web"

# Load .env from the project root first, then fall back to one directory above.
_root_env = ROOT / ".env"
_parent_env = ROOT.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env)
    ENV_SOURCE = str(_root_env)
elif _parent_env.exists():
    load_dotenv(_parent_env)
    ENV_SOURCE = str(_parent_env)
else:
    ENV_SOURCE = None


def _get(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# --- Model / gateway ---
USE_DIRECT_OPENAI = _get("USE_DIRECT_OPENAI", "0") in ("1", "true", "True")
PORTKEY_API_KEY = _get("PORTKEY_API_KEY") or _get("API_PORTKEY_API_KEY")
PORTKEY_BASE_URL = _get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
PORTKEY_PROVIDER = _get("PORTKEY_PROVIDER", "openai")
OPENAI_API_KEY = _get("OPENAI_API_KEY")
MODEL = _get("OPENAI_MODEL", "gpt-6-luna")

# --- Optional integrations ---
NEWS_API_KEY = _get("NEWS_API_KEY")
NEWS_API_PROVIDER = _get("NEWS_API_PROVIDER", "newsapi")
MS_CLIENT_ID = _get("MS_CLIENT_ID")

# --- Model pricing (USD per 1M tokens). CONFIGURABLE. ---
# Source: course pricing for gpt-6-luna (MGT 409, Lecture 11). Dated 2026-10; update
# PRICING if the course rates change. Cost shown in the app is an ESTIMATE from these
# rates applied to the API's own reported token counts (never invented).
PRICING = {
    "gpt-6-luna": {"input_per_1m": 0.10, "cached_input_per_1m": 0.01, "output_per_1m": 0.50},
}
PRICING_SOURCE = "Course pricing for gpt-6-luna (MGT 409, Lecture 11)"
PRICING_DATE = "2026-10"

# --- Safety / cost guardrails ---
MAX_AGENT_STEPS = int(_get("MAX_AGENT_STEPS", "6"))        # bounded agent iterations
MAX_RETRIES = int(_get("MAX_RETRIES", "2"))               # bounded retries per model call
REQUEST_TIMEOUT_S = float(_get("REQUEST_TIMEOUT_S", "60"))
MAX_OUTPUT_TOKENS = int(_get("MAX_OUTPUT_TOKENS", "1600"))
DAILY_RUN_LIMIT = int(_get("DAILY_RUN_LIMIT", "500"))      # configurable usage cap
MAX_UPLOAD_MB = float(_get("MAX_UPLOAD_MB", "20"))
ALLOWED_UPLOAD_EXT = {".pdf", ".docx", ".txt", ".md"}

# --- Tokenomics projection assumptions (explicit, documented) ---
# Used only for PROJECTIONS, clearly separated from measured costs in the UI.
RUNS_PER_USER_PER_DAY = int(_get("RUNS_PER_USER_PER_DAY", "20"))
ACTIVE_DAYS_PER_MONTH = int(_get("ACTIVE_DAYS_PER_MONTH", "20"))


def price_for(model: str) -> dict:
    return PRICING.get(model, PRICING["gpt-6-luna"])


def status() -> dict:
    """Non-secret configuration summary for diagnostics (never returns key values)."""
    return {
        "model": MODEL,
        "gateway": "openai-direct" if USE_DIRECT_OPENAI else "portkey",
        "env_source": ENV_SOURCE,
        "portkey_key_present": bool(PORTKEY_API_KEY),
        "openai_key_present": bool(OPENAI_API_KEY),
        "news_api_configured": bool(NEWS_API_KEY),
        "outlook_configured": bool(MS_CLIENT_ID),
        "pricing_source": PRICING_SOURCE,
        "pricing_date": PRICING_DATE,
        "limits": {
            "max_agent_steps": MAX_AGENT_STEPS,
            "max_retries": MAX_RETRIES,
            "timeout_s": REQUEST_TIMEOUT_S,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "daily_run_limit": DAILY_RUN_LIMIT,
            "max_upload_mb": MAX_UPLOAD_MB,
        },
    }
