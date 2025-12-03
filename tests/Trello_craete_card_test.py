import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from two_way_sync.task_client import TrelloClient
client = TrelloClient()
client.create_card("Test Lead Automation", "lead_test_001", "NEW")

# card = client.find_card_by_lead_id("lead_test_001")
# client.update_status(card["id"], "QUALIFIED")
