
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

PASSWORD = "TestPassword123!"
API = "/api/v1"


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def register_user(role="CUSTOMER"):
    """Register a user and return their credentials and token."""
    unique = uuid4().hex[:12]
    email = f"{role.lower()}_{unique}@example.com"

    response = client.post(
        f"{API}/auth/register",
        json={
            "full_name": f"Test {role.title()} {unique}",
            "email": email,
            "password": PASSWORD,
        },
    )

    assert response.status_code in (200, 201), response.text

    # Look up the user and apply the requested role.
    with engine.begin() as connection:
        user_id = connection.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).scalar_one()

        connection.execute(
            text(
                """
                UPDATE users
                SET role = :role, is_active = TRUE
                WHERE id = :user_id
                """
            ),
            {"role": role, "user_id": user_id},
        )

    # Log in after setting the role.
    login_response = client.post(
        f"{API}/auth/login",
        json={"email": email, "password": PASSWORD},
    )

    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    return {
        "id": user_id,
        "email": email,
        "password": PASSWORD,
        "role": role,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def create_customer_profile(customer, manager):
    response = client.post(
        f"{API}/customers",
        json={
            "full_name": f"Customer {customer['id']}",
            "email": customer["email"],
        },
        headers=manager["headers"],
    )

    assert response.status_code in (200, 201), response.text
    return response.json()


def create_category(manager):
    unique = uuid4().hex[:10]

    response = client.post(
        f"{API}/categories",
        json={
            "name": f"Workflow Category {unique}",
            "description": "Category for resolution workflow tests",
        },
        headers=manager["headers"],
    )

    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def create_complaint(manager, customer, category_id):
    response = client.post(
        f"{API}/complaints",
        json={
            "category_id": category_id,
            "title": f"Workflow complaint {uuid4().hex[:8]}",
            "description": "Testing complaint resolution workflow",
            "priority": "HIGH",
            "severity": "MEDIUM",
            "attachment_urls": [],
        },
        headers=customer["headers"],
    )

    assert response.status_code == 201, response.text
    return response.json()


def setup_case():
    """Create a manager, customer, category, and complaint."""
    manager = register_user("SUPPORT_MANAGER")
    customer = register_user("CUSTOMER")
    agent = register_user("SUPPORT_AGENT")

    create_customer_profile(customer, manager)
    category_id = create_category(manager)
    complaint = create_complaint(manager, customer, category_id)

    return {
        "manager": manager,
        "customer": customer,
        "agent": agent,
        "category_id": category_id,
        "complaint": complaint,
        "complaint_id": complaint["id"],
    }


def change_status(case, status, **extra):
    """Use the existing manager-only status endpoint."""
    return client.patch(
        f"{API}/complaints/{case['complaint_id']}/status",
        json={"status": status, **extra},
        headers=case["manager"]["headers"],
    )


def move_to_in_progress(case):
    response = change_status(case, "IN_PROGRESS")
    assert response.status_code == 200, response.text
    return response


def resolve_case(case):
    move_to_in_progress(case)

    return client.post(
        f"{API}/complaints/{case['complaint_id']}/resolve",
        json={
            "resolution_details": (
                "Corrected the issue and verified the fix successfully."
            ),
            "reason": "Automated workflow test",
        },
        headers=case["manager"]["headers"],
    )


# ---------------------------------------------------------
# CUSTOMER-VISIBLE COMMENTS
# ---------------------------------------------------------

def test_customer_can_add_comment():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/comments",
        json={"content": "Please provide an update on my complaint."},
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 201, response.text
    assert response.json()["content"] == (
        "Please provide an update on my complaint."
    )
    assert response.json()["is_internal"] is False


def test_staff_can_add_customer_visible_comment():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/comments",
        json={"content": "Our team is investigating this issue."},
        headers=case["agent"]["headers"],
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_internal"] is False


def test_comment_rejects_empty_content():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/comments",
        json={"content": "   "},
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 422, response.text


def test_customer_cannot_comment_on_another_customers_complaint():
    case = setup_case()
    another_customer = register_user("CUSTOMER")

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/comments",
        json={"content": "This is not my complaint."},
        headers=another_customer["headers"],
    )

    assert response.status_code == 403, response.text


# ---------------------------------------------------------
# INTERNAL NOTES
# ---------------------------------------------------------

def test_staff_can_add_internal_note():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/notes",
        json={"content": "Internal investigation notes for support staff."},
        headers=case["agent"]["headers"],
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_internal"] is True


def test_customer_cannot_add_internal_note():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/notes",
        json={"content": "Customer must not create internal notes."},
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 403, response.text


