"""Manual utility: read and update leads in Google Sheets."""

from two_way_sync.lead_client import LeadClient


def main():
    client = LeadClient()
    leads = client.get_all_leads()
    print(leads)

    if leads:
        client.update_lead_status(leads[0]["id"], "CONTACTED")


if __name__ == "__main__":
    main()
