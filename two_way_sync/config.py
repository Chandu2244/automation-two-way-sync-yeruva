import os
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
        "TODO_LIST_ID": TODO_LIST_ID,
        "IN_PROGRESS_LIST_ID": IN_PROGRESS_LIST_ID,
        "DONE_LIST_ID": DONE_LIST_ID,
    }

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(sorted(missing))
        )
