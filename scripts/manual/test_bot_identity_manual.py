"""Manual utility: print Trello bot identity for current token."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()


def main():
    response = requests.get(
        "https://api.trello.com/1/members/me",
        params={"key": os.getenv("TRELLO_API_KEY"), "token": os.getenv("TRELLO_TOKEN")},
        timeout=(5, 20),
    )
    print(response.json())


if __name__ == "__main__":
    main()
