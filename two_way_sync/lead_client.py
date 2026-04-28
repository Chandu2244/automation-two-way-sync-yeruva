"""Google Sheets client wrapper with light retry logic."""

import gspread
import time
from google.oauth2.service_account import Credentials
from two_way_sync.config import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE
from two_way_sync.utils.logger import log_info, log_error


class LeadClient:
    """Google Sheets client for reading leads and updating lead status."""

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self):
        """Create an authenticated Sheets client for the first worksheet."""
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=self.SCOPES
        )
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(GOOGLE_SHEET_ID).sheet1

    def _with_retry(self, action, action_name):
        """Retry transient API operations up to three times."""
        last_error = None
        for attempt in range(1, 4):
            try:
                return action()
            except Exception as exc:
                last_error = exc
                log_error(f"{action_name} failed (attempt {attempt}/3): {exc}")
                if attempt < 3:
                    time.sleep(0.6 * attempt)
        raise last_error

    def get_all_leads(self):
        """Read all rows from the first worksheet as normalized lead dictionaries."""
        try:
            rows = self._with_retry(self.sheet.get_all_records, "Fetch leads")
        except Exception as exc:
            log_error(f"Failed fetching leads: {exc}")
            return []

        leads = []
        for row in rows:
            leads.append({
                "id": row.get("Id"),
                "name": row.get("Name"),
                "email": row.get("Email"),
                "status": row.get("Status"),
                "last_updated_time": (
                    row.get("last_updated_time")
                    or row.get("Last Updated Time")
                    or row.get("Updated At")
                ),
            })
        log_info(f"Fetched {len(leads)} leads from sheet")
        return leads

    def update_lead_status(self, lead_id, new_status, updated_time=None, updated_source="trello"):
        """Update a lead status and optional sync metadata columns."""
        try:
            cell = self._with_retry(lambda: self.sheet.find(lead_id), "Find lead row")
            row = cell.row
            status_col = self._get_column_index("status")

            self._with_retry(
                lambda: self.sheet.update_cell(row, status_col, new_status),
                "Update lead status",
            )
            if updated_time:
                self._update_column_if_present(row, "last_updated_time", updated_time)
                self._update_column_if_present(row, "last_updated_source", updated_source)
            log_info(f"Updated lead {lead_id} to {new_status}")
            return True
        except Exception as e:
            log_error(f"Failed updating lead: {str(e)}")
            return False

    def _get_column_index(self, column_name):
        """Return 1-based column index by header name."""
        headers = [h.lower() for h in self._with_retry(lambda: self.sheet.row_values(1), "Fetch headers")]
        return headers.index(column_name.lower()) + 1

    def _update_column_if_present(self, row, column_name, value):
        """Update a metadata column only when the sheet actually has it."""
        try:
            column = self._get_column_index(column_name)
        except ValueError:
            return
        self._with_retry(
            lambda: self.sheet.update_cell(row, column, value),
            f"Update {column_name}",
        )

