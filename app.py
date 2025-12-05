from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

#  Core Sync Imports
from two_way_sync.sync_logic import run_partial_sync, STATUS_FROM_TRELLO

#  DB & API Clients
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.task_client import TrelloClient
from two_way_sync.lead_client import LeadClient

#  Logging
from two_way_sync.utils.logger import log_info, log_error

app = FastAPI()

# Enable CORS (Apps Script + Trello Webhook)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local Cache for ID → Status Mapping
store = MappingStore()


# -------------------------------------------------------------------
# 🏥 Health Check API
# -------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "UP"}


# -------------------------------------------------------------------
# 🟢 Sheets → Trello (Status Edit Trigger from Apps Script)
# -------------------------------------------------------------------
@app.post("/sync")
async def sync_from_sheets(request: Request):
    data = await request.json()
    log_info(f"📩 Sheet Trigger: {data}")

    lead_id = data["lead_id"]
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    status = data["status"].upper() 
    timestamp = data.get("sheet_timestamp") or datetime.utcnow().isoformat()

    exists = store.exists(lead_id)

    # Partial sync: Only status change reflected in Trello
    run_partial_sync(lead_id, name, email, status, timestamp)

    return {
        "source": "sheets",
        "lead_id": lead_id,
        "action": "update" if exists else "create",
    }


# -------------------------------------------------------------------
# 🔄 Trello → Sheets (Webhook, Only Status Update)
# -------------------------------------------------------------------
@app.post("/trello-webhook")
async def trello_webhook_handler(request: Request):
    body = await request.json()
    action = body.get("action", {})
    action_type = action.get("type")

    log_info(f"🔔 Trello Webhook Event: {action_type}")

    # Validate card presence in webhook data
    data = action.get("data", {})
    card_data = data.get("card", {})
    card_id = card_data.get("id")

    if not card_id:
        return {"ignored": "no_card"}

    trello_client = TrelloClient()
    lead_id = trello_client.get_lead_id_value(card_id)

    # Ignore unsynced cards
    if not lead_id:
        return {"ignored": "not_synced_card"}

    lead_client = LeadClient()

    # 🟥 CASE 1: Archive card → LOST in Sheets
    if card_data.get("closed", False):
        lead_client.update_lead_status(lead_id, "LOST")
        store.upsert(lead_id, sheet_status="LOST")

        log_info(f"🗑 Trello Archived → Sheet LOST updated: {lead_id}")
        return {"status": "archived_to_lost"}

    # Fetch card details to understand movement/list
    card_details = trello_client.get_card_details(card_id)
    list_id = card_details.get("idList")

    # 🟩 CASE 2: Card Restored → Recover status from Trello List
    new_status = STATUS_FROM_TRELLO.get(
        trello_client.LIST_TO_STATUS.get(list_id)
    )

    if new_status:
        lead_client.update_lead_status(lead_id, new_status)
        store.update_timestamp_from_trello(lead_id)

        log_info(f"🔄 Trello Restore → Sheet updated: {lead_id} → {new_status}")
        return {"status": "restore_to_active"}

    # 🟦 CASE 3: Moved list → Update status normally
    new_status = STATUS_FROM_TRELLO.get(
        data.get("listAfter", {}).get("name", "").upper()
    )

    if new_status:
        lead_client.update_lead_status(lead_id, new_status)
        store.update_timestamp_from_trello(lead_id)

        log_info(f"📌 Trello list change → Sheet updated: {lead_id} → {new_status}")
        return {"status": "list_move_updated"}

    return {"ignored": True}


# -------------------------------------------------------------------
#  Default Route
# -------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "message": "Two-Way Sync Service Running 🚀",
        "routes": ["/health", "/sync", "/trello-webhook", "/docs"]
    }
