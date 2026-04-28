"""Trello API client used by the sync orchestration layer."""

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

from two_way_sync.config import (
    DONE_LIST_ID,
    IN_PROGRESS_LIST_ID,
    TODO_LIST_ID,
    TRELLO_API_KEY,
    TRELLO_BOARD_SHORT_ID,
    TRELLO_TOKEN,
)
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.utils.logger import log_error, log_info


class TrelloClient:
    """Small wrapper around Trello card, list, and custom-field APIs."""

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
        """Create an authenticated Trello session with retry support."""
        self.auth = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
        self.store = MappingStore()
        self.custom_fields = {}
        self.timeout = (5, 20)
        self.session = self._build_retry_session()

    def _build_retry_session(self):
        """Build an HTTP session that retries transient Trello failures."""
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.7,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _request(self, method, url, **kwargs):
        """Run one Trello HTTP request with timeout and error logging."""
        kwargs.setdefault("timeout", self.timeout)
        try:
            return self.session.request(method, url, **kwargs)
        except RequestException as exc:
            log_error(f"Trello request failed method={method} url={url} error={exc}")
            return None

    def _get_custom_field_id(self, field_name):
        """Resolve and cache a Trello custom field ID by display name."""
        if field_name in self.custom_fields:
            return self.custom_fields[field_name]

        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_SHORT_ID}/customFields"
        res = self._request("GET", url, params=self.auth)
        if not res:
            return None
        if res.status_code != 200:
            log_error(f"Failed fetching Trello custom fields: {res.text}")
            return None

        for field in res.json():
            if field["name"].strip().lower() == field_name.lower():
                self.custom_fields[field_name] = field["id"]
                return field["id"]

        log_error(f"Trello custom field missing: {field_name}")
        return None

    def set_custom_field(self, card_id, field_name, value):
        """Set a text custom field on a Trello card."""
        field_id = self._get_custom_field_id(field_name)
        if not field_id:
            return False

        url = f"{self.BASE_URL}/card/{card_id}/customField/{field_id}/item"
        res = self._request(
            "PUT",
            url,
            params=self.auth,
            json={"value": {"text": value}},
        )
        if not res:
            return False
        if res.status_code != 200:
            log_error(f"Failed setting Trello field {field_name}: {res.text}")
            return False
        return True

    def create_card(self, name, lead_id, status="TODO", email=""):
        """Create a Trello card and attach required lead metadata."""
        list_id = self.STATUS_TO_LIST.get(status, TODO_LIST_ID)
        url = f"{self.BASE_URL}/cards"
        params = {**self.auth, "name": name or lead_id, "idList": list_id}
        res = self._request("POST", url, params=params)
        if not res:
            return False
        if res.status_code != 200:
            log_error(f"Create Trello card failed: {res.text}")
            return False

        card = res.json()
        if not self.set_custom_field(card["id"], "lead_id", lead_id):
            log_error(f"Failed attaching lead_id custom field lead_id={lead_id}")
            return False
        if email and not self.set_custom_field(card["id"], "email", email):
            log_error(f"Failed attaching email custom field lead_id={lead_id}")

        log_info(f"Trello card created lead_id={lead_id} status={status}")
        return card

    def sync_card_for_lead(self, name, lead_id, status, email=""):
        """Create, restore, or move the Trello card for one lead."""
        mapping = self.store.get(lead_id)
        card_id = mapping.get("trello_card_id") if mapping else None

        if card_id:
            restored = self.restore_archived_card_if_exists(lead_id, status)
            if restored:
                return restored

            updated = self.update_status(card_id, status, lead_id)
            if updated:
                return updated

        restored = self.restore_archived_card_if_exists(lead_id, status)
        if restored:
            return restored

        return self.create_card(name, lead_id, status, email)

    def update_status(self, card_id, status, lead_id):
        """Move a Trello card to the list mapped to the given status."""
        list_id = self.STATUS_TO_LIST.get(status)
        if not list_id:
            log_error(f"Unknown Trello status lead_id={lead_id} status={status}")
            return False

        url = f"{self.BASE_URL}/cards/{card_id}"
        res = self._request("PUT", url, params={**self.auth, "idList": list_id})
        if not res:
            return False
        if res.status_code != 200:
            log_error(f"Move Trello card failed lead_id={lead_id}: {res.text}")
            return False

        log_info(f"Trello status updated lead_id={lead_id} status={status}")
        return res.json()

    def archive_card(self, card_id):
        """Archive a Trello card."""
        url = f"{self.BASE_URL}/cards/{card_id}"
        res = self._request("PUT", url, params={**self.auth, "closed": "true"})
        if not res:
            return False
        if res.status_code != 200:
            log_error(f"Archive Trello card failed card_id={card_id}: {res.text}")
            return False

        log_info(f"Trello card archived card_id={card_id}")
        return True

    def _get_field_value(self, card_id, field_name):
        """Read a text custom field from a Trello card."""
        field_id = self._get_custom_field_id(field_name)
        if not field_id:
            return None

        url = f"{self.BASE_URL}/cards/{card_id}/customFieldItems"
        res = self._request("GET", url, params=self.auth)
        if not res or res.status_code != 200:
            return None

        for item in res.json():
            if item["idCustomField"] == field_id:
                return item.get("value", {}).get("text")
        return None

    def get_cards_with_lead_and_status(self):
        """Fetch board cards that have lead_id metadata and a known list."""
        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_SHORT_ID}/cards"
        res = self._request("GET", url, params=self.auth)
        if not res:
            return []
        if res.status_code != 200:
            log_error(f"Fetch Trello cards failed: {res.text}")
            return []

        cards = []
        for card in res.json():
            lead_id = self._get_field_value(card["id"], "lead_id")
            status = self.LIST_TO_STATUS.get(card["idList"])
            if not lead_id or not status:
                continue
            cards.append({
                "lead_id": lead_id,
                "card_id": card["id"],
                "status": status,
                "trello_timestamp": card.get("dateLastActivity"),
                "archived": card.get("closed", False),
            })

        log_info(f"Mapped Trello cards found count={len(cards)}")
        return cards

    def get_card_details(self, card_id):
        """Return raw Trello card details for webhook decisions."""
        url = f"{self.BASE_URL}/cards/{card_id}"
        res = self._request("GET", url, params=self.auth)
        if not res or res.status_code != 200:
            return {}
        return res.json()

    def get_lead_id_value(self, card_id):
        """Return the lead_id custom field value for a Trello card."""
        return self._get_field_value(card_id, "lead_id")

    def restore_archived_card_if_exists(self, lead_id, new_status):
        """Restore an archived card for the same lead, if one exists."""
        if not self._get_custom_field_id("lead_id"):
            return None

        url = f"{self.BASE_URL}/boards/{TRELLO_BOARD_SHORT_ID}/cards"
        res = self._request("GET", url, params={**self.auth, "filter": "closed"})
        if not res:
            return None
        if res.status_code != 200:
            log_error(f"Fetch archived Trello cards failed: {res.text}")
            return None

        list_id = self.STATUS_TO_LIST.get(new_status)
        if not list_id:
            log_error(f"Unknown restore status lead_id={lead_id} status={new_status}")
            return None

        for card in res.json():
            card_id = card["id"]
            if self._get_field_value(card_id, "lead_id") != lead_id:
                continue

            restore_url = f"{self.BASE_URL}/cards/{card_id}"
            restore_res = self._request(
                "PUT",
                restore_url,
                params={**self.auth, "closed": "false", "idList": list_id},
            )
            if restore_res and restore_res.status_code == 200:
                log_info(f"Trello card restored lead_id={lead_id} status={new_status}")
                return restore_res.json()

        return None
