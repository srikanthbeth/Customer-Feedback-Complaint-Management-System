
import os
from uuid import uuid4

from dotenv import load_dotenv

# ---------------------------------------------------------
# Test database configuration (must run before app imports)
# ---------------------------------------------------------
load_dotenv()

os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5433/customer_feedback_complaint_test",
)

from fastapi.testclient import TestClient
from sqlalchemy import text

from database import Base, SessionLocal, engine
from main import app
from models.user import User
from models.customer import Customer
from utils.security import hash_password


client = TestClient(app)

AUTH_URL = "/api/v1/auth"
CUSTOMERS_URL = "/api/v1/customers"
PASSWORD = "Test@12345"


# ---------------------------------------------------------
# Common helpers
# ---------------------------------------------------------
def unique_email(prefix="customer"):
    return f"{prefix}_{uuid4().hex[:12]}@example.com"


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def customer_payload(**overrides):
    data = {
        "full_name": "Test Customer",
        "email": unique_email(),
        "phone": "9876543210",
        "company_name": "Test Company",
        "address": "Madhapur",
        "city": "Hyderabad",
        "country": "India",
        "notes": "Level 2 integration test",
    }
    data.update(overrides)
    return data


def create_user_and_token(role="CUSTOMER", is_active=True):
    """Create an account directly, then obtain a JWT using the login API."""
    email = unique_email(role.lower())

    with SessionLocal() as db:
        user = User(
            full_name=f"Test {role.title()}",
            email=email,
            hashed_password=hash_password(PASSWORD),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()

    response = client.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": PASSWORD},
    )

    assert response.status_code == 200, response.text
    return response.json()["access_token"], email


def create_customer(admin_token, **overrides):
    payload = customer_payload(**overrides)
    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(admin_token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_customer_user_with_profile(admin_token):
    """Create a CUSTOMER login and a matching customer profile."""
    token, email = create_user_and_token("CUSTOMER")

    customer = create_customer(
        admin_token,
        email=email,
        full_name="Customer Self Service",
    )

    return token, email, customer


# ---------------------------------------------------------
# Database setup and cleanup
# ---------------------------------------------------------
def cleanup_database():
    with engine.begin() as connection:
        # CASCADE handles related tables referencing customers/users.
        connection.execute(
            text("TRUNCATE TABLE customers, users RESTART IDENTITY CASCADE")
        )


def setup_module():
    # Ensure all imported models are registered before table creation.
    Base.metadata.create_all(bind=engine)
    cleanup_database()


def teardown_module():
    cleanup_database()


# ---------------------------------------------------------
# CREATE CUSTOMER
# ---------------------------------------------------------
def test_create_customer():
    token, _ = create_user_and_token("ADMIN")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(),
    )

    assert response.status_code == 201, response.text
    body = response.json()

    assert body["id"] > 0
    assert body["full_name"] == "Test Customer"
    assert body["email"].endswith("@example.com")
    assert body["city"] == "Hyderabad"
    assert body["country"] == "India"
    assert body["is_active"] is True


def test_create_customer_with_minimum_fields():
    token, _ = create_user_and_token("ADMIN")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json={
            "full_name": "Minimal Customer",
            "email": unique_email(),
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["full_name"] == "Minimal Customer"


def test_create_customer_duplicate_email():
    token, _ = create_user_and_token("ADMIN")
    email = unique_email()

    first = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(email=email),
    )
    assert first.status_code == 201, first.text

    second = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(email=email),
    )

    assert second.status_code == 409, second.text


def test_create_customer_invalid_email():
    token, _ = create_user_and_token("ADMIN")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(email="not-an-email"),
    )

    assert response.status_code == 422, response.text


def test_create_customer_missing_full_name():
    token, _ = create_user_and_token("ADMIN")
    payload = customer_payload()
    payload.pop("full_name")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=payload,
    )

    assert response.status_code == 422, response.text


def test_create_customer_short_full_name():
    token, _ = create_user_and_token("ADMIN")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(full_name="A"),
    )

    assert response.status_code == 422, response.text


def test_create_customer_requires_authentication():
    response = client.post(
        CUSTOMERS_URL,
        json=customer_payload(),
    )

    assert response.status_code in (401, 403), response.text


