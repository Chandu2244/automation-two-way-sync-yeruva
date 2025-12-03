import requests
from two_way_sync.config import (
    TRELLO_API_KEY,
    TRELLO_TOKEN,
    TRELLO_BOARD_ID,
    TODO_LIST_ID,
    IN_PROGRESS_LIST_ID,
    DONE_LIST_ID
)
from two_way_sync.utils.logger import log_info, log_error
from two_way_sync.db.mapping_store import MappingStore



class TrelloClient:
    BASE_URL = "https://api.trello.com/1"

    # Status mapping (Single Source of Truth)
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
        self.auth_params = {
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
        }
        self.lead_field_id = None  # custom field id for lead_id
        self.email_field_id = None  # custom field id for email
        self.mapping_store = MappingStore()

    # ------------------------------------------------
    # Custom Field Lookups
    # ------------------------------------------------
    def _get_custom_field_id_by_name(self, field_name):
        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_ID}/customFields"
        res = requests.get(url, params=self.auth_params)

        if res.status_code != 200:
            log_error(f"Failed to fetch custom fields: {res.text}")
            return None

        for field in res.json():
            if field["name"].strip().lower() == field_name.lower():
                return field["id"]

        log_error(f"Custom field '{field_name}' not found!")
        return None

    def _get_lead_id_field(self):
        if not self.lead_field_id:
            self.lead_field_id = self._get_custom_field_id_by_name("lead_id")
        return self.lead_field_id

    def _get_email_field(self):
        if not self.email_field_id:
            self.email_field_id = self._get_custom_field_id_by_name("email")
        return self.email_field_id

    # ------------------------------------------------
    # Create / Update Cards
    # ------------------------------------------------
    def create_card(self, name, lead_id, status="TODO", email=""):
        list_id = self.STATUS_TO_LIST.get(status, TODO_LIST_ID)

        url = f"{self.BASE_URL}/cards"
        params = {
            **self.auth_params,
            "name": name,   # Only name in card title
            "idList": list_id,
        }

        res = requests.post(url, params=params)
        if res.status_code == 200:
            card = res.json()

            # Set custom fields
            self.set_lead_id(card["id"], lead_id)
            self.set_email(card["id"], email)

            self.mapping_store.upsert(
            lead_id,
            trello_card_id=card["id"],
            trello_status=status,
            trello_timestamp=card["dateLastActivity"]
            )
            log_info(f"Created card for lead {lead_id} in {status}")
            return card

        log_error(f"Failed to create card: {res.text}")
        return None

    def sync_card_for_lead(self, name, lead_id, status="TODO", email=""):
        mapping = self.mapping_store.get(lead_id)
        if mapping and mapping.get("trello_card_id"):
            card_id = mapping["trello_card_id"]
            self.update_status(card_id, status, lead_id)
            return


        return self.create_card(name, lead_id, status, email)

    def update_status(self, card_id, status, lead_id):
        list_id = self.STATUS_TO_LIST.get(status)
        url = f"{self.BASE_URL}/cards/{card_id}"
        params = {**self.auth_params, "idList": list_id}
        res = requests.put(url, params=params)

        if res.status_code == 200:
            card = res.json()
            self.mapping_store.upsert(
                lead_id,
                trello_status=status,
                trello_timestamp=card["dateLastActivity"],
            )

    # ------------------------------------------------
    # Custom Field Setting
    # ------------------------------------------------
    def set_lead_id(self, card_id, lead_id):
        field_id = self._get_lead_id_field()
        if not field_id:
            return

        url = f"{self.BASE_URL}/card/{card_id}/customField/{field_id}/item"
        body = {"value": {"text": lead_id}}
        requests.put(url, params=self.auth_params, json=body)

    def set_email(self, card_id, email):
        if not email:
            return

        field_id = self._get_email_field()
        if not field_id:
            return

        url = f"{self.BASE_URL}/card/{card_id}/customField/{field_id}/item"
        body = {"value": {"text": email}}
        requests.put(url, params=self.auth_params, json=body)

    # ------------------------------------------------
    # Read Cards for Reverse Sync
    # ------------------------------------------------
    def find_card_by_lead_id(self, lead_id):
        if not self._get_lead_id_field():
            return None

        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_ID}/cards"
        res = requests.get(url, params=self.auth_params)
        if res.status_code != 200:
            return None

        for card in res.json():
            if self.get_lead_id_value(card["id"]) == lead_id:
                return card
        return None

    def get_lead_id_value(self, card_id):
        field_id = self._get_lead_id_field()
        if not field_id:
            return None

        url = f"{self.BASE_URL}/cards/{card_id}/customFieldItems"
        res = requests.get(url, params=self.auth_params)
        if res.status_code != 200:
            return None

        for item in res.json():
            if item["idCustomField"] == field_id:
                return item["value"]["text"]
        return None

    def get_cards_with_lead_and_status(self):
        if not self._get_lead_id_field():
            return []

        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_ID}/cards"
        res = requests.get(url, params=self.auth_params)
        if res.status_code != 200:
            log_error(f"Card fetch failed: {res.text}")
            return []

        cards = []
        for card in res.json():
            lead_id = self.get_lead_id_value(card["id"])
            if not lead_id:
                continue

            status = self.LIST_TO_STATUS.get(card.get("idList"))
            if not status:
                continue

            cards.append({"lead_id": lead_id, "status": status})

        log_info(f"Reverse sync: Found {len(cards)} linked cards")
        return cards
