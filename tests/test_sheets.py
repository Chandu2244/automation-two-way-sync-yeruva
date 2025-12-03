import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from two_way_sync.lead_client import LeadClient

client = LeadClient()
leads = client.get_all_leads()
print(leads)

client.update_lead_status(leads[0]["id"], "CONTACTED")
