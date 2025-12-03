import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "mapping.db")


class MappingStore:

    def __init__(self):
        self._create_table()

    def _create_table(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mapping (
                lead_id TEXT PRIMARY KEY,
                trello_card_id TEXT,
                sheet_status TEXT,
                sheet_timestamp TEXT,
                trello_status TEXT,
                trello_timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    def get(self, lead_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mapping WHERE lead_id=?", (lead_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "lead_id": row[0],
            "trello_card_id": row[1],
            "sheet_status": row[2],
            "sheet_timestamp": row[3],
            "trello_status": row[4],
            "trello_timestamp": row[5],
        }

    def upsert(self, lead_id, trello_card_id=None,
               sheet_status=None, sheet_timestamp=None,
               trello_status=None, trello_timestamp=None):

        existing = self.get(lead_id)
        if not existing:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mapping
                (lead_id, trello_card_id, sheet_status, sheet_timestamp,
                 trello_status, trello_timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (lead_id, trello_card_id, sheet_status,
                  sheet_timestamp, trello_status, trello_timestamp))
            conn.commit()
            conn.close()
            return

        # Only overwrite provided fields
        new_data = {
            "trello_card_id": trello_card_id or existing["trello_card_id"],
            "sheet_status": sheet_status or existing["sheet_status"],
            "sheet_timestamp": sheet_timestamp or existing["sheet_timestamp"],
            "trello_status": trello_status or existing["trello_status"],
            "trello_timestamp": trello_timestamp or existing["trello_timestamp"],
        }

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE mapping
            SET trello_card_id=?, sheet_status=?, sheet_timestamp=?,
                trello_status=?, trello_timestamp=?
            WHERE lead_id=?
        """, (new_data["trello_card_id"], new_data["sheet_status"],
              new_data["sheet_timestamp"], new_data["trello_status"],
              new_data["trello_timestamp"], lead_id))
        conn.commit()
        conn.close()
