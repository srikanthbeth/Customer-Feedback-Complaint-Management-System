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

from database import Base, SessionLocal, engine
from main import app
from models.user import User
from utils.security import hash_password, verify_password


client = TestClient(app)


def unique_email():
    return f"user_{uuid4().hex[:10]}@example.com"


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


def register_user(email=None, password="StrongPassword123!"):
    if email is None:
        email = unique_email()

    return client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test Customer",
            "email": email,
            "password": password,
        },
    )


def login_user(email, password="StrongPassword123!"):
    return client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def create_user(
    email=None,
    role="CUSTOMER",
    password="StrongPassword123!",
    is_active=True,
):
    email = email or unique_email()

    with SessionLocal() as db:
        user = User(
            full_name="Test User",
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "password": password,
        }


def create_admin():
    admin = create_user(role="ADMIN")
    response = login_user(admin["email"], admin["password"])

    assert response.status_code == 200, response.text

    return response.json()["access_token"]


def test_register_user():
    response = register_user()

    assert response.status_code == 201, response.text

    data = response.json()

    assert data["full_name"] == "Test Customer"
    assert data["email"].endswith("@example.com")
    assert data["role"] == "CUSTOMER"
    assert data["is_active"] is True
    assert "hashed_password" not in data


def test_public_registration_cannot_select_admin_role():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Attempted Admin",
            "email": unique_email(),
            "password": "StrongPassword123!",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "CUSTOMER"


def test_duplicate_email():
    email = unique_email()

    first = register_user(email)
    assert first.status_code == 201, first.text

    second = register_user(email)

    assert second.status_code == 409
    assert second.json()["success"] is False
    assert second.json()["error"]["code"] == 409
    assert second.json()["error"]["message"] == (
    "An account with this email already exists"
)


def test_password_is_hashed():
    email = unique_email()

    response = register_user(email)

    assert response.status_code == 201, response.text

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()

        assert user is not None
        assert user.hashed_password != "StrongPassword123!"
        assert verify_password(
            "StrongPassword123!",
            user.hashed_password,
        )


def test_login_success():
    email = unique_email()

    registration = register_user(email)
    assert registration.status_code == 201, registration.text

    response = login_user(email)

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_invalid_password():
    email = unique_email()

    registration = register_user(email)
    assert registration.status_code == 201, registration.text

    response = login_user(email, "WrongPassword123!")

    assert response.status_code == 401


def test_current_user():
    email = unique_email()

    registration = register_user(email)
    assert registration.status_code == 201, registration.text

    login_response = login_user(email)
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == email
    assert response.json()["role"] == "CUSTOMER"
    assert "hashed_password" not in response.json()


def test_missing_authentication():
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_invalid_access_token():
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_customer_cannot_list_users():
    customer = create_user(role="CUSTOMER")

    login_response = login_user(
        customer["email"],
        customer["password"],
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_can_list_users():
    token = create_admin()

    response = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_worker_cannot_update_user_status():
    customer = create_user(role="CUSTOMER")
    target = create_user(role="CUSTOMER")

    login_response = login_user(
        customer["email"],
        customer["password"],
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    response = client.patch(
        f"/api/v1/users/{target['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_can_deactivate_user():
    token = create_admin()
    target = create_user(role="CUSTOMER")

    response = client.patch(
        f"/api/v1/users/{target['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_inactive_user_cannot_login():
    user = create_user(
        role="CUSTOMER",
        is_active=False,
    )

    response = login_user(
        user["email"],
        user["password"],
    )

    assert response.status_code == 403


def test_inactive_user_cannot_use_old_token():
    admin_token = create_admin()
    customer = create_user(role="CUSTOMER")

    customer_login = login_user(
        customer["email"],
        customer["password"],
    )
    assert customer_login.status_code == 200, customer_login.text

    customer_token = customer_login.json()["access_token"]

    deactivation = client.patch(
        f"/api/v1/users/{customer['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert deactivation.status_code == 200, deactivation.text

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    assert response.status_code == 403
