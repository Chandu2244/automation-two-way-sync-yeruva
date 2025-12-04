import os
import requests
from dotenv import load_dotenv

# Load .env file
load_dotenv()

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")
CALLBACK_URL = os.getenv("CALLBACK_URL")  # like https://abcd.ngrok-free.app/trello-webhook

url = "https://api.trello.com/1/webhooks/"

params = {
    "key": TRELLO_API_KEY,
    "token": TRELLO_TOKEN,
    "idModel": TRELLO_BOARD_ID,
    "callbackURL": CALLBACK_URL,
    "description": "Webhook for Trello → Google Sheets Sync"
}

print("📡 Registering webhook with Trello...")
response = requests.post(url, params=params)

print("Status Code:", response.status_code)
try:
    print("Response:", response.json())
except:
    print("Response:", response.text)
