"""
Central configuration. Everything secret comes from environment variables
(loaded from a .env file next to this script). Nothing sensitive is hardcoded.

Copy .env.example to .env and fill it in.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Gemini ---------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Confirm the exact string in Google AI Studio -> it changes per release.
# Flash free-tier candidates: gemini-3.6-flash, gemini-flash-latest, gemini-2.5-flash
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# --- Telegram -------------------------------------------------------------
# Get the token from @BotFather. Get your chat id by messaging the bot once
# and reading it from the first update (the code prints it on startup).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # your own user id

# --- Behaviour ------------------------------------------------------------
# How many new applications the agent is allowed to queue per run. A hard
# brake so a scraper bug can't fire 300 letters at you.
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "5"))
# Run the scrape cycle every N hours (also runs once at startup).
CYCLE_HOURS = float(os.environ.get("CYCLE_HOURS", "24"))

# --- Your identity (top of the PDF letter) --------------------------------
FULL_NAME = os.environ.get("FULL_NAME", "")
EMAIL = os.environ.get("EMAIL", "")
PHONE = os.environ.get("PHONE", "")
CITY = os.environ.get("CITY", "")

# --- Paths ----------------------------------------------------------------
FACTS_FILE = BASE_DIR / "facts.txt"      # your CV as plain text (the source of truth)
DB_FILE = BASE_DIR / "agent.db"          # sqlite state store
OUT_DIR = BASE_DIR / "letters"           # rendered PDFs land here
OUT_DIR.mkdir(exist_ok=True)


def check() -> list[str]:
    """Return a list of missing-config problems (empty == good to go)."""
    problems = []
    if not GEMINI_API_KEY:
        problems.append("GEMINI_API_KEY is empty (.env)")
    if not TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN is empty (.env)")
    if not FACTS_FILE.exists() or FACTS_FILE.read_text().strip().startswith("<<<"):
        problems.append("facts.txt not filled in (paste your CV as plain text)")
    return problems


# --- applicant details for the apply form (from .env) ---
APPLICANT_FIRST_NAME = os.environ.get("APPLICANT_FIRST_NAME", "")
APPLICANT_LAST_NAME = os.environ.get("APPLICANT_LAST_NAME", "")
APPLICANT_EMAIL = os.environ.get("APPLICANT_EMAIL", "")
APPLICANT_PHONE = os.environ.get("APPLICANT_PHONE", "")
