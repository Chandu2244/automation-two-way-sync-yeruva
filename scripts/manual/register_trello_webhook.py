"""Manual utility: register Trello webhook for this service."""

import os
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")
CALLBACK_URL = os.getenv("CALLBACK_URL")

URL = "https://api.trello.com/1/webhooks/"


def main():
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idModel": TRELLO_BOARD_ID,
        "callbackURL": CALLBACK_URL,
        "description": "Webhook for Trello -> Google Sheets Sync",
    }

    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.7,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    print("Registering webhook with Trello...")
    try:
        response = session.post(URL, params=params, timeout=(5, 20))
    except RequestException as exc:
        print("Request failed:", str(exc))
        raise SystemExit(1)

    print("Status Code:", response.status_code)
    try:
        print("Response:", response.json())
    except Exception:
        print("Response:", response.text)


if __name__ == "__main__":
    main()
