import os
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
    return f"complaint_{uuid4().hex[:10]}@example.com"


def register_user(role="CUSTOMER"):
    email = unique_email()
    password = "TestPassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": f"Test {role.title()}",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code in (200, 201), response.text

    token_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert token_response.status_code == 200, token_response.text

    token = token_response.json()["access_token"]

    if role != "CUSTOMER":
        user_id = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["id"]

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET role = :role, is_active = TRUE "
                    "WHERE id = :user_id"
                ),
                {"role": role, "user_id": user_id},
            )

        token_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert token_response.status_code == 200, token_response.text
        token = token_response.json()["access_token"]

    return {
        "email": email,
        "password": password,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }

def create_customer_profile(user):
    manager = register_user("SUPPORT_MANAGER")

    response = client.post(
        "/api/v1/customers",
        headers=manager["headers"],
        json={
            "full_name": "Complaint Test Customer",
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
            "name": f"Complaint Category {uuid4().hex[:8]}",
            "description": "Category for complaint tests",
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def complaint_payload(category_id):
    return {
        "category_id": category_id,
        "title": "Unable to access my account",
        "description": "I cannot log in to my account after resetting my password.",
        "priority": "HIGH",
        "severity": "MEDIUM",
        "attachment_urls": [],
    }


def create_complaint(customer, category_id):
    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=complaint_payload(category_id),
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_create_complaint_success():
    customer = register_user()
    create_customer_profile(customer)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=complaint_payload(category["id"]),
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["title"] == "Unable to access my account"
    assert data["priority"] == "HIGH"
    assert data["severity"] == "MEDIUM"
    assert data["status"] == "OPEN"
    assert data["customer_id"] is not None
    assert data["reference_number"]


def test_create_complaint_requires_authentication():
    response = client.post(
        "/api/v1/complaints",
        json=complaint_payload(1),
    )
    assert response.status_code == 401


def test_create_complaint_requires_customer_profile():
    customer = register_user()
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=complaint_payload(category["id"]),
    )
    assert response.status_code == 404


def test_create_complaint_rejects_invalid_category():
    customer = register_user()
    create_customer_profile(customer)

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=complaint_payload(999999),
    )
    assert response.status_code in (400, 404)


def test_create_complaint_rejects_missing_title():
    customer = register_user()
    create_customer_profile(customer)
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)

    payload = complaint_payload(category["id"])
    payload.pop("title")

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=payload,
    )
    assert response.status_code == 422


def test_create_complaint_rejects_invalid_priority():
    customer = register_user()
    create_customer_profile(customer)
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)

    payload = complaint_payload(category["id"])
    payload["priority"] = "URGENT_NOW"

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=payload,
    )
    assert response.status_code == 422


def test_create_complaint_rejects_invalid_severity():
    customer = register_user()
    create_customer_profile(customer)
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)

    payload = complaint_payload(category["id"])
    payload["severity"] = "EXTREME"

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json=payload,
    )
    assert response.status_code == 422


def test_customer_can_list_own_complaints():
    customer = register_user()
    create_customer_profile(customer)
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    create_complaint(customer, category["id"])

    response = client.get(
        "/api/v1/complaints",
        headers=customer["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert len(items) >= 1
    assert all(item["customer_id"] for item in items)


def test_customer_can_get_own_complaint():
    customer = register_user()
    create_customer_profile(customer)
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    response = client.get(
        f"/api/v1/complaints/{complaint['id']}",
        headers=customer["headers"],
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == complaint["id"]


def test_customer_cannot_get_another_customers_complaint():
    customer1 = register_user()
    create_customer_profile(customer1)

    customer2 = register_user()
    create_customer_profile(customer2)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(customer1, category["id"])

    response = client.get(
        f"/api/v1/complaints/{complaint['id']}",
        headers=customer2["headers"],
    )

    assert response.status_code == 403


def test_get_nonexistent_complaint_returns_404():
    manager = register_user("SUPPORT_MANAGER")

    response = client.get(
        "/api/v1/complaints/999999",
        headers=manager["headers"],
    )
    assert response.status_code == 404


def test_support_manager_can_list_complaints():
    manager = register_user("SUPPORT_MANAGER")

    response = client.get(
        "/api/v1/complaints",
        headers=manager["headers"],
    )

    assert response.status_code == 200, response.text


def test_customer_cannot_update_complaint_status():
    customer = register_user()
    create_customer_profile(customer)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}/status",
        headers=customer["headers"],
        json={"status": "RESOLVED"},
    )

    assert response.status_code == 403


def test_support_manager_can_update_complaint_status():
    customer = register_user()
    create_customer_profile(customer)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}/status",
        headers=manager["headers"],
        json={"status": "IN_PROGRESS"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"


def test_update_complaint_rejects_invalid_status():
    customer = register_user()
    create_customer_profile(customer)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}/status",
        headers=manager["headers"],
        json={"status": "INVALID_STATUS"},
    )

    assert response.status_code == 422


def test_complaint_reference_numbers_are_unique():
    customer = register_user()
    create_customer_profile(customer)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)

    first = create_complaint(customer, category["id"])
    second = create_complaint(customer, category["id"])

    assert first["reference_number"] != second["reference_number"]


def test_complaint_response_contains_expected_fields():
    customer = register_user()
    create_customer_profile(customer)

    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(customer, category["id"])

    response = client.get(
        f"/api/v1/complaints/{complaint['id']}",
        headers=customer["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()

    expected_fields = {
        "id",
        "reference_number",
        "customer_id",
        "category_id",
        "title",
        "description",
        "priority",
        "severity",
        "status",
        "created_at",
        "updated_at",
    }
    assert expected_fields.issubset(data.keys())
