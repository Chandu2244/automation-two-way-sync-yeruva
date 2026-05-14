"""Gemini-powered lead extraction and backend validation."""

import json
import re

import requests
from requests.exceptions import RequestException

from two_way_sync.config import GEMINI_API_KEY, GEMINI_MODEL

SHEET_STATUSES = {"NEW", "CONTACTED", "QUALIFIED"}
TRELLO_TO_SHEET_STATUS = {
    "TODO": "NEW",
    "IN_PROGRESS": "CONTACTED",
    "DONE": "QUALIFIED",
}

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,98}[A-Za-z.]$")


class LeadValidationError(ValueError):
    """Raised when AI output is missing or invalid."""


class GeminiLeadParser:
    """Extract a lead JSON object from a natural-language sentence."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.timeout = (5, 30)

    def parse(self, sentence):
        """Return validated lead fields extracted from the sentence."""
        if not self.api_key:
            raise RuntimeError("Missing required environment variable: GEMINI_API_KEY")

        sentence = (sentence or "").strip()
        if not sentence:
            raise LeadValidationError("sentence is required")

        try:
            response = requests.post(
                f"{self.BASE_URL}/{self.model}:generateContent",
                params={"key": self.api_key},
                json=self._build_payload(sentence),
                timeout=self.timeout,
            )
        except RequestException as exc:
            raise RuntimeError("Gemini request failed before receiving a response") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini request failed: {response.text}")

        raw_text = self._extract_text(response.json())
        return validate_lead_payload(self._decode_json(raw_text))

    def _build_payload(self, sentence):
        prompt = (
            "Extract one sales lead from the user's sentence. "
            "Return only JSON with exactly these string keys: name, email, status. "
            "Use status NEW, CONTACTED, or QUALIFIED. "
            "If the sentence says todo, use NEW. If it says in progress, contacted, "
            "or working, use CONTACTED. If it says done, qualified, or completed, "
            "use QUALIFIED.\n\n"
            f"Sentence: {sentence}"
        )
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

    def _extract_text(self, payload):
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini response did not contain text output") from exc

    def _decode_json(self, raw_text):
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text).strip()
        try:
            decoded = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LeadValidationError("Gemini response was not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise LeadValidationError("Gemini response must be a JSON object")
        return decoded


def validate_lead_payload(payload):
    """Validate and normalize AI-produced lead fields."""
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    status = str(payload.get("status", "")).upper().strip().replace(" ", "_")

    if not NAME_RE.match(name):
        raise LeadValidationError("name must be 3-100 characters and contain letters")
    if not EMAIL_RE.match(email):
        raise LeadValidationError("email must be a valid email address")

    status = TRELLO_TO_SHEET_STATUS.get(status, status)
    if status not in SHEET_STATUSES:
        allowed = ", ".join(sorted(SHEET_STATUSES | set(TRELLO_TO_SHEET_STATUS)))
        raise LeadValidationError(f"status must be one of: {allowed}")

    return {
        "name": name,
        "email": email,
        "status": status,
    }
