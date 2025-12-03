import os
from dotenv import load_dotenv

load_dotenv()

# Trello Auth
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")

# Google Sheets Auth
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

# Trello List IDs (Status Mapping)
TODO_LIST_ID = os.getenv("TODO_LIST_ID")
IN_PROGRESS_LIST_ID = os.getenv("IN_PROGRESS_LIST_ID")
DONE_LIST_ID = os.getenv("DONE_LIST_ID")
