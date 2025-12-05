import os, requests
from dotenv import load_dotenv
load_dotenv()

resp = requests.get(
    "https://api.trello.com/1/members/me",
    params={"key": os.getenv("TRELLO_API_KEY"), "token": os.getenv("TRELLO_TOKEN")}
)
print(resp.json())
