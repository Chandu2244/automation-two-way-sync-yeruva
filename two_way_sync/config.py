import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Load local development settings from .env when present.
load_dotenv()

# Trello Auth
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_SHORT_ID = os.getenv("TRELLO_BOARD_SHORT_ID")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")

# Google Sheets Auth
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
SHEETS_SHARED_SECRET = os.getenv("SHEETS_SHARED_SECRET")

# Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Database
RAW_DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if RAW_DATABASE_URL.upper().startswith("DATABASE_URL="):
    RAW_DATABASE_URL = RAW_DATABASE_URL.split("=", 1)[1].strip().strip('"').strip("'")

DB_HOST = os.getenv("DB_HOST") or os.getenv("HOST")
DB_PORT = os.getenv("DB_PORT") or os.getenv("PORT") or "5432"
DB_NAME = os.getenv("DB_NAME")
DB_USERNAME = os.getenv("DB_USERNAME") or os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")


def _build_database_url():
    if RAW_DATABASE_URL.startswith(("postgresql://", "postgres://")):
        return RAW_DATABASE_URL
    if all([DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD]):
        username = quote_plus(DB_USERNAME)
        password = quote_plus(DB_PASSWORD)
        return (
            f"postgresql://{username}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            f"?sslmode={DB_SSLMODE}"
        )
    return RAW_DATABASE_URL


DATABASE_URL = _build_database_url()

# Trello List IDs (Status Mapping)
TODO_LIST_ID = os.getenv("TODO_LIST_ID")
IN_PROGRESS_LIST_ID = os.getenv("IN_PROGRESS_LIST_ID")
DONE_LIST_ID = os.getenv("DONE_LIST_ID")


def validate_config():
    """Fail fast when required integration settings are missing."""
    required = {
        "TRELLO_API_KEY": TRELLO_API_KEY,
        "TRELLO_TOKEN": TRELLO_TOKEN,
        "TRELLO_BOARD_SHORT_ID": TRELLO_BOARD_SHORT_ID,
        "TRELLO_BOARD_ID": TRELLO_BOARD_ID,
        "GOOGLE_SHEET_ID": GOOGLE_SHEET_ID,
        "GOOGLE_SERVICE_ACCOUNT_FILE": GOOGLE_SERVICE_ACCOUNT_FILE,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "DATABASE_URL": DATABASE_URL,
        "TODO_LIST_ID": TODO_LIST_ID,
        "IN_PROGRESS_LIST_ID": IN_PROGRESS_LIST_ID,
        "DONE_LIST_ID": DONE_LIST_ID,
    }

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(sorted(missing))
        )
