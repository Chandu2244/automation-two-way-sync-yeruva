import requests
from two_way_sync.config import (
    TRELLO_API_KEY,
    TRELLO_TOKEN,
    TRELLO_BOARD_ID,
    TODO_LIST_ID,
    IN_PROGRESS_LIST_ID,
    DONE_LIST_ID
)
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.utils.logger import log_info, log_error


class TrelloClient:
    BASE_URL = "https://api.trello.com/1"

    STATUS_TO_LIST = {
        "TODO": TODO_LIST_ID,
        "IN_PROGRESS": IN_PROGRESS_LIST_ID,
        "DONE": DONE_LIST_ID,
    }

    LIST_TO_STATUS = {
        TODO_LIST_ID: "TODO",
        IN_PROGRESS_LIST_ID: "IN_PROGRESS",
        DONE_LIST_ID: "DONE",
    }

    def __init__(self):
        self.auth = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
        self.store = MappingStore()
        self.custom_fields = {}  # Cache field IDs

    # ------------------------------------------------
    # Custom Field Utilities
    # ------------------------------------------------
    def _get_custom_field_id(self, field_name):
        if field_name in self.custom_fields:
            return self.custom_fields[field_name]

        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_ID}/customFields"
        res = requests.get(url, params=self.auth)

        if res.status_code != 200:
            log_error(f"❌ Failed fetch custom fields: {res.text}")
            return None

        for field in res.json():
            if field["name"].strip().lower() == field_name.lower():
                self.custom_fields[field_name] = field["id"]
                return field["id"]

        log_error(f"⚠ Custom field missing: {field_name}")
        return None

    def set_custom_field(self, card_id, field_name, value):
        field_id = self._get_custom_field_id(field_name)
        if not field_id:
            return False

        url = f"{self.BASE_URL}/card/{card_id}/customField/{field_id}/item"
        body = {"value": {"text": value}}
        res = requests.put(url, params=self.auth, json=body)

        if res.status_code != 200:
            log_error(f"❌ Failed set field {field_name}: {res.text}")
            return False

        return True

    # ------------------------------------------------
    # Create / Update Cards
    # ------------------------------------------------
    def create_card(self, name, lead_id, status="TODO", email=""):
        list_id = self.STATUS_TO_LIST.get(status, TODO_LIST_ID)

        url = f"{self.BASE_URL}/cards"
        params = {**self.auth, "name": name, "idList": list_id}
        res = requests.post(url, params=params)

        if res.status_code != 200:
            log_error(f"❌ Create card failed: {res.text}")
            return False

        card = res.json()

        # Attach metadata
        self.set_custom_field(card["id"], "lead_id", lead_id)
        if email:
            self.set_custom_field(card["id"], "email", email)

        self.store.upsert(
            lead_id,
            trello_card_id=card["id"],
            trello_status=status,
            trello_timestamp=card["dateLastActivity"],
        )

        log_info(f"🆕 Card Created for {lead_id} → {status}")
        return card

    def sync_card_for_lead(self, name, lead_id, status, email=""):
        mapping = self.store.get(lead_id)

        if mapping and mapping.get("trello_card_id"):
            return self.update_status(mapping["trello_card_id"], status, lead_id)

        return self.create_card(name, lead_id, status, email)

    def update_status(self, card_id, status, lead_id):
        list_id = self.STATUS_TO_LIST.get(status)
        url = f"{self.BASE_URL}/cards/{card_id}"
        params = {**self.auth, "idList": list_id}
        res = requests.put(url, params=params)

        if res.status_code != 200:
            log_error(f"❌ Move card failed: {res.text}")
            return False

        card = res.json()

        self.store.upsert(
            lead_id,
            trello_status=status,
            trello_timestamp=card["dateLastActivity"],
        )

        log_info(f"♻ Status Updated: {lead_id} → {status}")
        return card

    # ------------------------------------------------
    # Archive Support
    # ------------------------------------------------
    def archive_card(self, card_id):
        url = f"{self.BASE_URL}/cards/{card_id}"
        params = {**self.auth, "closed": "true"}

        res = requests.put(url, params=params)
        if res.status_code != 200:
            log_error(f"❌ Archive failed: {res.text}")
            return False

        log_info(f"🗑 Archived card {card_id}")
        return True

    # ------------------------------------------------
    # Read / Reverse Sync Helpers
    # ------------------------------------------------
    def _get_field_value(self, card_id, field_name):
        field_id = self._get_custom_field_id(field_name)
        if not field_id:
            return None

        url = f"{self.BASE_URL}/cards/{card_id}/customFieldItems"
        res = requests.get(url, params=self.auth)

        if res.status_code != 200:
            return None

        for item in res.json():
            if item["idCustomField"] == field_id:
                return item["value"]["text"]

        return None

    def get_cards_with_lead_and_status(self):
        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_ID}/cards"
        res = requests.get(url, params=self.auth)

        if res.status_code != 200:
            log_error(f"❌ Failed fetch cards: {res.text}")
            return []

        cards = []
        for card in res.json():
            lead_id = self._get_field_value(card["id"], "lead_id")
            if not lead_id:
                continue

            status = self.LIST_TO_STATUS.get(card["idList"])
            if not status:
                continue

            cards.append({
                "lead_id": lead_id,
                "status": status,
                "trello_timestamp": card.get("dateLastActivity")
            })

        log_info(f"🔍 Reverse Sync Found {len(cards)} mapped Trello cards")
        return cards
