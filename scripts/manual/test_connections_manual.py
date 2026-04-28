"""Manual utility: verify Trello and Google Sheets connectivity."""

import os
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

load_dotenv()


def test_trello():
    print("Testing Trello...")
    url = (
        "https://api.trello.com/1/members/me"
        f"?key={os.getenv('TRELLO_API_KEY')}&token={os.getenv('TRELLO_TOKEN')}"
    )
    response = requests.get(url, timeout=(5, 20))
    print("Status:", response.status_code)
    print("Response Text:", response.json())


def test_sheets():
    print("Testing Google Sheets...")
    creds = Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="Sheet1!A1:E5",
    ).execute()
    print("Sheet Result:", result)


if __name__ == "__main__":
    test_trello()
    test_sheets()
