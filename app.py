from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from two_way_sync.sync_logic import run_partial_sync
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.task_client import TrelloClient
from two_way_sync.lead_client import LeadClient
from two_way_sync.sync_logic import STATUS_FROM_TRELLO
from two_way_sync.utils.logger import log_info, log_error

app = FastAPI()

# Allow requests from Apps Script & Trello Webhook
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = MappingStore()


@app.get("/health")
async def health_check():
    return {"status": "UP"}


# 🟢 Sheets → Trello (Status edit trigger)
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

    run_partial_sync(lead_id, name, email, status, timestamp)

    return {
        "source": "sheets",
        "lead_id": lead_id,
        "action": "update" if exists else "create"
    }


# 🔄 Trello → Sheets (Webhook, Only for Status change)
@app.post("/trello-webhook")
async def trello_webhook_handler(request: Request):
    body = await request.json()
    action = body.get("action", {})
    action_type = action.get("type", "")

    log_info(f"🔔 Trello Event: {action_type}")

    data = action.get("data", {})
    list_before = data.get("listBefore", {})
    list_after = data.get("listAfter", {})

    # 🚫 Ignore if not a list movement event
    if not list_after:
        return {"ignored": True}

    old_list_id = list_before.get("id")
    new_list_id = list_after.get("id")

    # 🚫 Ignore reorder inside same list & duplicate first event (only process entry)
    if not new_list_id or old_list_id == new_list_id:
        return {"ignored": True}

    from two_way_sync.task_client import TrelloClient
    trello_client = TrelloClient()

    card_id = data.get("card", {}).get("id")
    lead_id = trello_client.get_lead_id_value(card_id)

    # 🚫 Not a card we track
    if not lead_id:
        return {"ignored": True}

    new_list_name = list_after.get("name", "").upper()

    from two_way_sync.sync_logic import STATUS_FROM_TRELLO
    new_status = STATUS_FROM_TRELLO.get(new_list_name)

    # 🚫 List not mapped to status — ignore silently
    if not new_status:
        return {"ignored": True}

    from two_way_sync.lead_client import LeadClient
    lead_client = LeadClient()
    lead_client.update_lead_status(lead_id, new_status)

    from two_way_sync.db.mapping_store import MappingStore
    store = MappingStore()
    store.update_timestamp_from_trello(lead_id)

    log_info(f"📌 Reverse Sync Applied: {lead_id} → {new_status}")

    return {"ok": True, "reverse_sync": True, "lead_id": lead_id}


@app.get("/")
async def root():
    return {
        "message": "Two-Way Sync Service Running 🚀",
        "routes": ["/health", "/sync", "/trello-webhook", "/docs"]
    }
