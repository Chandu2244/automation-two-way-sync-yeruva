"""FastAPI entrypoint for the Google Sheets <-> Trello sync service."""

from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from two_way_sync.config import SHEETS_SHARED_SECRET, validate_config
from two_way_sync.db.mapping_store import MappingStore
from two_way_sync.scheduler import SyncScheduler
from two_way_sync.sync_logic import STATUS_FROM_TRELLO, SyncService
from two_way_sync.task_client import TrelloClient
from two_way_sync.utils.logger import log_error, log_info

app = FastAPI()
scheduler = SyncScheduler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SheetSyncPayload(BaseModel):
    lead_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    name: str = ""
    email: str = ""
    sheet_timestamp: str | None = None
    last_updated_time: str | None = None


@app.on_event("startup")
async def startup_event():
    """Validate config and start background catch-up/safety jobs."""
    validate_config()
    scheduler.start()
    log_info("Configuration validated successfully")


@app.on_event("shutdown")
async def shutdown_event():
    await scheduler.stop()


@app.get("/health")
async def health_check():
    """Lightweight liveness endpoint."""
    return {"status": "UP"}


@app.post("/sync")
async def sync_from_sheets(
    payload: SheetSyncPayload,
    x_sync_secret: str | None = Header(default=None),
):
    """Event-driven Sheets -> Trello sync trigger."""
    if SHEETS_SHARED_SECRET and x_sync_secret != SHEETS_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid sync secret")

    lead_id = payload.lead_id.strip()
    status = payload.status.upper().strip()
    incoming_time = (
        payload.last_updated_time
        or payload.sheet_timestamp
        or datetime.utcnow().isoformat()
    )

    log_info(f"Sheet event received lead_id={lead_id} incoming_time={incoming_time}")

    if not lead_id or not status:
        raise HTTPException(status_code=422, detail="lead_id and status are required")

    try:
        result = SyncService().apply_sheets_event(
            lead_id,
            payload.name.strip(),
            payload.email.strip(),
            status,
            incoming_time,
        )
    except Exception as exc:
        log_error(f"Sheets event failed lead_id={lead_id}: {exc}")
        raise HTTPException(status_code=500, detail="Sync processing failed")

    return {"source": "sheets", "lead_id": lead_id, **result}


@app.post("/trello-webhook")
@app.post("/trello-webhook/")
async def trello_webhook_handler(request: Request):
    """Event-driven Trello -> Sheets sync trigger."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    store = MappingStore()
    trello_client = TrelloClient()
    event_id = None

    try:
        action = body.get("action", {})
        event_id = action.get("id")
        action_type = action.get("type")
        data = action.get("data", {})
        card_data = data.get("card", {})
        card_id = card_data.get("id")

        log_info(f"Trello webhook received event_id={event_id} type={action_type}")

        if event_id and not store.try_claim_event(event_id):
            return {"ignored": "duplicate_event"}
        if not card_id:
            store.mark_event_processed(event_id)
            return {"ignored": "no_card"}

        lead_id = trello_client.get_lead_id_value(card_id)
        if not lead_id:
            store.mark_event_processed(event_id)
            return {"ignored": "not_synced_card"}

        incoming_time = action.get("date") or datetime.utcnow().isoformat()
        status = _status_from_trello_webhook(data, card_data, trello_client, card_id)
        if not status:
            store.mark_event_processed(event_id)
            return {"ignored": "no_status_change"}

        result = SyncService(store=store, trello_client=trello_client).apply_trello_event(
            lead_id,
            status,
            incoming_time,
            card_id,
        )
        store.mark_event_processed(event_id)
        return {"source": "trello", "lead_id": lead_id, "status": status, **result}
    except Exception as exc:
        store.release_event_claim(event_id)
        log_error(f"Trello webhook handling failed: {exc}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


def _status_from_trello_webhook(data, card_data, trello_client, card_id):
    if card_data.get("closed", False):
        return "LOST"

    list_after_name = data.get("listAfter", {}).get("name", "").upper()
    if list_after_name:
        return STATUS_FROM_TRELLO.get(list_after_name)

    card_details = trello_client.get_card_details(card_id)
    list_id = card_details.get("idList")
    trello_status = trello_client.LIST_TO_STATUS.get(list_id)
    return STATUS_FROM_TRELLO.get(trello_status)


@app.get("/trello-webhook")
@app.get("/trello-webhook/")
async def validate_trello_webhook():
    """Trello webhook validation endpoint."""
    return Response(content="OK", status_code=200)


@app.head("/trello-webhook")
@app.head("/trello-webhook/")
async def trello_webhook_head():
    """Trello webhook HEAD validation endpoint."""
    return Response(status_code=200)


@app.get("/")
async def root():
    """Service info endpoint."""
    return {
        "message": "Two-Way Sync Service Running",
        "routes": ["/health", "/sync", "/trello-webhook", "/docs"],
        "sync_layers": [
            "event_driven",
            "idempotency",
            "incremental",
            "retry_queue",
            "scheduled_reconciliation",
        ],
    }
