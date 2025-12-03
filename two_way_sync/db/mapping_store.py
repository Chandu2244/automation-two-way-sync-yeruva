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
                trello_card_id TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def get_card_id(self, lead_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT trello_card_id FROM mapping WHERE lead_id=?", (lead_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def set_mapping(self, lead_id, trello_card_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO mapping (lead_id, trello_card_id)
            VALUES (?, ?)
        """, (lead_id, trello_card_id))
        conn.commit()
        conn.close()

    def delete_mapping(self, lead_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mapping WHERE lead_id=?", (lead_id,))
        conn.commit()
        conn.close()
