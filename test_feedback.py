
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv

# Configure the test database before importing the application.
load_dotenv()

os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5433/"
    "customer_feedback_complaint_test",
)

from fastapi.testclient import TestClient
from sqlalchemy import text

from database import Base, SessionLocal, engine
from main import app
from models.user import User
from utils.security import hash_password


client = TestClient(app)

AUTH_URL = "/api/v1/auth"
CUSTOMERS_URL = "/api/v1/customers"
FEEDBACK_URL = "/api/v1/feedback"
PASSWORD = "Test@12345"


# ---------------------------------------------------------
# Common helpers
# ---------------------------------------------------------
def unique_email(prefix="feedback"):
    return f"{prefix}_{uuid4().hex[:12]}@example.com"


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def create_user_and_token(role="CUSTOMER"):
    email = unique_email(role.lower())

    with SessionLocal() as db:
        user = User(
            full_name=f"Test {role.title()}",
            email=email,
            hashed_password=hash_password(PASSWORD),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()

    response = client.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text

    return response.json()["access_token"], email


def create_customer_profile(admin_token, email):
    response = client.post(
        CUSTOMERS_URL,
        headers=auth_headers(admin_token),
        json={
            "full_name": "Feedback Test Customer",
            "email": email,
            "phone": "9876543210",
            "company_name": "Test Company",
            "address": "Madhapur",
            "city": "Hyderabad",
            "country": "India",
            "notes": "Feedback integration test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_customer_with_profile(admin_token):
    token, email = create_user_and_token("CUSTOMER")
    customer = create_customer_profile(admin_token, email)
    return token, email, customer


def feedback_payload(**overrides):
    payload = {
        "category": "PRODUCT",
        "rating": 5,
        "description": "The product works well and meets my expectations.",
    }
    payload.update(overrides)
    return payload


def submit_feedback(token, **overrides):
    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(token),
        json=feedback_payload(**overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_feedback_test_context():
    admin_token, _ = create_user_and_token("ADMIN")
    customer_token, customer_email, customer = (
        create_customer_with_profile(admin_token)
    )
    feedback = submit_feedback(customer_token)

    return {
        "admin_token": admin_token,
        "customer_token": customer_token,
        "customer_email": customer_email,
        "customer": customer,
        "feedback": feedback,
    }


# ---------------------------------------------------------
# Database setup and cleanup
# ---------------------------------------------------------
def cleanup_database():
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
        )


def setup_module():
    Base.metadata.create_all(bind=engine)
    cleanup_database()


def teardown_module():
    cleanup_database()


# ---------------------------------------------------------
# 1. Submit feedback
# ---------------------------------------------------------
def test_submit_feedback_success():
    context = create_feedback_test_context()

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
        json=feedback_payload(),
    )

    assert response.status_code == 201, response.text

    data = response.json()
    assert data["id"] > 0
    assert data["customer_id"] == context["customer"]["id"]
    assert data["category"] == "PRODUCT"
    assert data["rating"] == 5
    assert data["status"] == "NEW"
    assert data["description"] == feedback_payload()["description"]


def test_submit_feedback_requires_authentication():
    response = client.post(
        FEEDBACK_URL,
        json=feedback_payload(),
    )

    assert response.status_code == 401


def test_admin_cannot_submit_customer_feedback():
    admin_token, _ = create_user_and_token("ADMIN")

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(admin_token),
        json=feedback_payload(),
    )

    assert response.status_code == 403


def test_submit_feedback_requires_customer_profile():
    customer_token, _ = create_user_and_token("CUSTOMER")

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(customer_token),
        json=feedback_payload(),
    )

    assert response.status_code == 404


# ---------------------------------------------------------
# 2. Validate ratings, categories and descriptions
# ---------------------------------------------------------
@pytest.mark.parametrize("rating", [0, -1, 6, 100])
def test_submit_feedback_rejects_invalid_rating(rating):
    context = create_feedback_test_context()

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
        json=feedback_payload(rating=rating),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_submit_feedback_accepts_valid_ratings(rating):
    context = create_feedback_test_context()

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
        json=feedback_payload(rating=rating),
    )

    assert response.status_code == 201, response.text
    assert response.json()["rating"] == rating


def test_submit_feedback_rejects_invalid_category():
    context = create_feedback_test_context()

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
        json=feedback_payload(category="INVALID_CATEGORY"),
    )

    assert response.status_code == 422


def test_submit_feedback_rejects_empty_description():
    context = create_feedback_test_context()

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
        json=feedback_payload(description="   "),
    )

    assert response.status_code == 422


