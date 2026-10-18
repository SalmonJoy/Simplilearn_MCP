from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from Inventory_management.services import inventory_service
from seed import seed_database

EMPLOYEE = {
    "employee_id": "EMP999",
    "full_name": "  Test Learner  ",
    "email": "TEST@EXAMPLE.TEST",
    "department": "Engineering",
    "designation": "Engineer",
    "joining_date": "2026-10-17",
}


def test_nine_business_endpoints(clients):
    hrms, inventory = clients
    h = hrms.get("/openapi.json").json()["paths"]
    i = inventory.get("/openapi.json").json()["paths"]
    assert (
        sum(len(operations) for path, operations in h.items() if path != "/health") == 5
    )
    assert (
        sum(len(operations) for path, operations in i.items() if path != "/health") == 4
    )


def test_employee_create_update_and_duplicates(clients):
    hrms, _ = clients
    created = hrms.post("/employees", json=EMPLOYEE)
    assert created.status_code == 201
    assert created.json()["email"] == "test@example.test"
    assert created.json()["full_name"] == "Test Learner"
    assert created.json()["status"] == "joining"
    assert hrms.post("/employees", json=EMPLOYEE).status_code == 409
    assert (
        hrms.post("/employees", json={**EMPLOYEE, "employee_id": "EMP998"}).status_code
        == 409
    )
    assert (
        hrms.patch("/employees/EMP999", json={"department": "Finance"}).json()[
            "department"
        ]
        == "Finance"
    )
    assert hrms.get("/employees/EMP999").json()["department"] == "Finance"
    assert hrms.get("/employees/missing").status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"email": None},
        {"employee_id": "NEW"},
        {"email": "invalid"},
        {"status": "other"},
        {"department": "  "},
    ],
)
def test_invalid_patches(clients, changes):
    assert clients[0].patch("/employees/EMP001", json=changes).status_code == 422


def test_patch_email_uniqueness(clients, seeded):
    assert (
        clients[0]
        .patch("/employees/EMP001", json={"email": "EMPLOYEE002@EXAMPLE.TEST"})
        .status_code
        == 409
    )


def test_filters_pagination_and_summary(clients, seeded):
    hrms, _ = clients
    page = hrms.get("/employees", params={"limit": 7}).json()
    assert len(page["items"]) == 7 and page["total"] == 30 and page["has_more"]
    assert page["items"][0]["employee_id"] == "EMP001"
    assert (
        hrms.get("/employees", params={"name": ".*"}).json()["total"] == 0
    )  # literal search
    assert hrms.get("/employees", params={"name": "asha"}).json()["total"] == 3
    filtered = hrms.get(
        "/employees", params={"department": "Finance", "status": "active", "limit": 100}
    ).json()
    summary = hrms.get(
        "/employees/summary", params={"department": "Finance", "status": "active"}
    ).json()
    assert filtered["total"] == summary["total"]
    assert sum(summary["by_department"].values()) == summary["total"]
    assert sum(summary["by_joining_month"].values()) == summary["total"]
    date = hrms.get("/employees/EMP001").json()["joining_date"]
    exact = hrms.get(
        "/employees", params={"joining_from": date, "joining_to": date}
    ).json()
    assert any(e["employee_id"] == "EMP001" for e in exact["items"])
    assert (
        hrms.get(
            "/employees",
            params={"joining_from": "2026-10-18", "joining_to": "2026-10-01"},
        ).status_code
        == 422
    )
    assert hrms.get("/employees", params={"limit": 101}).status_code == 422


def test_seed_is_insert_only(seeded):
    seeded.employees.update_one({"_id": "EMP001"}, {"$set": {"department": "Custom"}})
    seeded.inventory_items.update_one({"_id": "ITEM021"}, {"$set": {"name": "Custom"}})
    result = seed_database(seeded)
    assert result == {
        "employees_created": 0,
        "items_created": 0,
        "employees_total": 30,
        "items_total": 60,
    }
    assert seeded.employees.find_one({"_id": "EMP001"})["department"] == "Custom"
    assert seeded.inventory_items.find_one({"_id": "ITEM021"})["name"] == "Custom"


def test_assign_return_and_conflicts(clients, seeded, monkeypatch):
    _, inventory = clients
    monkeypatch.setattr(inventory_service, "validate_employee", lambda employee: None)
    response = inventory.post("/items/ITEM021/assign", json={"employee_id": "EMP001"})
    assert (
        response.status_code == 200
        and response.json()["assignment"]["employee_id"] == "EMP001"
    )
    assert (
        inventory.post(
            "/items/ITEM021/assign", json={"employee_id": "EMP002"}
        ).status_code
        == 409
    )
    assert (
        inventory.post(
            "/items/ITEM021/return", json={"employee_id": "EMP002"}
        ).status_code
        == 409
    )
    assert (
        inventory.post("/items/ITEM021/return", json={"employee_id": "EMP001"}).json()[
            "assignment"
        ]
        is None
    )
    assert (
        inventory.post(
            "/items/ITEM021/return", json={"employee_id": "EMP001"}
        ).status_code
        == 409
    )
    assert inventory.get("/items/missing").status_code == 404


def test_atomic_competing_assignments(seeded, monkeypatch):
    monkeypatch.setattr(inventory_service, "validate_employee", lambda employee: None)

    def assign(employee):
        try:
            inventory_service.assign_item(seeded.inventory_items, "ITEM021", employee)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(assign, ["EMP001", "EMP002"])) == [200, 409]


def test_employee_validation_errors(clients, seeded, monkeypatch):
    hrms, inventory = clients
    monkeypatch.setattr(
        inventory_service.httpx,
        "get",
        lambda url, timeout: hrms.get("/employees/" + url.rsplit("/", 1)[-1]),
    )
    assert (
        inventory.post(
            "/items/ITEM021/assign", json={"employee_id": "EMP999"}
        ).status_code
        == 404
    )
    assert (
        inventory.post(
            "/items/ITEM021/assign", json={"employee_id": "EMP010"}
        ).status_code
        == 409
    )
    assert (
        inventory.post(
            "/items/ITEM021/assign", json={"employee_id": "EMP005"}
        ).status_code
        == 200
    )
    hrms.patch("/employees/EMP005", json={"status": "inactive"})
    assert (
        inventory.get("/items/ITEM021").json()["assignment"]["employee_id"] == "EMP005"
    )


def test_empty_data_and_inventory_filters(clients, database):
    hrms, inventory = clients
    assert hrms.get("/employees").json()["items"] == []
    assert hrms.get("/employees/summary").json()["total"] == 0
    seed_database(database)
    items = inventory.get(
        "/items", params={"category": "device", "employee_id": "EMP001", "limit": 100}
    ).json()
    assert all(
        item["category"] == "device" and item["assignment"]["employee_id"] == "EMP001"
        for item in items["items"]
    )


def test_unavailable_dependencies(clients, seeded, monkeypatch):
    import httpx
    from pymongo.errors import ConnectionFailure

    def fail(*args, **kwargs):
        raise ConnectionFailure("Simulated failure")

    monkeypatch.setattr(seeded.employees, "find_one", fail)
    assert clients[0].get("/employees/EMP001").status_code == 503

    def network_error(*args, **kwargs):
        raise httpx.ConnectError("Simulated failure")

    monkeypatch.setattr(inventory_service.httpx, "get", network_error)
    assert (
        clients[1]
        .post("/items/ITEM021/assign", json={"employee_id": "EMP001"})
        .status_code
        == 503
    )
