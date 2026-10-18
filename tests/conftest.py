import mongomock
import pytest
from fastapi.testclient import TestClient
from HRMS.main import app as hrms
from Inventory_management.main import app as inventory
from HRMS import database as hrms_db
from Inventory_management import database as inventory_db
from seed import seed_database


@pytest.fixture
def database():
    client = mongomock.MongoClient(tz_aware=True)
    return client.mcp_learning


@pytest.fixture
def clients(database, monkeypatch):
    monkeypatch.setattr(
        hrms_db, "connect", lambda: (database.client, database.employees)
    )
    monkeypatch.setattr(
        inventory_db, "connect", lambda: (database.client, database.inventory_items)
    )
    with TestClient(hrms) as hrms_client, TestClient(inventory) as inventory_client:
        yield hrms_client, inventory_client


@pytest.fixture
def seeded(database):
    seed_database(database)
    return database
