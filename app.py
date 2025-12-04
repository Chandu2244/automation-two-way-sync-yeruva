from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from two_way_sync.sync_logic import run_partial_sync, run_full_sync
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.utils.logger import log_info, log_error

app = FastAPI()

# Allow Apps Script and Trello webhook
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = MappingStore()


@app.get("/health")
async def health_check():
    return {"status": "OK"}


@app.post("/sync")
@app.put("/sync")
async def sync_from_sheets(request: Request):
    data = await request.json()
    log_info(f"📩 Trigger from Google Sheet: {data}")

    lead_id = data["lead_id"]
    name = data.get("name", "")
    email = data.get("email", "")
    status = data["status"].upper()
    timestamp = data["sheet_timestamp"]  # exact commit time

    exists_in_db = bool(store.get(lead_id))

    # Case 1️⃣: New Lead
    if not exists_in_db:
        log_info(f"🆕 New Lead created: {lead_id} → Trello POST")
        run_partial_sync(lead_id, name, email, status, timestamp)
        return {"created": True, "lead_id": lead_id}

    # Case 2️⃣: Existing Lead → Update Trello
    log_info(f"♻ Updating existing lead: {lead_id} → Trello PUT")
    run_partial_sync(lead_id, name, email, status, timestamp)

    return {"updated": True, "lead_id": lead_id}


@app.post("/trello-webhook")
async def trello_webhook_handler(request: Request):
    body = await request.json()
    log_info(f"🔔 Trello Webhook Event Received: {body}")

    # Trello is considered more recent source → reverse sync
    run_full_sync()

    return {"webhook": "processed"}


@app.get("/")
async def root():
    return {
        "message": "Lead ↔ Trello Sync Service Running 🚀",
        "endpoints": ["/health", "/sync", "/trello-webhook", "/docs"]
    }