def test_customer_sees_only_customer_visible_comments():
    case = setup_case()
    complaint_id = case["complaint_id"]

    public_response = client.post(
        f"{API}/complaints/{complaint_id}/comments",
        json={"content": "This is a public update."},
        headers=case["manager"]["headers"],
    )
    assert public_response.status_code == 201, public_response.text

    internal_response = client.post(
        f"{API}/complaints/{complaint_id}/notes",
        json={"content": "This is an internal investigation note."},
        headers=case["manager"]["headers"],
    )
    assert internal_response.status_code == 201, internal_response.text

    response = client.get(
        f"{API}/complaints/{complaint_id}/comments",
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 200, response.text

    # Support either a direct list or a {"items": [...]} response.
    body = response.json()
    comments = body if isinstance(body, list) else body["items"]

    assert all(item["is_internal"] is False for item in comments)
    assert any(
        item["content"] == "This is a public update."
        for item in comments
    )


def test_staff_can_see_internal_notes():
    case = setup_case()
    complaint_id = case["complaint_id"]

    note_response = client.post(
        f"{API}/complaints/{complaint_id}/notes",
        json={"content": "Staff-only investigation details."},
        headers=case["manager"]["headers"],
    )
    assert note_response.status_code == 201, note_response.text

    response = client.get(
        f"{API}/complaints/{complaint_id}/comments",
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 200, response.text

    body = response.json()
    comments = body if isinstance(body, list) else body["items"]

    assert any(
        item["is_internal"] is True
        and item["content"] == "Staff-only investigation details."
        for item in comments
    )


# ---------------------------------------------------------
# RESOLUTION WORKFLOW
# ---------------------------------------------------------

def test_cannot_resolve_without_resolution_details():
    case = setup_case()
    move_to_in_progress(case)

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/resolve",
        json={"resolution_details": "   "},
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 422, response.text


def test_cannot_resolve_complaint_directly_from_open():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/resolve",
        json={
            "resolution_details": "Fixed the issue and verified the result."
        },
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 409, response.text


def test_manager_can_resolve_in_progress_complaint():
    case = setup_case()

    response = resolve_case(case)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["resolution_details"] == (
        "Corrected the issue and verified the fix successfully."
    )
    assert body["resolved_at"] is not None


def test_cannot_close_open_complaint():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/close",
        json={"reason": "Attempting to close before resolution"},
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 409, response.text


def test_manager_can_close_resolved_complaint():
    case = setup_case()

    resolve_response = resolve_case(case)
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/close",
        json={"reason": "Resolution verified by support."},
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CLOSED"
    assert response.json()["closed_at"] is not None


def test_manager_can_reopen_resolved_complaint():
    case = setup_case()

    resolve_response = resolve_case(case)
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/reopen",
        json={"reason": "The customer reports that the issue returned."},
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REOPENED"


def test_cannot_reopen_open_complaint():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/reopen",
        json={"reason": "Invalid reopening attempt"},
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 409, response.text


def test_status_endpoint_rejects_invalid_transition():
    case = setup_case()

    response = change_status(case, "CLOSED")

    assert response.status_code == 409, response.text


# ---------------------------------------------------------
# STATUS HISTORY
# ---------------------------------------------------------

def test_status_history_records_transitions():
    case = setup_case()

    progress_response = change_status(case, "IN_PROGRESS")
    assert progress_response.status_code == 200, progress_response.text

    resolve_response = client.post(
        f"{API}/complaints/{case['complaint_id']}/resolve",
        json={
            "resolution_details": "Corrected the issue and confirmed recovery."
        },
        headers=case["manager"]["headers"],
    )
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.get(
        f"{API}/complaints/{case['complaint_id']}/status-history",
        headers=case["manager"]["headers"],
    )

    assert response.status_code == 200, response.text

    body = response.json()
    history = body if isinstance(body, list) else body["items"]

    assert any(
        item["previous_status"] == "OPEN"
        and item["new_status"] == "IN_PROGRESS"
        for item in history
    )
    assert any(
        item["previous_status"] == "IN_PROGRESS"
        and item["new_status"] == "RESOLVED"
        for item in history
    )


# ---------------------------------------------------------
# AUTHENTICATION AND AUTHORIZATION
# ---------------------------------------------------------

def test_comments_endpoint_requires_authentication():
    case = setup_case()

    response = client.get(
        f"{API}/complaints/{case['complaint_id']}/comments"
    )

    assert response.status_code == 401, response.text


def test_customer_cannot_resolve_complaint():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/resolve",
        json={
            "resolution_details": "Customer must not resolve the complaint."
        },
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 403, response.text


def test_customer_cannot_close_complaint():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/close",
        json={"reason": "Customer cannot perform staff closure."},
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 403, response.text


def test_customer_cannot_reopen_complaint():
    case = setup_case()

    response = client.post(
        f"{API}/complaints/{case['complaint_id']}/reopen",
        json={"reason": "Customer cannot use the staff reopen endpoint."},
        headers=case["customer"]["headers"],
    )

    assert response.status_code == 403, response.text
