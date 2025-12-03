import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gspread
from google.oauth2.service_account import Credentials
from two_way_sync.config import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE
from two_way_sync.utils.logger import log_info, log_error


class LeadClient:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self):
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=self.SCOPES
        )
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(GOOGLE_SHEET_ID).sheet1

    def get_all_leads(self):
        """Read all leads and return list of dict objects"""
        rows = self.sheet.get_all_records()
        leads = []
        for row in rows:
            leads.append({
                "id": row.get("Id"),
                "name": row.get("Name"),
                "email": row.get("Email"),
                "status": row.get("Status")
            })
        log_info(f"Fetched {len(leads)} leads from sheet")
        return leads

    def update_lead_status(self, lead_id, new_status):
        """Update lead status by searching its row"""
        try:
            cell = self.sheet.find(lead_id)
            row = cell.row
            status_col = self._get_column_index("status")

            self.sheet.update_cell(row, status_col, new_status)
            log_info(f"Updated lead {lead_id} to {new_status}")
        except Exception as e:
            log_error(f"Failed updating lead: {str(e)}")

    def _get_column_index(self, column_name):
        headers = [h.lower() for h in self.sheet.row_values(1)]
        return headers.index(column_name.lower()) + 1

