"""SQLite persistence for sync mappings, idempotency, retries, and metadata."""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "mapping.db")


class MappingStore:
    """Small SQLite repository used by the sync service."""

    def __init__(self):
        """Create or migrate the local database schema."""
        self._create_table()

    def _connect(self):
        """Open a SQLite connection configured for webhook concurrency."""
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        return conn

    def _create_table(self):
        """Create all runtime tables if they do not already exist."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mapping (
                    lead_id TEXT PRIMARY KEY,
                    trello_card_id TEXT,
                    trello_status TEXT,
                    trello_timestamp TEXT,
                    sheet_status TEXT,
                    sheet_timestamp TEXT,
                    last_update_source TEXT,
                    last_updated_time TEXT,
                    last_updated_source TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    processed_at TEXT,
                    status TEXT DEFAULT 'processing'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS retry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_echoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    target_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_timestamp TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            self._ensure_column(cursor, "mapping", "last_update_source", "TEXT")
            self._ensure_column(cursor, "mapping", "last_updated_time", "TEXT")
            self._ensure_column(cursor, "mapping", "last_updated_source", "TEXT")
            self._ensure_column(cursor, "processed_events", "status", "TEXT DEFAULT 'processing'")
            self._ensure_column(cursor, "pending_echoes", "expected_timestamp", "TEXT")
            conn.commit()

    def _ensure_column(self, cursor, table_name, column_name, column_type):
        """Add a column for lightweight schema migrations."""
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def get(self, lead_id):
        """Return persisted sync state for one lead."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT trello_card_id, trello_status, trello_timestamp,
                       sheet_status, sheet_timestamp, last_update_source,
                       last_updated_time, last_updated_source
                FROM mapping WHERE lead_id = ?
            """, (lead_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "trello_card_id": row[0],
            "trello_status": row[1],
            "trello_timestamp": row[2],
            "sheet_status": row[3],
            "sheet_timestamp": row[4],
            "last_update_source": row[5],
            "last_updated_time": row[6],
            "last_updated_source": row[7],
        }

    def exists(self, lead_id):
        """Return True when a lead has local sync state."""
        return self.get(lead_id) is not None

    def get_card_id(self, lead_id):
        """Return the Trello card ID mapped to a lead."""
        row = self.get(lead_id)
        return row["trello_card_id"] if row else None

    def get_all_lead_ids(self):
        """Return all lead IDs tracked in the mapping table."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lead_id FROM mapping")
            return [row[0] for row in cursor.fetchall()]

    def upsert(
        self,
        lead_id,
        trello_card_id=None,
        trello_status=None,
        trello_timestamp=None,
        sheet_status=None,
        sheet_timestamp=None,
        last_update_source=None,
        last_updated_time=None,
        last_updated_source=None,
    ):
        """Insert or update one mapping while preserving omitted fields."""
        existing = self.get(lead_id) or {}
        values = (
            lead_id,
            trello_card_id or existing.get("trello_card_id"),
            trello_status or existing.get("trello_status"),
            trello_timestamp or existing.get("trello_timestamp"),
            sheet_status or existing.get("sheet_status"),
            sheet_timestamp or existing.get("sheet_timestamp"),
            last_update_source or existing.get("last_update_source"),
            last_updated_time or existing.get("last_updated_time"),
            last_updated_source or existing.get("last_updated_source"),
        )

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO mapping
                (lead_id, trello_card_id, trello_status, trello_timestamp,
                 sheet_status, sheet_timestamp, last_update_source,
                 last_updated_time, last_updated_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values)
            conn.commit()

    def update_timestamp_from_trello(self, lead_id, timestamp=None):
        """Legacy helper to stamp a mapping after a Trello-origin update."""
        timestamp = timestamp or datetime.utcnow().isoformat()
        self.upsert(
            lead_id,
            trello_timestamp=timestamp,
            last_update_source="trello",
            last_updated_time=timestamp,
            last_updated_source="trello",
        )

    def try_claim_event(self, event_id):
        """Atomically reserve a Trello event ID before processing it."""
        if not event_id:
            return True
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO processed_events (event_id, processed_at, status)
                VALUES (?, ?, 'processing')
            """, (event_id, datetime.utcnow().isoformat()))
            conn.commit()
            return cursor.rowcount == 1

    def is_event_processed(self, event_id):
        """Return True if an event has already been claimed or processed."""
        if not event_id:
            return False
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,))
            return cursor.fetchone() is not None

    def mark_event_processed(self, event_id):
        """Mark a claimed Trello event as completed."""
        if not event_id:
            return
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processed_events (event_id, processed_at, status)
                VALUES (?, ?, 'processed')
                ON CONFLICT(event_id) DO UPDATE SET
                    processed_at = excluded.processed_at,
                    status = 'processed'
            """, (event_id, datetime.utcnow().isoformat()))
            conn.commit()

    def release_event_claim(self, event_id):
        """Release a failed event claim so Trello can retry later."""
        if not event_id:
            return
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM processed_events WHERE event_id = ? AND status = 'processing'",
                (event_id,),
            )
            conn.commit()

    def delete(self, lead_id):
        """Delete local sync state for one lead."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mapping WHERE lead_id = ?", (lead_id,))
            conn.commit()

    def get_metadata(self, key, default=None):
        """Read a global sync metadata value."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sync_metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_metadata(self, key, value):
        """Persist a global sync metadata value."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sync_metadata (key, value)
                VALUES (?, ?)
            """, (key, value))
            conn.commit()

    def enqueue_retry(self, operation, payload, error=None, max_attempts=5):
        """Queue or refresh a failed operation for later retry."""
        now = datetime.utcnow().isoformat()
        payload_json = json.dumps(payload)
        lead_id = payload.get("lead_id")

        with self._connect() as conn:
            cursor = conn.cursor()
            if lead_id:
                cursor.execute("""
                    SELECT id FROM retry_queue
                    WHERE operation = ?
                      AND json_extract(payload, '$.lead_id') = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (operation, lead_id))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        UPDATE retry_queue
                        SET payload = ?,
                            next_attempt_at = ?,
                            last_error = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (payload_json, now, str(error) if error else None, now, row[0]))
                    conn.commit()
                    return

            cursor.execute("""
                INSERT INTO retry_queue
                (operation, payload, attempts, max_attempts, next_attempt_at,
                 last_error, created_at, updated_at)
                VALUES (?, ?, 0, ?, ?, ?, ?, ?)
            """, (
                operation,
                payload_json,
                max_attempts,
                now,
                str(error) if error else None,
                now,
                now,
            ))
            conn.commit()

    def get_due_retries(self, limit=25):
        """Return retry jobs whose next attempt time has arrived."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, operation, payload, attempts, max_attempts
                FROM retry_queue
                WHERE next_attempt_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (now, limit))
            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "operation": row[1],
                "payload": json.loads(row[2]),
                "attempts": row[3],
                "max_attempts": row[4],
            }
            for row in rows
        ]

    def mark_retry_success(self, retry_id):
        """Remove a retry job after success."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM retry_queue WHERE id = ?", (retry_id,))
            conn.commit()

    def mark_retry_failed(self, retry_id, attempts, error, next_attempt_at):
        """Record a failed retry attempt and schedule the next attempt."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE retry_queue
                SET attempts = ?,
                    next_attempt_at = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
            """, (attempts, next_attempt_at, str(error), now, retry_id))
            conn.commit()

    def drop_retry(self, retry_id):
        """Drop a retry job after max attempts or invalid data."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM retry_queue WHERE id = ?", (retry_id,))
            conn.commit()

    def record_pending_echo(self, lead_id, target_source, status, expected_timestamp=None):
        """Record an expected webhook/event caused by our own outbound write."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pending_echoes
                (lead_id, target_source, status, expected_timestamp, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                lead_id,
                target_source,
                (status or "").upper().strip(),
                expected_timestamp,
                datetime.utcnow().isoformat(),
            ))
            conn.commit()

    def consume_pending_echo(
        self,
        lead_id,
        target_source,
        status,
        incoming_timestamp=None,
        ttl_seconds=600,
    ):
        """Return True and delete a recent expected echo event."""
        cutoff = (
            datetime.utcnow().replace(tzinfo=timezone.utc)
            - timedelta(seconds=ttl_seconds)
        ).replace(tzinfo=None).isoformat()
        status = (status or "").upper().strip()

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_echoes WHERE created_at < ?", (cutoff,))
            cursor.execute("""
                SELECT id, expected_timestamp FROM pending_echoes
                WHERE lead_id = ?
                  AND target_source = ?
                  AND status = ?
                ORDER BY created_at ASC
            """, (lead_id, target_source, status))
            rows = cursor.fetchall()
            if not rows:
                conn.commit()
                return False

            if target_source != "sheets":
                cursor.execute("DELETE FROM pending_echoes WHERE id = ?", (rows[0][0],))
                conn.commit()
                return True

            legacy_echo_ids = []
            for echo_id, expected_timestamp in rows:
                if not expected_timestamp:
                    legacy_echo_ids.append(echo_id)
                    continue
                if self._timestamps_match(incoming_timestamp, expected_timestamp):
                    if legacy_echo_ids:
                        cursor.executemany(
                            "DELETE FROM pending_echoes WHERE id = ?",
                            [(item_id,) for item_id in legacy_echo_ids],
                        )
                    cursor.execute("DELETE FROM pending_echoes WHERE id = ?", (echo_id,))
                    conn.commit()
                    return True

            if legacy_echo_ids:
                cursor.executemany(
                    "DELETE FROM pending_echoes WHERE id = ?",
                    [(item_id,) for item_id in legacy_echo_ids],
                )
            conn.commit()
            return False

    def _timestamps_match(self, first, second, tolerance_seconds=2):
        """Return True when two webhook timestamps refer to the same write."""
        first_dt = self._parse_timestamp(first)
        second_dt = self._parse_timestamp(second)
        if first_dt and second_dt:
            return abs((first_dt - second_dt).total_seconds()) <= tolerance_seconds
        return (first or "").strip() == (second or "").strip()

    def _parse_timestamp(self, value):
        if not value or not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
