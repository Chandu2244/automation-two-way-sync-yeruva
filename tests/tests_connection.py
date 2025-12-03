import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import requests

load_dotenv()

# Test Trello Auth
def test_trello():
    print("Testing Trello...")
    url = f"https://api.trello.com/1/members/me?key={os.getenv('TRELLO_API_KEY')}&token={os.getenv('TRELLO_TOKEN')}"
    res = requests.get(url)
    print("Status:", res.status_code)
    print("Response Text:", res.json())  


# Test Google Sheets Auth
def test_sheets():
    print("Testing Google Sheets...")
    creds = Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="Sheet1!A1:E5"
    ).execute()
    print("Sheet Result:", result)

if __name__ == "__main__":
    test_trello()
    test_sheets()