def test_customer_cannot_create_customer():
    token, _ = create_user_and_token("CUSTOMER")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(),
    )

    assert response.status_code == 403, response.text


def test_support_manager_can_create_customer():
    token, _ = create_user_and_token("SUPPORT_MANAGER")

    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        json=customer_payload(),
    )

    assert response.status_code == 201, response.text


# ---------------------------------------------------------
# LIST CUSTOMERS
# ---------------------------------------------------------
def test_list_customers():
    token, _ = create_user_and_token("ADMIN")
    create_customer(token)
    create_customer(token)

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["total"] >= 2
    assert len(body["items"]) >= 2


def test_list_customers_requires_authentication():
    response = client.get(CUSTOMERS_URL)

    assert response.status_code in (401, 403), response.text


def test_customer_cannot_list_all_customers():
    token, _ = create_user_and_token("CUSTOMER")

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
    )

    assert response.status_code == 403, response.text


def test_list_customers_pagination():
    token, _ = create_user_and_token("ADMIN")

    for _ in range(3):
        create_customer(token)

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"page": 1, "page_size": 2},
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) <= 2


def test_list_customers_invalid_page():
    token, _ = create_user_and_token("ADMIN")

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"page": 0},
    )

    assert response.status_code == 422, response.text


def test_list_customers_invalid_page_size():
    token, _ = create_user_and_token("ADMIN")

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"page_size": 101},
    )

    assert response.status_code == 422, response.text


def test_list_customers_filter_by_city():
    token, _ = create_user_and_token("ADMIN")
    city = f"Hyderabad-{uuid4().hex[:6]}"

    create_customer(token, city=city)

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"city": city},
    )

    assert response.status_code == 200, response.text
    assert all(item["city"] == city for item in response.json()["items"])


def test_list_customers_filter_by_country():
    token, _ = create_user_and_token("ADMIN")
    country = f"Country-{uuid4().hex[:6]}"

    create_customer(token, country=country)

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"country": country},
    )

    assert response.status_code == 200, response.text
    assert all(
        item["country"] == country for item in response.json()["items"]
    )


def test_list_customers_search():
    token, _ = create_user_and_token("ADMIN")
    unique_name = f"SearchCustomer{uuid4().hex[:8]}"

    create_customer(token, full_name=unique_name)

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"search": unique_name},
    )

    assert response.status_code == 200, response.text
    assert any(
        item["full_name"] == unique_name
        for item in response.json()["items"]
    )


