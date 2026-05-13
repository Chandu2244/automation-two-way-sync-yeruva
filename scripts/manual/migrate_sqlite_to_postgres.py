"""Copy the local SQLite sync database into PostgreSQL.

Run this once on the server before deleting mapping.db, if you want to preserve
existing mappings, processed events, retry jobs, metadata, and pending echoes.
"""

import json
import os
import sqlite3
from pathlib import Path

import psycopg

from two_way_sync.config import DATABASE_URL
from two_way_sync.db.mapping_store import MappingStore


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = ROOT / "two_way_sync" / "db" / "mapping.db"
SQLITE_PATH = Path(os.getenv("SQLITE_DB_PATH", DEFAULT_SQLITE_PATH))


def sqlite_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def copy_mapping(sqlite_cursor, pg_cursor):
    sqlite_cursor.execute("""
        SELECT lead_id, trello_card_id, trello_status, trello_timestamp,
               sheet_status, sheet_timestamp, last_update_source,
               last_updated_time, last_updated_source
        FROM mapping
    """)
    for row in sqlite_cursor.fetchall():
        pg_cursor.execute("""
            INSERT INTO mapping
            (lead_id, trello_card_id, trello_status, trello_timestamp,
             sheet_status, sheet_timestamp, last_update_source,
             last_updated_time, last_updated_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (lead_id) DO UPDATE SET
                trello_card_id = EXCLUDED.trello_card_id,
                trello_status = EXCLUDED.trello_status,
                trello_timestamp = EXCLUDED.trello_timestamp,
                sheet_status = EXCLUDED.sheet_status,
                sheet_timestamp = EXCLUDED.sheet_timestamp,
                last_update_source = EXCLUDED.last_update_source,
                last_updated_time = EXCLUDED.last_updated_time,
                last_updated_source = EXCLUDED.last_updated_source
        """, row)


def copy_processed_events(sqlite_cursor, pg_cursor):
    sqlite_cursor.execute("SELECT event_id, processed_at, status FROM processed_events")
    for row in sqlite_cursor.fetchall():
        pg_cursor.execute("""
            INSERT INTO processed_events (event_id, processed_at, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (event_id) DO UPDATE SET
                processed_at = EXCLUDED.processed_at,
                status = EXCLUDED.status
        """, row)


def copy_sync_metadata(sqlite_cursor, pg_cursor):
    sqlite_cursor.execute("SELECT key, value FROM sync_metadata")
    for row in sqlite_cursor.fetchall():
        pg_cursor.execute("""
            INSERT INTO sync_metadata (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, row)


def copy_retry_queue(sqlite_cursor, pg_cursor):
    sqlite_cursor.execute("""
        SELECT operation, payload, attempts, max_attempts, next_attempt_at,
               last_error, created_at, updated_at
        FROM retry_queue
        ORDER BY id
    """)
    for row in sqlite_cursor.fetchall():
        payload = row[1]
        payload_json = payload if isinstance(payload, str) else json.dumps(payload)
        pg_cursor.execute("""
            INSERT INTO retry_queue
            (operation, payload, attempts, max_attempts, next_attempt_at,
             last_error, created_at, updated_at)
            VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s)
        """, (row[0], payload_json, *row[2:]))


def copy_pending_echoes(sqlite_cursor, pg_cursor):
    columns = sqlite_columns(sqlite_cursor, "pending_echoes")
    if "expected_timestamp" in columns:
        sqlite_cursor.execute("""
            SELECT lead_id, target_source, status, expected_timestamp, created_at
            FROM pending_echoes
            ORDER BY id
        """)
    else:
        sqlite_cursor.execute("""
            SELECT lead_id, target_source, status, NULL, created_at
            FROM pending_echoes
            ORDER BY id
        """)

    for row in sqlite_cursor.fetchall():
        pg_cursor.execute("""
            INSERT INTO pending_echoes
            (lead_id, target_source, status, expected_timestamp, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, row)


def main():
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not configured")

    MappingStore()

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    try:
        sqlite_cursor = sqlite_conn.cursor()
        with psycopg.connect(DATABASE_URL, connect_timeout=10) as pg_conn:
            with pg_conn.cursor() as pg_cursor:
                copy_mapping(sqlite_cursor, pg_cursor)
                copy_processed_events(sqlite_cursor, pg_cursor)
                copy_sync_metadata(sqlite_cursor, pg_cursor)
                copy_retry_queue(sqlite_cursor, pg_cursor)
                copy_pending_echoes(sqlite_cursor, pg_cursor)
            pg_conn.commit()
    finally:
        sqlite_conn.close()

    print("SQLite data copied to PostgreSQL")


if __name__ == "__main__":
    main()
