import sqlite3
import os

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
                trello_status TEXT,
                trello_timestamp TEXT,
                sheet_status TEXT,
                sheet_timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    # --------------------------------
    # CRUD Operations
    # --------------------------------
    def get(self, lead_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT trello_card_id, trello_status, trello_timestamp,
                   sheet_status, sheet_timestamp
            FROM mapping WHERE lead_id=?
        """, (lead_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "trello_card_id": row[0],
            "trello_status": row[1],
            "trello_timestamp": row[2],
            "sheet_status": row[3],
            "sheet_timestamp": row[4],
        }

    def get_card_id(self, lead_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trello_card_id FROM mapping WHERE lead_id=?", (lead_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def upsert(self, lead_id, trello_card_id=None, trello_status=None,
               trello_timestamp=None, sheet_status=None, sheet_timestamp=None):
        existing = self.get(lead_id)

        trello_card_id = trello_card_id or (existing.get("trello_card_id") if existing else None)
        trello_status = trello_status or (existing.get("trello_status") if existing else None)
        trello_timestamp = trello_timestamp or (existing.get("trello_timestamp") if existing else None)
        sheet_status = sheet_status or (existing.get("sheet_status") if existing else None)
        sheet_timestamp = sheet_timestamp or (existing.get("sheet_timestamp") if existing else None)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO mapping 
            (lead_id, trello_card_id, trello_status, trello_timestamp,
             sheet_status, sheet_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (lead_id, trello_card_id, trello_status, trello_timestamp,
              sheet_status, sheet_timestamp))
        conn.commit()
        conn.close()

    def delete(self, lead_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mapping WHERE lead_id=?", (lead_id,))
        conn.commit()
        conn.close()

    def get_all_lead_ids(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT lead_id FROM mapping")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
