
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv

load_dotenv()

os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5433/customer_feedback_complaint_test",
)

from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
from models.user import User


BASE_URL = "/api/v1"
TEST_PASSWORD = "TestPass@12345"

client = TestClient(app)


def unique_email():
    return f"reports_{uuid4().hex[:12]}@example.com"


def create_user_with_role(role: str):
    """
    Register a user through the API, then set the role directly
    in the test database.
    """
    email = unique_email()

    response = client.post(
        f"{BASE_URL}/auth/register",
        json={
            "full_name": f"Reports Test {role}",
            "email": email,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code in (200, 201), (
        f"Registration failed: {response.status_code} {response.text}"
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None, f"Registered user not found: {email}"

        user.role = role
        db.commit()
    finally:
        db.close()

    login_response = client.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": email,
            "password": TEST_PASSWORD,
        },
    )

    assert login_response.status_code == 200, (
        f"Login failed: {login_response.status_code} "
        f"{login_response.text}"
    )

    token = login_response.json()["access_token"]

    return {
        "email": email,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture(scope="module")
def admin_user():
    return create_user_with_role("ADMIN")


@pytest.fixture(scope="module")
def manager_user():
    return create_user_with_role("SUPPORT_MANAGER")


@pytest.fixture(scope="module")
def customer_user():
    return create_user_with_role("CUSTOMER")


# ---------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------

def test_dashboard_requires_authentication():
    response = client.get(f"{BASE_URL}/reports/dashboard")

    assert response.status_code == 401


def test_dashboard_admin_access(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/dashboard",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    expected_fields = [
        "total_customers",
        "total_feedback_submissions",
        "total_complaints",
        "open_complaints",
        "resolved_complaints",
        "overdue_complaints",
        "average_resolution_time_hours",
        "average_customer_rating",
    ]

    for field in expected_fields:
        assert field in data, f"Missing dashboard field: {field}"


def test_dashboard_manager_access(manager_user):
    response = client.get(
        f"{BASE_URL}/reports/dashboard",
        headers=manager_user["headers"],
    )

    assert response.status_code == 200


def test_dashboard_customer_forbidden(customer_user):
    response = client.get(
        f"{BASE_URL}/reports/dashboard",
        headers=customer_user["headers"],
    )

    assert response.status_code == 403


def test_dashboard_accepts_date_range(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/dashboard",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_dashboard_accepts_start_date_only(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/dashboard",
        params={"start_date": "2026-01-01"},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_dashboard_accepts_end_date_only(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/dashboard",
        params={"end_date": "2026-12-31"},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


# ---------------------------------------------------------
# Complaints grouped by priority
# ---------------------------------------------------------

def test_complaints_by_priority_requires_authentication():
    response = client.get(
        f"{BASE_URL}/reports/complaints-by-priority"
    )

    assert response.status_code == 401


def test_complaints_by_priority_admin_access(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints-by-priority",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_complaints_by_priority_manager_access(manager_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints-by-priority",
        headers=manager_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_by_priority_customer_forbidden(customer_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints-by-priority",
        headers=customer_user["headers"],
    )

    assert response.status_code == 403


def test_complaints_by_priority_accepts_date_range(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints-by-priority",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


# ---------------------------------------------------------
# Agent performance report
# ---------------------------------------------------------

def test_agent_performance_requires_authentication():
    response = client.get(
        f"{BASE_URL}/reports/agent-performance"
    )

    assert response.status_code == 401


def test_agent_performance_admin_access(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/agent-performance",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_agent_performance_manager_access(manager_user):
    response = client.get(
        f"{BASE_URL}/reports/agent-performance",
        headers=manager_user["headers"],
    )

    assert response.status_code == 200


def test_agent_performance_customer_forbidden(customer_user):
    response = client.get(
        f"{BASE_URL}/reports/agent-performance",
        headers=customer_user["headers"],
    )

    assert response.status_code == 403


def test_agent_performance_accepts_date_range(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/agent-performance",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


# ---------------------------------------------------------
# Paginated complaints report
# ---------------------------------------------------------

def test_complaints_report_requires_authentication():
    response = client.get(f"{BASE_URL}/reports/complaints")

    assert response.status_code == 401


def test_complaints_report_admin_access(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    assert isinstance(data["items"], list)


def test_complaints_report_manager_access(manager_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        headers=manager_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_report_customer_forbidden(customer_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        headers=customer_user["headers"],
    )

    assert response.status_code == 403


def test_complaints_report_pagination(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={
            "page": 1,
            "page_size": 5,
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["items"]) <= 5


def test_complaints_report_second_page(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={
            "page": 2,
            "page_size": 10,
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["page"] == 2


def test_complaints_report_sort_ascending(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={
            "sort_by": "created_at",
            "sort_order": "asc",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_report_sort_descending(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={
            "sort_by": "created_at",
            "sort_order": "desc",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_report_filter_by_status(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={"status": "OPEN"},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_report_filter_by_priority(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={"priority": "HIGH"},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_report_accepts_date_range(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200


def test_complaints_report_combines_filters(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={
            "status": "OPEN",
            "priority": "HIGH",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "page": 1,
            "page_size": 10,
            "sort_by": "created_at",
            "sort_order": "desc",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["page"] == 1
    assert data["page_size"] == 10


def test_complaints_report_rejects_invalid_page(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={"page": 0},
        headers=admin_user["headers"],
    )

    assert response.status_code == 422


def test_complaints_report_rejects_invalid_page_size(admin_user):
    response = client.get(
        f"{BASE_URL}/reports/complaints",
        params={"page_size": 0},
        headers=admin_user["headers"],
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# Authentication token validation
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "endpoint",
    [
        "/reports/dashboard",
        "/reports/complaints-by-priority",
        "/reports/agent-performance",
        "/reports/complaints",
    ],
)
def test_reports_reject_invalid_token(endpoint):
    response = client.get(
        f"{BASE_URL}{endpoint}",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