def test_submit_feedback_rejects_missing_rating():
    context = create_feedback_test_context()
    payload = feedback_payload()
    payload.pop("rating")

    response = client.post(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
        json=payload,
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# 3. List and retrieve feedback
# ---------------------------------------------------------
def test_customer_can_list_own_feedback():
    context = create_feedback_test_context()

    response = client.get(
        FEEDBACK_URL,
        headers=auth_headers(context["customer_token"]),
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) >= 1
    assert all(
        item["customer_id"] == context["customer"]["id"]
        for item in response.json()
    )


def test_customer_can_list_my_feedback():
    context = create_feedback_test_context()

    response = client.get(
        f"{FEEDBACK_URL}/me",
        headers=auth_headers(context["customer_token"]),
    )

    assert response.status_code == 200, response.text
    assert any(
        item["id"] == context["feedback"]["id"]
        for item in response.json()
    )


def test_admin_can_list_all_feedback():
    context = create_feedback_test_context()

    response = client.get(
        FEEDBACK_URL,
        headers=auth_headers(context["admin_token"]),
    )

    assert response.status_code == 200, response.text
    assert any(
        item["id"] == context["feedback"]["id"]
        for item in response.json()
    )


def test_list_feedback_requires_authentication():
    response = client.get(FEEDBACK_URL)

    assert response.status_code == 401


def test_customer_can_get_own_feedback():
    context = create_feedback_test_context()
    feedback_id = context["feedback"]["id"]

    response = client.get(
        f"{FEEDBACK_URL}/{feedback_id}",
        headers=auth_headers(context["customer_token"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == feedback_id


def test_customer_cannot_get_another_customers_feedback():
    admin_token, _ = create_user_and_token("ADMIN")

    customer1_token, _, _ = create_customer_with_profile(admin_token)
    customer2_token, _, _ = create_customer_with_profile(admin_token)

    feedback = submit_feedback(customer1_token)

    response = client.get(
        f"{FEEDBACK_URL}/{feedback['id']}",
        headers=auth_headers(customer2_token),
    )

    assert response.status_code == 403


def test_get_nonexistent_feedback():
    context = create_feedback_test_context()

    response = client.get(
        f"{FEEDBACK_URL}/99999999",
        headers=auth_headers(context["admin_token"]),
    )

    assert response.status_code == 404


# ---------------------------------------------------------
# 4. Edit feedback
# ---------------------------------------------------------
def test_customer_can_edit_own_new_feedback():
    context = create_feedback_test_context()
    feedback_id = context["feedback"]["id"]

    response = client.patch(
        f"{FEEDBACK_URL}/{feedback_id}",
        headers=auth_headers(context["customer_token"]),
        json={
            "rating": 4,
            "description": "Updated feedback description.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["rating"] == 4
    assert response.json()["description"] == "Updated feedback description."


def test_customer_cannot_edit_another_customers_feedback():
    admin_token, _ = create_user_and_token("ADMIN")

    customer1_token, _, _ = create_customer_with_profile(admin_token)
    customer2_token, _, _ = create_customer_with_profile(admin_token)

    feedback = submit_feedback(customer1_token)

    response = client.patch(
        f"{FEEDBACK_URL}/{feedback['id']}",
        headers=auth_headers(customer2_token),
        json={"rating": 3},
    )

    assert response.status_code == 403


def test_edit_feedback_rejects_invalid_rating():
    context = create_feedback_test_context()

    response = client.patch(
        f"{FEEDBACK_URL}/{context['feedback']['id']}",
        headers=auth_headers(context["customer_token"]),
        json={"rating": 6},
    )

    assert response.status_code == 422


def test_edit_feedback_rejects_empty_update():
    context = create_feedback_test_context()

    response = client.patch(
        f"{FEEDBACK_URL}/{context['feedback']['id']}",
        headers=auth_headers(context["customer_token"]),
        json={},
    )

    assert response.status_code == 422


def test_edit_feedback_requires_authentication():
    context = create_feedback_test_context()

    response = client.patch(
        f"{FEEDBACK_URL}/{context['feedback']['id']}",
        json={"rating": 4},
    )

    assert response.status_code == 401


# ---------------------------------------------------------
# 5. Feedback status permissions
# ---------------------------------------------------------
def test_admin_can_update_feedback_status():
    context = create_feedback_test_context()

    response = client.patch(
        f"{FEEDBACK_URL}/{context['feedback']['id']}/status",
        headers=auth_headers(context["admin_token"]),
        json={"status": "IN_REVIEW"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_REVIEW"


def test_customer_cannot_update_feedback_status():
    context = create_feedback_test_context()

    response = client.patch(
        f"{FEEDBACK_URL}/{context['feedback']['id']}/status",
        headers=auth_headers(context["customer_token"]),
        json={"status": "IN_REVIEW"},
    )

    assert response.status_code == 403


def test_update_feedback_status_rejects_invalid_status():
    context = create_feedback_test_context()

    response = client.patch(
        f"{FEEDBACK_URL}/{context['feedback']['id']}/status",
        headers=auth_headers(context["admin_token"]),
        json={"status": "INVALID_STATUS"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# 6. Feedback history
# ---------------------------------------------------------
def test_feedback_creation_records_history():
    context = create_feedback_test_context()

    response = client.get(
        f"{FEEDBACK_URL}/{context['feedback']['id']}/history",
        headers=auth_headers(context["customer_token"]),
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) >= 1
    assert any(
        item["action"] == "CREATED"
        for item in response.json()
    )


def test_feedback_edit_records_history():
    context = create_feedback_test_context()
    feedback_id = context["feedback"]["id"]

    update_response = client.patch(
        f"{FEEDBACK_URL}/{feedback_id}",
        headers=auth_headers(context["customer_token"]),
        json={"rating": 3},
    )
    assert update_response.status_code == 200, update_response.text

    response = client.get(
        f"{FEEDBACK_URL}/{feedback_id}/history",
        headers=auth_headers(context["customer_token"]),
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) >= 2


def test_customer_cannot_view_another_customers_feedback_history():
    admin_token, _ = create_user_and_token("ADMIN")

    customer1_token, _, _ = create_customer_with_profile(admin_token)
    customer2_token, _, _ = create_customer_with_profile(admin_token)

    feedback = submit_feedback(customer1_token)

    response = client.get(
        f"{FEEDBACK_URL}/{feedback['id']}/history",
        headers=auth_headers(customer2_token),
    )

    assert response.status_code == 403


def test_feedback_history_requires_authentication():
    context = create_feedback_test_context()

    response = client.get(
        f"{FEEDBACK_URL}/{context['feedback']['id']}/history",
    )

    assert response.status_code == 401
