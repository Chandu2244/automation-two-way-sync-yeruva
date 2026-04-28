"""Manual utility: create a Trello card for quick integration testing."""

from two_way_sync.task_client import TrelloClient


def main():
    client = TrelloClient()
    client.create_card("Test Lead Automation", "lead_test_001", "TODO")


if __name__ == "__main__":
    main()
