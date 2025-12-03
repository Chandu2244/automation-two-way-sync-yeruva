import sys, os
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from two_way_sync.lead_client import LeadClient
from two_way_sync.task_client import TrelloClient
from two_way_sync.utils.logger import log_info, log_error


STATUS_TO_TRELLO = {
    "NEW": "TODO",
    "CONTACTED": "IN_PROGRESS",
    "QUALIFIED": "DONE",
    "LOST": "DONE",
}

STATUS_FROM_TRELLO = {
    "TODO": "NEW",
    "IN_PROGRESS": "CONTACTED",
    "DONE": "QUALIFIED",
}


def safe_execute(action_name: str, func, *args, retries=3, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            log_error(f"{action_name} failed ({attempt}/{retries}): {str(error)}")
    return None


def sync_leads_to_trello(lead_client, trello_client):
    leads = safe_execute("Read Leads from Sheets", lead_client.get_all_leads)
    if not leads:
        return

    updated = 0

    for lead in leads:
        lead_id = lead.get("id")
        name = lead.get("name", "").strip()
        email = lead.get("email", "")
        status = (lead.get("status") or "").upper()

        if not lead_id or not name:
            continue

        if status == "LOST":
            continue

        trello_status = STATUS_TO_TRELLO.get(status, "TODO")

        safe_execute(
            f"Sync card for {lead_id}",
            trello_client.sync_card_for_lead,
            name, lead_id, trello_status, email=email
        )
        updated += 1

    log_info(f"[Sheets → Trello] Updated {updated} tasks.")


def sync_trello_to_leads(lead_client, trello_client):
    leads = safe_execute("Read Leads from Sheets", lead_client.get_all_leads)
    if not leads:
        return

    lead_status_map = {
        lead["id"]: (lead.get("status") or "").upper()
        for lead in leads if lead.get("id")
    }

    cards = safe_execute("Read Cards from Trello", trello_client.get_cards_with_lead_and_status) or []
    updated = 0

    for card in cards:
        lead_id = card["lead_id"]
        trello_status = card["status"]

        if trello_status not in STATUS_FROM_TRELLO:
            continue

        mapped_status = STATUS_FROM_TRELLO[trello_status]
        if lead_id in lead_status_map and mapped_status != lead_status_map[lead_id]:
            safe_execute(
                f"Update Sheet Lead {lead_id}",
                lead_client.update_lead_status,
                lead_id,
                mapped_status
            )
            updated += 1

    log_info(f"[Trello → Sheets] Updated {updated} leads.")


def run_full_sync():
    log_info(f"=== Sync started @ {datetime.now()} ===")

    lead_client = LeadClient()
    trello_client = TrelloClient()

    sync_trello_to_leads(lead_client, trello_client)  # Reverse FIRST
    sync_leads_to_trello(lead_client, trello_client)

    log_info("=== Sync completed ===")


if __name__ == "__main__":
    run_full_sync()