def test_list_customers_sort_invalid_field():
    token, _ = create_user_and_token("ADMIN")

    response = client.get(
        CUSTOMERS_URL,
        headers=auth_headers(token),
        params={"sort_by": "password"},
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------
# GET CUSTOMER
# ---------------------------------------------------------
def test_get_customer_by_id():
    token, _ = create_user_and_token("ADMIN")
    customer = create_customer(token)

    response = client.get(
        f"{CUSTOMERS_URL}/{customer['id']}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == customer["id"]


def test_get_nonexistent_customer():
    token, _ = create_user_and_token("ADMIN")

    response = client.get(
        f"{CUSTOMERS_URL}/99999999",
        headers=auth_headers(token),
    )

    assert response.status_code == 404, response.text


def test_get_customer_requires_authentication():
    response = client.get(f"{CUSTOMERS_URL}/1")

    assert response.status_code in (401, 403), response.text


def test_customer_can_get_own_profile():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, email, customer = create_customer_user_with_profile(
        admin_token
    )

    response = client.get(
        f"{CUSTOMERS_URL}/{customer['id']}",
        headers=auth_headers(customer_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"].lower() == email.lower()


def test_customer_cannot_get_another_customers_profile():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, _, _ = create_customer_user_with_profile(admin_token)

    other_customer = create_customer(admin_token)

    response = client.get(
        f"{CUSTOMERS_URL}/{other_customer['id']}",
        headers=auth_headers(customer_token),
    )

    assert response.status_code == 403, response.text


# ---------------------------------------------------------
# UPDATE CUSTOMER
# ---------------------------------------------------------
def test_update_customer():
    token, _ = create_user_and_token("ADMIN")
    customer = create_customer(token)

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}",
        headers=auth_headers(token),
        json={
            "full_name": "Updated Customer",
            "city": "Secunderabad",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["full_name"] == "Updated Customer"
    assert body["city"] == "Secunderabad"


def test_update_customer_email():
    token, _ = create_user_and_token("ADMIN")
    customer = create_customer(token)
    new_email = unique_email("updated")

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}",
        headers=auth_headers(token),
        json={"email": new_email},
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"].lower() == new_email.lower()


def test_update_nonexistent_customer():
    token, _ = create_user_and_token("ADMIN")

    response = client.patch(
        f"{CUSTOMERS_URL}/99999999",
        headers=auth_headers(token),
        json={"full_name": "Updated Customer"},
    )

    assert response.status_code == 404, response.text


def test_customer_can_update_own_name():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, _, customer = create_customer_user_with_profile(
        admin_token
    )

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}",
        headers=auth_headers(customer_token),
        json={"full_name": "My Updated Name"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "My Updated Name"


def test_customer_cannot_change_own_email():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, _, customer = create_customer_user_with_profile(
        admin_token
    )

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}",
        headers=auth_headers(customer_token),
        json={"email": unique_email("changed")},
    )

    assert response.status_code == 403, response.text


def test_update_customer_requires_authentication():
    response = client.patch(
        f"{CUSTOMERS_URL}/1",
        json={"full_name": "Updated Name"},
    )

    assert response.status_code in (401, 403), response.text


# ---------------------------------------------------------
# CUSTOMER STATUS
# ---------------------------------------------------------
def test_admin_deactivates_customer():
    token, _ = create_user_and_token("ADMIN")
    customer = create_customer(token)

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}/status",
        headers=auth_headers(token),
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_admin_reactivates_customer():
    token, _ = create_user_and_token("ADMIN")
    customer = create_customer(token)

    deactivate = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}/status",
        headers=auth_headers(token),
        json={"is_active": False},
    )
    assert deactivate.status_code == 200, deactivate.text

    activate = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}/status",
        headers=auth_headers(token),
        json={"is_active": True},
    )

    assert activate.status_code == 200, activate.text
    assert activate.json()["is_active"] is True


def test_support_manager_cannot_change_customer_status():
    admin_token, _ = create_user_and_token("ADMIN")
    manager_token, _ = create_user_and_token("SUPPORT_MANAGER")
    customer = create_customer(admin_token)

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}/status",
        headers=auth_headers(manager_token),
        json={"is_active": False},
    )

    assert response.status_code == 403, response.text


def test_customer_cannot_change_customer_status():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, _, customer = create_customer_user_with_profile(
        admin_token
    )

    response = client.patch(
        f"{CUSTOMERS_URL}/{customer['id']}/status",
        headers=auth_headers(customer_token),
        json={"is_active": False},
    )

    assert response.status_code == 403, response.text


def test_update_status_nonexistent_customer():
    token, _ = create_user_and_token("ADMIN")

    response = client.patch(
        f"{CUSTOMERS_URL}/99999999/status",
        headers=auth_headers(token),
        json={"is_active": False},
    )

    assert response.status_code == 404, response.text


# ---------------------------------------------------------
# CUSTOMER SELF-SERVICE
# ---------------------------------------------------------
def test_get_my_customer_profile():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, email, _ = create_customer_user_with_profile(
        admin_token
    )

    response = client.get(
        f"{CUSTOMERS_URL}/me",
        headers=auth_headers(customer_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"].lower() == email.lower()


def test_get_my_profile_for_admin_is_forbidden():
    token, _ = create_user_and_token("ADMIN")

    response = client.get(
        f"{CUSTOMERS_URL}/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 403, response.text


def test_get_my_profile_without_matching_customer_record():
    token, _ = create_user_and_token("CUSTOMER")

    response = client.get(
        f"{CUSTOMERS_URL}/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 404, response.text


def test_get_my_profile_requires_authentication():
    response = client.get(f"{CUSTOMERS_URL}/me")

    assert response.status_code in (401, 403), response.text
