import os
from datetime import date, timedelta
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5433/customer_feedback_complaint_test",
)

from fastapi.testclient import TestClient
from sqlalchemy import text

from database import engine
from main import app

client = TestClient(app)


def unique_email():
    return f"filter_{uuid4().hex[:10]}@example.com"


def register_user(role="CUSTOMER"):
    email = unique_email()
    password = "TestPassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"Filter Test {role.title()}",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code in (200, 201), response.text

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    if role != "CUSTOMER":
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200, me.text

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET role = :role, is_active = TRUE "
                    "WHERE id = :user_id"
                ),
                {"role": role, "user_id": me.json()["id"]},
            )

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

    return {
        "email": email,
        "password": password,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def create_customer_profile(user, manager):
    response = client.post(
        "/api/v1/customers",
        headers=manager["headers"],
        json={
            "full_name": f"Customer {uuid4().hex[:6]}",
            "email": user["email"],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_category(manager):
    response = client.post(
        "/api/v1/categories",
        headers=manager["headers"],
        json={
            "name": f"Filter Category {uuid4().hex[:8]}",
            "description": "Category for filter tests",
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_complaint(customer, category_id, **overrides):
    payload = {
        "category_id": category_id,
        "title": f"Filter complaint {uuid4().hex[:8]}",
        "description": "Complaint created to test combined filtering.",
        "priority": "HIGH",
        "severity": "MEDIUM",
        "attachment_urls": [],
    }
    payload.update(overrides)

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def list_complaints(manager, params=None):
    response = client.get(
        "/api/v1/complaints",
        headers=manager["headers"],
        params=params or {},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    if isinstance(data, list):
        return data

    return data.get("items", [])


def test_filter_complaints_by_priority():
    manager = register_user("SUPPORT_MANAGER")
    customer = register_user()
    create_customer_profile(customer, manager)
    category = create_category(manager)

    create_complaint(customer, category["id"], priority="HIGH")
    create_complaint(customer, category["id"], priority="LOW")

    results = list_complaints(manager, {"priority": "HIGH"})

    assert results
    assert all(item["priority"] == "HIGH" for item in results)


def test_filter_complaints_by_category():
    manager = register_user("SUPPORT_MANAGER")
    customer = register_user()
    create_customer_profile(customer, manager)

    category1 = create_category(manager)
    category2 = create_category(manager)

    expected = create_complaint(customer, category1["id"])
    create_complaint(customer, category2["id"])

    results = list_complaints(
        manager,
        {"category_id": category1["id"]},
    )

def test_filter_complaints_by_customer():
    manager = register_user("SUPPORT_MANAGER")
    customer1 = register_user()
    profile1 = create_customer_profile(customer1, manager)
    customer2 = register_user()
    create_customer_profile(customer2, manager)

    category = create_category(manager)
    expected = create_complaint(customer1, category["id"])
    create_complaint(customer2, category["id"])

    results = list_complaints(
        manager,
        {"customer_id": profile1["id"]},
    )

    assert results
    assert all(item["customer_id"] == profile1["id"] for item in results)
    assert any(item["id"] == expected["id"] for item in results)


def test_filter_complaints_by_status():
    manager = register_user("SUPPORT_MANAGER")
    customer = register_user()
    create_customer_profile(customer, manager)
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    update = client.patch(
        f"/api/v1/complaints/{complaint['id']}/status",
        headers=manager["headers"],
        json={"status": "IN_PROGRESS"},
    )
    assert update.status_code == 200, update.text

    results = list_complaints(manager, {"status": "IN_PROGRESS"})

    assert any(item["id"] == complaint["id"] for item in results)
    assert all(item["status"] == "IN_PROGRESS" for item in results)


def test_filter_complaints_by_created_date():
    from datetime import date

    manager = register_user("SUPPORT_MANAGER")
    customer = register_user()
    create_customer_profile(customer, manager)
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    today = date.today().isoformat()
    results = list_complaints(
        manager,
        {"created_from": today, "created_to": today},
    )

    assert any(item["id"] == complaint["id"] for item in results)


def test_combined_priority_and_category_filters():
    manager = register_user("SUPPORT_MANAGER")
    customer = register_user()
    create_customer_profile(customer, manager)
    category1 = create_category(manager)
    category2 = create_category(manager)

    expected = create_complaint(
        customer,
        category1["id"],
        priority="HIGH",
    )
    create_complaint(
        customer,
        category1["id"],
        priority="LOW",
    )
    create_complaint(
        customer,
        category2["id"],
        priority="HIGH",
    )

    results = list_complaints(
        manager,
        {
            "priority": "HIGH",
            "category_id": category1["id"],
        },
    )

    assert any(item["id"] == expected["id"] for item in results)
    assert all(item["priority"] == "HIGH" for item in results)
    assert all(item["category_id"] == category1["id"] for item in results)


def test_customer_cannot_filter_another_customers_complaints():
    manager = register_user("SUPPORT_MANAGER")
    customer1 = register_user()
    profile1 = create_customer_profile(customer1, manager)
    customer2 = register_user()
    create_customer_profile(customer2, manager)

    category = create_category(manager)
    create_complaint(customer1, category["id"])

    response = client.get(
        "/api/v1/complaints",
        headers=customer2["headers"],
        params={"customer_id": profile1["id"]},
    )

    assert response.status_code == 403
