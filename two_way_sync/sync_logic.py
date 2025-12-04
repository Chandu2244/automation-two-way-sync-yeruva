import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from two_way_sync.lead_client import LeadClient
from two_way_sync.task_client import TrelloClient
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.utils.logger import log_info, log_error


# ================================
# Status Mapping
# ================================
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


# ================================
# Partial Sync (from Google Sheets)
# ================================
def run_partial_sync(lead_id, name, email, sheet_status, sheet_timestamp):
    log_info(f"📌 Sheets Partial Sync for {lead_id}")

    store = MappingStore()
    trello_client = TrelloClient()
    existing = store.get(lead_id)

    # LOST → Archive card
    if sheet_status == "LOST":
        if existing and existing.get("trello_card_id"):
            trello_client.archive_card(existing["trello_card_id"])
            store.delete(lead_id)
            log_info(f"🗑 Archived card (LOST): {lead_id}")
        return

    # NEW entry → push to Trello
    if not existing:
        update_trello_and_store(
            trello_client, store,
            lead_id, name, email, sheet_status, sheet_timestamp
        )
        return

    trello_ts = existing.get("trello_timestamp")

    # Only update if Sheet is newer
    if not trello_ts or sheet_timestamp > trello_ts:
        update_trello_and_store(
            trello_client, store,
            lead_id, name, email, sheet_status, sheet_timestamp
        )
    else:
        log_info(f"⏭ Skipped — Trello newer ({lead_id})")


# ================================
# Shared Updater
# ================================
def update_trello_and_store(client, store, lead_id, name, email, sheet_status, sheet_timestamp):
    trello_status = STATUS_TO_TRELLO.get(sheet_status, "TODO")
    card = client.sync_card_for_lead(name, lead_id, trello_status, email)

    if card is False:
        log_error(f"❌ Trello API failed ({lead_id})")
        return

    card_id = card["id"] if isinstance(card, dict) else store.get_card_id(lead_id)

    if card_id:
        store.upsert(
            lead_id,
            trello_card_id=card_id,
            sheet_status=sheet_status,
            sheet_timestamp=sheet_timestamp
        )
        log_info(f"🔁 Trello Updated: {lead_id} → {sheet_status}")
    else:
        log_error(f"⚠ No card ID received for {lead_id}")


# ================================
# Full Sync (manual/webhook)
# ================================
def run_full_sync():
    log_info(f"=== Full Sync Start @ {datetime.utcnow().isoformat()} ===")

    client_s = LeadClient()
    client_t = TrelloClient()
    store = MappingStore()

    sync_trello_to_leads(client_s, client_t, store)
    sync_leads_to_trello(client_s, client_t, store)
    reconcile_deleted_leads(client_s, client_t, store)

    log_info("=== Full Sync End ===\n")


# ================================
# Reverse Sync (Trello → Sheets)
# ================================
def sync_trello_to_leads(lead_client, trello_client, store):
    log_info("🔄 Checking Trello updates...")

    cards = trello_client.get_cards_with_lead_and_status()
    updated = 0

    for card in cards:
        lead_id = card["lead_id"]
        new_status = STATUS_FROM_TRELLO.get(card["status"])
        trello_ts = card.get("updated_at") or datetime.utcnow().isoformat()

        existing = store.get(lead_id)

        if not existing:
            store.upsert(
                lead_id,
                trello_status=new_status,
                trello_timestamp=trello_ts
            )
            continue

        sheet_ts = existing.get("sheet_timestamp")

        if not sheet_ts or trello_ts > sheet_ts:
            lead_client.update_lead_status(lead_id, new_status)
            store.upsert(
                lead_id,
                sheet_status=new_status,
                sheet_timestamp=trello_ts
            )
            updated += 1
            log_info(f"📌 Sheet Updated: {lead_id} → {new_status}")

    log_info(f"✔ Reverse Sync: {updated} changes applied")


# ================================
# Forward Sync (Sheet → Trello)
# ================================
def sync_leads_to_trello(lead_client, trello_client, store):
    log_info("🔁 Checking Sheets for new leads...")
    leads = lead_client.get_all_leads()

    current_time = datetime.utcnow().isoformat()
    updated = 0

    for lead in leads:
        lead_id = lead["id"]
        status = lead["status"].upper()

        if status == "LOST":
            continue

        if not store.get(lead_id):
            update_trello_and_store(
                trello_client, store,
                lead_id,
                lead["name"],
                lead.get("email", ""),
                status,
                current_time
            )
            updated += 1

    log_info(f"✔ Forward Sync: {updated} new Trello cards created")


# ================================
# Row Deletion Handler
# ================================
def reconcile_deleted_leads(lead_client, trello_client, store):
    leads = lead_client.get_all_leads()
    current_ids = {lead["id"] for lead in leads}
    stored_ids = set(store.get_all_lead_ids())

    deleted_ids = stored_ids - current_ids

    for lead_id in deleted_ids:
        mapping = store.get(lead_id)
        card_id = mapping.get("trello_card_id")

        if card_id:
            trello_client.archive_card(card_id)
            log_info(f"🗑 Archived deleted lead card {lead_id}")

        store.delete(lead_id)
