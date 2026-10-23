
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
    return f"category_{uuid4().hex[:10]}@example.com"


def register_user(role="ADMIN"):
    email = unique_email()
    password = "TestPassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Category Test User",
        },
    )

    assert response.status_code in (200, 201), response.text

    # Set role directly in the test database so the test can exercise
    # the required staff/customer permission levels.
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE users
                SET role = :role
                WHERE lower(email) = lower(:email)
                """
            ),
            {"role": role, "email": email},
        )

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert login.status_code == 200, login.text
    body = login.json()
    token = body.get("access_token")

    if not token and isinstance(body.get("data"), dict):
        token = body["data"].get("access_token")

    assert token, f"Access token missing from login response: {body}"

    return {"Authorization": f"Bearer {token}"}


def create_category(headers, name=None, description="Test category description"):
    name = name or f"Category {uuid4().hex[:8]}"

    return client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": name, "description": description},
    )


def test_create_category_success():
    headers = register_user("ADMIN")
    response = create_category(headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["name"].startswith("Category ")
    assert body["description"] == "Test category description"
    assert body["is_active"] is True


def test_create_category_trims_name():
    headers = register_user("ADMIN")
    name = f"  Trimmed {uuid4().hex[:8]}  "

    response = create_category(headers, name=name)

    assert response.status_code == 201, response.text
    assert response.json()["name"] == name.strip()


def test_create_category_without_description():
    headers = register_user("ADMIN")
    response = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": f"No Description {uuid4().hex[:8]}"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["description"] is None


def test_create_category_duplicate_name_returns_conflict():
    headers = register_user("ADMIN")
    name = f"Duplicate {uuid4().hex[:8]}"

    first = create_category(headers, name=name)
    assert first.status_code == 201, first.text

    second = create_category(headers, name=name)

    assert second.status_code == 409, second.text


def test_create_category_duplicate_name_case_insensitive():
    headers = register_user("ADMIN")
    name = f"CaseTest {uuid4().hex[:8]}"

    first = create_category(headers, name=name)
    assert first.status_code == 201, first.text

    second = create_category(headers, name=name.upper())

    assert second.status_code == 409, second.text


def test_create_category_rejects_short_name():
    headers = register_user("ADMIN")

    response = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "A"},
    )

    assert response.status_code == 422, response.text


def test_create_category_rejects_missing_name():
    headers = register_user("ADMIN")

    response = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"description": "Missing category name"},
    )

    assert response.status_code == 422, response.text


def test_create_category_rejects_blank_name():
    headers = register_user("ADMIN")

    response = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "   "},
    )

    assert response.status_code == 422, response.text


def test_create_category_rejects_long_name():
    headers = register_user("ADMIN")

    response = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "C" * 101},
    )

    assert response.status_code == 422, response.text


def test_list_categories():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    response = client.get("/api/v1/categories", headers=headers)

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)
    assert any(item["id"] == created.json()["id"] for item in response.json())


def test_get_category_by_id():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text
    category_id = created.json()["id"]

    response = client.get(
        f"/api/v1/categories/{category_id}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == category_id


def test_get_nonexistent_category_returns_404():
    headers = register_user("ADMIN")

    response = client.get("/api/v1/categories/99999999", headers=headers)

    assert response.status_code == 404, response.text


def test_update_category_name():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    category_id = created.json()["id"]
    new_name = f"Updated {uuid4().hex[:8]}"

    response = client.patch(
        f"/api/v1/categories/{category_id}",
        headers=headers,
        json={"name": new_name},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == new_name


def test_update_category_description():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    category_id = created.json()["id"]
    description = "Updated description"

    response = client.patch(
        f"/api/v1/categories/{category_id}",
        headers=headers,
        json={"description": description},
    )

    assert response.status_code == 200, response.text
    assert response.json()["description"] == description


def test_update_category_trims_name():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    category_id = created.json()["id"]
    new_name = f"  Updated {uuid4().hex[:8]}  "

    response = client.patch(
        f"/api/v1/categories/{category_id}",
        headers=headers,
        json={"name": new_name},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == new_name.strip()


def test_update_category_duplicate_name_returns_conflict():
    headers = register_user("ADMIN")
    first = create_category(headers)
    second = create_category(headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    response = client.patch(
        f"/api/v1/categories/{second.json()['id']}",
        headers=headers,
        json={"name": first.json()["name"]},
    )

    assert response.status_code == 409, response.text


def test_update_nonexistent_category_returns_404():
    headers = register_user("ADMIN")

    response = client.patch(
        "/api/v1/categories/99999999",
        headers=headers,
        json={"name": "Updated Category"},
    )

    assert response.status_code == 404, response.text


def test_update_category_rejects_empty_body():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    response = client.patch(
        f"/api/v1/categories/{created.json()['id']}",
        headers=headers,
        json={},
    )

    assert response.status_code == 422, response.text


def test_update_category_rejects_short_name():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    response = client.patch(
        f"/api/v1/categories/{created.json()['id']}",
        headers=headers,
        json={"name": "A"},
    )

    assert response.status_code == 422, response.text


def test_deactivate_category():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    response = client.patch(
        f"/api/v1/categories/{created.json()['id']}/status",
        headers=headers,
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_activate_category():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    category_id = created.json()["id"]

    deactivate = client.patch(
        f"/api/v1/categories/{category_id}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert deactivate.status_code == 200, deactivate.text

    activate = client.patch(
        f"/api/v1/categories/{category_id}/status",
        headers=headers,
        json={"is_active": True},
    )

    assert activate.status_code == 200, activate.text
    assert activate.json()["is_active"] is True


def test_filter_categories_by_active_status():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text
    category_id = created.json()["id"]

    changed = client.patch(
        f"/api/v1/categories/{category_id}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert changed.status_code == 200, changed.text

    response = client.get(
        "/api/v1/categories",
        headers=headers,
        params={"is_active": False},
    )

    assert response.status_code == 200, response.text
    assert all(item["is_active"] is False for item in response.json())
    assert any(item["id"] == category_id for item in response.json())


def test_filter_categories_by_name():
    headers = register_user("ADMIN")
    unique_part = uuid4().hex[:8]
    name = f"Searchable-{unique_part}"

    created = create_category(headers, name=name)
    assert created.status_code == 201, created.text

    response = client.get(
        "/api/v1/categories",
        headers=headers,
        params={"search": unique_part},
    )

    assert response.status_code == 200, response.text
    assert any(item["id"] == created.json()["id"] for item in response.json())


def test_list_categories_requires_authentication():
    response = client.get("/api/v1/categories")

    assert response.status_code == 401, response.text


def test_get_category_requires_authentication():
    response = client.get("/api/v1/categories/1")

    assert response.status_code == 401, response.text


def test_create_category_requires_authentication():
    response = client.post(
        "/api/v1/categories",
        json={"name": f"Unauthenticated {uuid4().hex[:8]}"},
    )

    assert response.status_code == 401, response.text


def test_customer_cannot_create_category():
    headers = register_user("CUSTOMER")

    response = create_category(headers)

    assert response.status_code == 403, response.text


def test_customer_cannot_update_category():
    admin_headers = register_user("ADMIN")
    created = create_category(admin_headers)
    assert created.status_code == 201, created.text

    customer_headers = register_user("CUSTOMER")
    response = client.patch(
        f"/api/v1/categories/{created.json()['id']}",
        headers=customer_headers,
        json={"name": f"Customer Edit {uuid4().hex[:8]}"},
    )

    assert response.status_code == 403, response.text


def test_customer_cannot_change_category_status():
    admin_headers = register_user("ADMIN")
    created = create_category(admin_headers)
    assert created.status_code == 201, created.text

    customer_headers = register_user("CUSTOMER")
    response = client.patch(
        f"/api/v1/categories/{created.json()['id']}/status",
        headers=customer_headers,
        json={"is_active": False},
    )

    assert response.status_code == 403, response.text


def test_support_manager_can_create_category():
    headers = register_user("SUPPORT_MANAGER")

    response = create_category(headers)

    assert response.status_code == 201, response.text


def test_customer_can_list_categories():
    admin_headers = register_user("ADMIN")
    created = create_category(admin_headers)
    assert created.status_code == 201, created.text

    customer_headers = register_user("CUSTOMER")
    response = client.get("/api/v1/categories", headers=customer_headers)

    assert response.status_code == 200, response.text
    assert any(item["id"] == created.json()["id"] for item in response.json())


def test_category_status_requires_boolean():
    headers = register_user("ADMIN")
    created = create_category(headers)
    assert created.status_code == 201, created.text

    response = client.patch(
        f"/api/v1/categories/{created.json()['id']}/status",
        headers=headers,
        json={"is_active": "not-a-boolean"},
    )

    assert response.status_code == 422, response.text
