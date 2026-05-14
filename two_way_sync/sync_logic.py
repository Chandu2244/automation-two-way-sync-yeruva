"""Core synchronization logic for Google Sheets and Trello."""

from datetime import datetime, timedelta, timezone

from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.lead_client import LeadClient
from two_way_sync.task_client import TrelloClient
from two_way_sync.utils.logger import log_error, log_info

STATUS_TO_TRELLO = {
    "NEW": "TODO",
    "CONTACTED": "IN_PROGRESS",
    "QUALIFIED": "DONE",
}

STATUS_FROM_TRELLO = {
    "TODO": "NEW",
    "IN_PROGRESS": "CONTACTED",
    "DONE": "QUALIFIED",
}

SOURCE_SHEETS = "sheets"
SOURCE_TRELLO = "trello"
LAST_SYNC_KEY = "last_sync_time"


def utc_now_iso():
    """Return the current UTC time in ISO format."""
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def _parse_timestamp(value):
    """Parse an ISO-like timestamp into a timezone-aware datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_timestamp(value):
    """Public timestamp parser used by reconciliation and tests."""
    return _parse_timestamp(value)


def is_newer_timestamp(incoming_ts, existing_ts):
    """Return True when the incoming timestamp is newer than the stored timestamp."""
    incoming_dt = _parse_timestamp(incoming_ts)
    existing_dt = _parse_timestamp(existing_ts)
    if incoming_dt and existing_dt:
        return incoming_dt > existing_dt
    if incoming_dt and not existing_dt:
        return True
    return False


def is_incoming_newer(incoming_time, stored_time):
    """Alias used by event-driven sync checks."""
    return is_newer_timestamp(incoming_time, stored_time)


def should_skip_event(store, lead_id, incoming_time, incoming_source, incoming_status=None):
    """Decide whether an incoming event is stale, duplicate, or an expected echo."""
    incoming_status = (incoming_status or "").upper().strip()

    if store.consume_pending_echo(
        lead_id,
        incoming_source,
        incoming_status,
        incoming_timestamp=incoming_time,
    ):
        log_info(
            "SKIP: self-trigger "
            f"lead_id={lead_id} incoming_time={incoming_time} "
            f"source={incoming_source} status={incoming_status}"
        )
        return True, "self_trigger"

    stored = store.get(lead_id) or {}
    stored_time = stored.get("last_updated_time")
    stored_source = stored.get("last_updated_source") or stored.get("last_update_source")

    if stored_time and not is_incoming_newer(incoming_time, stored_time):
        reason = "self_trigger" if stored_source == incoming_source else "outdated_timestamp"
        log_info(
            f"SKIP: {reason.replace('_', ' ')} "
            f"lead_id={lead_id} incoming_time={incoming_time} stored_time={stored_time} "
            f"source={incoming_source} stored_source={stored_source}"
        )
        return True, reason

    return False, None


class SyncService:
    """Orchestrates event sync, retries, incremental catch-up, and reconciliation."""

    def __init__(self, store=None, lead_client=None, trello_client=None):
        """Create the service with injectable dependencies for testing."""
        self.store = store or MappingStore()
        self.lead_client = lead_client or LeadClient()
        self.trello_client = trello_client or TrelloClient()

    def apply_sheets_event(
        self,
        lead_id,
        name,
        email,
        status,
        incoming_time=None,
        enforce_idempotency=True,
    ):
        """Primary path: apply one Google Sheets change to Trello."""
        incoming_time = incoming_time or utc_now_iso()
        lead_id = (lead_id or "").strip()
        status = (status or "").upper().strip()

        if enforce_idempotency:
            skip, reason = should_skip_event(
                self.store, lead_id, incoming_time, SOURCE_SHEETS, status
            )
            if skip:
                return {"applied": False, "reason": reason}

        try:
            if status == "LOST":
                self._archive_trello_card(lead_id, incoming_time)
            else:
                self._upsert_trello_card(lead_id, name, email, status, incoming_time)
        except Exception as exc:
            self.queue_retry(
                "sheets_to_trello",
                {
                    "lead_id": lead_id,
                    "name": name,
                    "email": email,
                    "status": status,
                    "incoming_time": incoming_time,
                },
                exc,
            )
            return {"applied": False, "reason": "queued_retry"}

        log_info(
            "APPLY: Sheets->Trello "
            f"lead_id={lead_id} incoming_time={incoming_time} source={SOURCE_SHEETS}"
        )
        return {"applied": True}

    def apply_trello_event(
        self,
        lead_id,
        status,
        incoming_time=None,
        card_id=None,
        enforce_idempotency=True,
    ):
        """Primary path: apply one Trello webhook/change to Google Sheets."""
        incoming_time = incoming_time or utc_now_iso()
        lead_id = (lead_id or "").strip()
        status = (status or "").upper().strip()

        if enforce_idempotency:
            skip, reason = should_skip_event(
                self.store, lead_id, incoming_time, SOURCE_TRELLO, status
            )
            if skip:
                return {"applied": False, "reason": reason}

        try:
            updated = self.lead_client.update_lead_status(
                lead_id, status, incoming_time, SOURCE_TRELLO
            )
            if not updated:
                raise RuntimeError("Sheets status update failed")
        except Exception as exc:
            self.queue_retry(
                "trello_to_sheets",
                {
                    "lead_id": lead_id,
                    "status": status,
                    "incoming_time": incoming_time,
                    "card_id": card_id,
                },
                exc,
            )
            return {"applied": False, "reason": "queued_retry"}

        self.store.record_pending_echo(
            lead_id,
            SOURCE_SHEETS,
            status,
            expected_timestamp=incoming_time,
        )
        self.store.upsert(
            lead_id,
            trello_card_id=card_id,
            sheet_status=status,
            sheet_timestamp=incoming_time,
            trello_timestamp=incoming_time,
            last_update_source=SOURCE_TRELLO,
            last_updated_time=incoming_time,
            last_updated_source=SOURCE_TRELLO,
        )
        log_info(
            "APPLY: Trello->Sheets "
            f"lead_id={lead_id} incoming_time={incoming_time} source={SOURCE_TRELLO}"
        )
        return {"applied": True}

    def create_lead_from_ai_fields(self, name, email, status, incoming_time=None):
        """Create a lead in Sheets first, then create the matching Trello card."""
        incoming_time = incoming_time or utc_now_iso()
        name = (name or "").strip()
        email = (email or "").strip()
        status = (status or "").upper().strip()
        lead_id = self.store.get_next_lead_id()

        created = self.lead_client.append_lead(
            lead_id,
            name,
            email,
            status,
            incoming_time,
            SOURCE_SHEETS,
        )
        if not created:
            raise RuntimeError("Google Sheets row creation failed")

        self.store.upsert(
            lead_id,
            sheet_status=status,
            sheet_timestamp=incoming_time,
            last_update_source=SOURCE_SHEETS,
            last_updated_time=incoming_time,
            last_updated_source=SOURCE_SHEETS,
        )

        try:
            self._upsert_trello_card(lead_id, name, email, status, incoming_time)
        except Exception as exc:
            self.queue_retry(
                "sheets_to_trello",
                {
                    "lead_id": lead_id,
                    "name": name,
                    "email": email,
                    "status": status,
                    "incoming_time": incoming_time,
                },
                exc,
            )
            return {
                "created": True,
                "lead_id": lead_id,
                "trello_created": False,
                "reason": "queued_retry",
            }

        log_info(
            "CREATE: AI->Sheets->Trello "
            f"lead_id={lead_id} incoming_time={incoming_time}"
        )
        return {
            "created": True,
            "lead_id": lead_id,
            "trello_created": True,
            "status": status,
        }

    def _upsert_trello_card(self, lead_id, name, email, sheet_status, incoming_time):
        """Create, restore, or move the Trello card for a Sheets-origin update."""
        trello_status = STATUS_TO_TRELLO.get(sheet_status, "TODO")
        card = self.trello_client.sync_card_for_lead(name, lead_id, trello_status, email)
        if not card:
            raise RuntimeError("Trello card upsert failed")

        card_id = card.get("id") if isinstance(card, dict) else self.store.get_card_id(lead_id)
        trello_time = card.get("dateLastActivity") if isinstance(card, dict) else incoming_time
        self.store.upsert(
            lead_id,
            trello_card_id=card_id,
            trello_status=trello_status,
            trello_timestamp=trello_time,
            sheet_status=sheet_status,
            sheet_timestamp=incoming_time,
            last_update_source=SOURCE_SHEETS,
            last_updated_time=incoming_time,
            last_updated_source=SOURCE_SHEETS,
        )
        self.store.record_pending_echo(
            lead_id,
            SOURCE_TRELLO,
            sheet_status,
            expected_timestamp=incoming_time,
        )

    def _archive_trello_card(self, lead_id, incoming_time):
        """Archive the mapped Trello card when a Sheets lead is marked LOST."""
        existing = self.store.get(lead_id) or {}
        card_id = existing.get("trello_card_id")
        if card_id and not self.trello_client.archive_card(card_id):
            raise RuntimeError("Trello archive failed")

        self.store.upsert(
            lead_id,
            sheet_status="LOST",
            sheet_timestamp=incoming_time,
            last_update_source=SOURCE_SHEETS,
            last_updated_time=incoming_time,
            last_updated_source=SOURCE_SHEETS,
        )
        self.store.record_pending_echo(
            lead_id,
            SOURCE_TRELLO,
            "LOST",
            expected_timestamp=incoming_time,
        )

    def queue_retry(self, operation, payload, error):
        """Persist a failed operation so the scheduler can retry it later."""
        self.store.enqueue_retry(operation, payload, error=error)
        log_error(
            "RETRY: queued "
            f"operation={operation} lead_id={payload.get('lead_id')} error={error}"
        )

    def retry_due_items(self):
        """Retry due queue items with capped exponential backoff."""
        for item in self.store.get_due_retries():
            retry_id = item["id"]
            attempts = item["attempts"] + 1
            try:
                self._execute_retry(item["operation"], item["payload"])
                self.store.mark_retry_success(retry_id)
                log_info(
                    "RETRY: success "
                    f"operation={item['operation']} lead_id={item['payload'].get('lead_id')}"
                )
            except Exception as exc:
                if attempts >= item["max_attempts"]:
                    self.store.drop_retry(retry_id)
                    log_error(
                        "RETRY: failed max attempts "
                        f"operation={item['operation']} lead_id={item['payload'].get('lead_id')} "
                        f"error={exc}"
                    )
                    continue

                delay_seconds = min(300, 30 * (2 ** (attempts - 1)))
                next_attempt_at = (
                    datetime.utcnow() + timedelta(seconds=delay_seconds)
                ).isoformat()
                self.store.mark_retry_failed(retry_id, attempts, exc, next_attempt_at)
                log_error(
                    "RETRY: failed "
                    f"operation={item['operation']} lead_id={item['payload'].get('lead_id')} "
                    f"attempts={attempts} next_attempt_at={next_attempt_at} error={exc}"
                )

    def _execute_retry(self, operation, payload):
        """Execute one retry queue item."""
        if operation == "sheets_to_trello":
            self._upsert_trello_card(
                payload["lead_id"],
                payload.get("name", ""),
                payload.get("email", ""),
                payload["status"],
                payload["incoming_time"],
            )
            return

        if operation == "trello_to_sheets":
            updated = self.lead_client.update_lead_status(
                payload["lead_id"],
                payload["status"],
                payload["incoming_time"],
                SOURCE_TRELLO,
            )
            if not updated:
                raise RuntimeError("Sheets status update failed")
            self.store.record_pending_echo(
                payload["lead_id"],
                SOURCE_SHEETS,
                payload["status"],
                expected_timestamp=payload["incoming_time"],
            )
            self.store.upsert(
                payload["lead_id"],
                trello_card_id=payload.get("card_id"),
                sheet_status=payload["status"],
                sheet_timestamp=payload["incoming_time"],
                trello_timestamp=payload["incoming_time"],
                last_update_source=SOURCE_TRELLO,
                last_updated_time=payload["incoming_time"],
                last_updated_source=SOURCE_TRELLO,
            )
            return

        raise ValueError(f"Unknown retry operation: {operation}")

    def run_incremental_sync(self):
        """Catch up records updated after the global last_sync_time."""
        last_sync_time = self.store.get_metadata(LAST_SYNC_KEY)
        run_started_at = utc_now_iso()

        for lead in self.lead_client.get_all_leads():
            lead_id = lead.get("id")
            if not lead_id:
                continue
            incoming_time = lead.get("last_updated_time") or lead.get("updated_at")
            if not incoming_time and self.store.exists(lead_id):
                continue
            incoming_time = incoming_time or run_started_at
            if last_sync_time and not is_incoming_newer(incoming_time, last_sync_time):
                continue
            self.apply_sheets_event(
                lead_id,
                lead.get("name", ""),
                lead.get("email", ""),
                lead.get("status", ""),
                incoming_time,
            )

        for card in self.trello_client.get_cards_with_lead_and_status():
            incoming_time = card.get("trello_timestamp") or run_started_at
            if last_sync_time and not is_incoming_newer(incoming_time, last_sync_time):
                continue
            sheet_status = STATUS_FROM_TRELLO.get(card.get("status"))
            if sheet_status:
                self.apply_trello_event(
                    card["lead_id"],
                    sheet_status,
                    incoming_time,
                    card.get("card_id"),
                )

        self.store.set_metadata(LAST_SYNC_KEY, run_started_at)
        log_info(f"Incremental sync complete last_sync_time={run_started_at}")

    def run_reconciliation(self, recent_minutes=60):
        """Compare recent mapped records and repair drift using the latest timestamp."""
        cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=recent_minutes)
        cards_by_lead = {
            card["lead_id"]: card
            for card in self.trello_client.get_cards_with_lead_and_status()
            if parse_timestamp(card.get("trello_timestamp"))
            and parse_timestamp(card.get("trello_timestamp")) >= cutoff
        }

        for lead_id in self.store.get_all_lead_ids():
            mapping = self.store.get(lead_id) or {}
            card = cards_by_lead.get(lead_id)
            if not card:
                continue

            trello_time = card.get("trello_timestamp")
            sheet_time = mapping.get("sheet_timestamp")
            trello_sheet_status = STATUS_FROM_TRELLO.get(card.get("status"))

            if trello_sheet_status and is_incoming_newer(trello_time, sheet_time):
                self.apply_trello_event(
                    lead_id,
                    trello_sheet_status,
                    trello_time,
                    card.get("card_id"),
                    enforce_idempotency=False,
                )
            elif mapping.get("sheet_status") and is_incoming_newer(sheet_time, trello_time):
                self.apply_sheets_event(
                    lead_id,
                    "",
                    "",
                    mapping["sheet_status"],
                    sheet_time,
                    enforce_idempotency=False,
                )

        log_info(f"Scheduled reconciliation complete recent_minutes={recent_minutes}")


def run_partial_sync(lead_id, name, email, sheet_status, sheet_timestamp):
    """Backward-compatible helper for one Sheets-origin update."""
    return SyncService().apply_sheets_event(
        lead_id, name, email, sheet_status, sheet_timestamp
    )


def update_trello_and_store(client, store, lead_id, name, email, sheet_status, sheet_timestamp):
    """Backward-compatible helper that updates Trello and local state."""
    service = SyncService(store=store, trello_client=client)
    return service.apply_sheets_event(
        lead_id, name, email, sheet_status, sheet_timestamp, enforce_idempotency=False
    )


def run_full_sync():
    """Run a broad catch-up sync followed by deletion reconciliation."""
    log_info(f"Full sync start time={datetime.utcnow().isoformat()}")
    lead_client = LeadClient()
    trello_client = TrelloClient()
    store = MappingStore()
    sync_trello_to_leads(lead_client, trello_client, store)
    sync_leads_to_trello(lead_client, trello_client, store)
    reconcile_deleted_leads(lead_client, trello_client, store)
    log_info("Full sync complete")


def sync_trello_to_leads(lead_client, trello_client, store):
    """Apply newer Trello states back into Google Sheets."""
    service = SyncService(store=store, lead_client=lead_client, trello_client=trello_client)
    updated = 0
    for card in trello_client.get_cards_with_lead_and_status():
        status = "LOST" if card.get("archived") else STATUS_FROM_TRELLO.get(card["status"])
        if not status:
            continue
        result = service.apply_trello_event(
            card["lead_id"],
            status,
            card.get("trello_timestamp") or utc_now_iso(),
            card.get("card_id"),
        )
        if result.get("applied"):
            updated += 1
    log_info(f"Reverse sync complete updated={updated}")


def sync_leads_to_trello(lead_client, trello_client, store):
    """Create or update Trello cards for Sheets leads."""
    service = SyncService(store=store, lead_client=lead_client, trello_client=trello_client)
    updated = 0
    for lead in lead_client.get_all_leads():
        lead_id = lead.get("id")
        status = (lead.get("status") or "").upper()
        if not lead_id or status == "LOST":
            continue
        timestamp = lead.get("last_updated_time") or utc_now_iso()
        result = service.apply_sheets_event(
            lead_id,
            lead.get("name", ""),
            lead.get("email", ""),
            status,
            timestamp,
        )
        if result.get("applied"):
            updated += 1
    log_info(f"Forward sync complete updated={updated}")


def reconcile_deleted_leads(lead_client, trello_client, store):
    """Archive Trello cards whose mapped lead rows no longer exist in Sheets."""
    leads = lead_client.get_all_leads()
    stored_ids = set(store.get_all_lead_ids())
    if not leads and stored_ids:
        log_error("Skipping deletion reconcile because Sheets returned no rows")
        return

    current_ids = {lead["id"] for lead in leads if lead.get("id")}
    for lead_id in stored_ids - current_ids:
        mapping = store.get(lead_id) or {}
        card_id = mapping.get("trello_card_id")
        if card_id:
            trello_client.archive_card(card_id)
            log_info(f"Archived Trello card for deleted lead lead_id={lead_id}")
        store.delete(lead_id)
