from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from two_way_sync.sync_logic import run_partial_sync, run_full_sync
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.utils.logger import log_info

app = FastAPI()

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


@app.post("/sync")
async def sync_from_sheets(request: Request):
    data = await request.json()
    log_info(f"📩 Sheet Trigger: {data}")

    lead_id = data["lead_id"]
    name = data.get("name", "")
    email = data.get("email", "")
    status = data["status"].upper()
    timestamp = data["sheet_timestamp"]

    # Check if lead exists in mapping DB
    lead_exists = store.exists(lead_id)

    run_partial_sync(lead_id, name, email, status, timestamp)

    return {
        "lead_id": lead_id,
        "action": "update" if lead_exists else "create",
        "source": "sheets",
    }


@app.post("/trello-webhook")
async def trello_webhook_handler(request: Request):
    body = await request.json()
    log_info(f"🔔 Trello Webhook Event: {body}")

    # Run full sync because Trello is a source of truth
    run_full_sync()

    return {"webhook": "ok"}


@app.get("/")
async def root():
    return {
        "message": "Two-Way Sync Running 🚀",
        "routes": ["/health", "/sync", "/trello-webhook", "/docs"]
    }
