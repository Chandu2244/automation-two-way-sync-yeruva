# 🚀 Two-Way Lead Sync Automation

### Google Sheets ⇄ Trello | FastAPI | Webhooks + Real-Time Sync | Ngrok Public Tunnel

This project automates lead synchronization between:

📊 **Google Sheets** — Sales team lead tracking
📌 **Trello** — Task execution and progress

Updates in **one system** instantly reflect in the **other**.
Built with real integration techniques used in production systems.

---

## 🎯 Problem → Solution

| CRM Reality                          | This System's Solution            |
| ------------------------------------ | --------------------------------- |
| Sheets & Trello often go out of sync | Instant two-way sync              |
| Manual updates cause delays & errors | Fully automated sync engine       |
| Archived leads are forgotten         | Automatic LOST lifecycle tracking |
| Webhooks require a public server     | Secure ngrok tunnel used          |

This is not just CRUD —
it’s **workflow automation across two SaaS platforms**.

---

## 🧠 System Architecture

```
┌───────────────┐      Sheets Trigger/API   ┌──────────────┐
│ Google Sheets │ ───────────────────────→ │ FastAPI Sync  │
└───────────────┘                          │ Service (Local│
      ↑                                     │ + Ngrok Tunnel│
 Reverse Sync (Webhook)                     └──────────────┘
      │                                                  │
      └──────────── Trello Webhook Events ───────────────┘
                      Trello (Board + Lists)
```

---

🔁 Sync Logic

| Action                         | Synced Behavior             |
| ------------------------------ | --------------------------- |
| Sheet: NEW → TODO              | Create new card             |
| Sheet: CONTACTED → IN_PROGRESS | Move to next Trello stage   |
| Sheet: QUALIFIED → DONE        | Mark card as completed      |
| Sheet: LOST                    | Archive card in Trello      |
| Trello move between lists      | Sheet status auto-updates   |
| Trello archive                 | Sheet → LOST                |
| Trello restore                 | Sheet restores prior status |
| Delete ID in Sheet             | Card automatically archived |

✔ Only meaningful changes sync
✔ Skips duplicate updates
✔ Ensures latest source wins

---

## 🛡️ Reliability + Data Integrity Proofs

| Feature               | Why it matters              |
| --------------------- | --------------------------- |
| Idempotent updates    | Prevent infinite sync loops |
| Mapping DB            | No accidental duplicates    |
| Timestamp-based state | Solves race conditions      |
| Fallback full sync    | Recovers mismatches         |
| Smart ignores         | Stops noisy webhook events  |

Built to handle **edge cases** like a real production system.

---

## 🛠️ Tech Stack

| Category         | Tools                                         |
| ---------------- | --------------------------------------------- |
| Backend          | Python, FastAPI, Uvicorn                      |
| Integrations     | Trello REST API & Webhooks, Google Sheets API |
| Auth             | Google Service Account                        |
| Local Deployment | Ngrok Public Tunnel                           |
| DB               | SQLite (Mapping Store)                        |
| Logging          | Structured logs for debugging and audits      |

---

## 📁 Project Structure

```text
.
├── app.py                         # FastAPI entrypoint
├── two_way_sync/                  # Core sync package
│   ├── config.py                  # Environment configuration
│   ├── lead_client.py             # Google Sheets client
│   ├── task_client.py             # Trello API client
│   ├── sync_logic.py              # Sync orchestration logic
│   ├── db/
│   │   ├── mapping_store.py       # SQLite mapping operations
│   │   └── mapping.db             # Local mapping database
│   └── utils/logger.py            # Logging helpers
└── scripts/manual/                # Manual utilities for local checks
    ├── register_trello_webhook.py
    ├── test_bot_identity_manual.py
    ├── test_connections_manual.py
    ├── test_sheets_manual.py
    └── test_trello_create_card_manual.py
```

---

## 🌐 Deployment: Ngrok

Since Trello needs a **public URL** for webhook events,
ngrok is used to securely forward traffic to local FastAPI service.

### Steps

```bash
uvicorn app:app --reload --port 8000
ngrok http 8000
```

ngrok will generate a URL like:

```
https://abc123.ngrok-free.app
```

Update this URL in:

| Place                        | Endpoint                                       |
| ---------------------------- | ---------------------------------------------- |
| Trello Webhook               | `https://abc123.ngrok-free.app/trello-webhook` |
| Google Sheets Trigger Script | `https://abc123.ngrok-free.app/sync`           |

✔ Perfect secure testing environment
✔ No server cost
✔ Works in interviews to demo real sync behavior live 🔥

---

## 🧪 Manual Utility Scripts

Run these only when needed during setup or troubleshooting:

```bash
python scripts/manual/register_trello_webhook.py
python scripts/manual/test_connections_manual.py
python scripts/manual/test_sheets_manual.py
python scripts/manual/test_trello_create_card_manual.py
python scripts/manual/test_bot_identity_manual.py
```

---

## 📡 API Endpoints

| Verb | Route             | Purpose                     |
| ---- | ----------------- | --------------------------- |
| GET  | `/health`         | Service alive check         |
| POST | `/sync`           | Sheet → Trello partial sync |
| POST | `/trello-webhook` | Trello → Sheet reverse sync |
| GET  | `/docs`           | Swagger UI                  |

---


## 💡 Engineering Skills Applied Throughout the Solution

| Skill                | Demonstrated Through             |
| -------------------- | -------------------------------- |
| Event-driven design  | Trello → Sheets Webhook          |
| Sync automation      | Polling + triggers               |
| Data consistency     | Timestamp conflict resolution    |
| API integrations     | Trello + Sheets bidirectional    |
| Robust logic         | Loop-prevention and ID mapping   |
| Practical deployment | Ngrok webhook tunnel             |
| Troubleshooting      | Handling double-trigger behavior |

**real automation systems** used in CRMs & SaaS.

---

## 📈 Future Enhancements

| Future Feature                        | Why it matters                                 |
| ------------------------------------- | ---------------------------------------------- |
| **Analytics dashboard**               | Managers can see lead progress visually        |
| **Retry queue**                       | If API fails, sync retries later — reliability |
| **Multi-board / multi-sheet mapping** | Bigger companies support multiple teams        |
| **Background job processing**         | Sync works even with high volume data          |
| **OAuth User login**                  | Real users sign in and manage their own boards |

---

## 📝 Demo Video

[![Demo Video](https://img.youtube.com/vi/YQefAxYvM_M/0.jpg)](https://youtu.be/YQefAxYvM_M)

---

## 👨‍💻 Author

**Yeruva**
Backend Developer — API Integrations & Automation
📍 Hyderabad, India








