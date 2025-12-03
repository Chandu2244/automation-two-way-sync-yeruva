import sys, os
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from two_way_sync.lead_client import LeadClient
from two_way_sync.task_client import TrelloClient
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.utils.logger import log_info, log_error


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


def sync_trello_to_leads(lead_client, trello_client, store):
    log_info("🔄 Checking Trello updates...")
    cards = trello_client.get_cards_with_lead_and_status()

    updates = 0
    for card in cards:
        lead_id = card["lead_id"]
        trello_status = STATUS_FROM_TRELLO[card["status"]]
        trello_updated_at = card.get("updated_at") or datetime.now().isoformat()

        existing = store.get(lead_id)

        # New lead mapping — store initial Trello info
        if not existing or existing["trello_timestamp"] is None:
            store.upsert(
                lead_id,
                trello_status=trello_status,
                trello_timestamp=trello_updated_at,
            )
            continue

        sheet_time = existing.get("sheet_timestamp")
        trello_time = existing.get("trello_timestamp")

        # If Trello changed more recently → update Sheet
        if sheet_time is None or trello_time < trello_updated_at:
            lead_client.update_lead_status(lead_id, trello_status)
            store.upsert(
                lead_id,
                sheet_status=trello_status,
                sheet_timestamp=datetime.now().isoformat()
            )
            log_info(f"📌 Updated Sheet: {lead_id} → {trello_status}")
            updates += 1

    log_info(f"✔ Reverse sync complete — {updates} updates applied to Sheets.")


def sync_leads_to_trello(lead_client, trello_client, store):
    log_info("🔁 Checking Sheet updates...")
    leads = lead_client.get_all_leads()

    updates = 0
    for lead in leads:
        lead_id = lead["id"]
        sheet_status = lead["status"].upper()
        sheet_time = datetime.now().isoformat()

        # 🚫 Skip LOST leads (and archive existing card)
        if sheet_status == "LOST":
            mapping = store.get(lead_id)
            if mapping and mapping.get("trello_card_id"):
                trello_client.archive_card(mapping["trello_card_id"])
                store.delete(lead_id)
                log_info(f"🗑️ Archived Trello card for LOST lead {lead_id}")
            continue

        existing = store.get(lead_id)

        # 🔹 New mapping case → create card initially
        if not existing or existing["sheet_timestamp"] is None:
            card = trello_client.sync_card_for_lead(
                lead["name"], lead_id,
                STATUS_TO_TRELLO.get(sheet_status, "TODO"),
                lead.get("email", "")
            )
            if card:
                store.upsert(
                    lead_id,
                    trello_card_id=card["id"],
                    sheet_status=sheet_status,
                    sheet_timestamp=sheet_time
                )
                updates += 1
            continue

        trello_time = existing.get("trello_timestamp")
        stored_sheet_status = existing.get("sheet_status")

        # 🔄 Sheet changed more recently → update Trello
        if stored_sheet_status != sheet_status and \
           (trello_time is None or sheet_time > trello_time):

            card = trello_client.sync_card_for_lead(
                lead["name"], lead_id,
                STATUS_TO_TRELLO[sheet_status],
                lead.get("email", "")
            )
            if card:
                store.upsert(
                    lead_id,
                    sheet_status=sheet_status,
                    sheet_timestamp=sheet_time
                )
                log_info(f"📌 Updated Trello: {lead_id} → {sheet_status}")
                updates += 1

    log_info(f"✔ Forward sync complete — {updates} updates applied to Trello.")


def run_full_sync():
    log_info(f"=== Sync START @ {datetime.now().isoformat()} ===")

    lead_client = LeadClient()
    trello_client = TrelloClient()
    store = MappingStore()

    sync_trello_to_leads(lead_client, trello_client, store)
    sync_leads_to_trello(lead_client, trello_client, store)

    log_info("=== Sync END ===\n")


if __name__ == "__main__":
    run_full_sync()
