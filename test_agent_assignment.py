
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

ASSIGNMENT_URL = "/api/v1/agent-assignments"


def unique_email():
    return f"assignment_{uuid4().hex[:12]}@example.com"


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

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200, me_response.text
    user_id = me_response.json()["id"]

    if role != "CUSTOMER":
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET role = :role, is_active = TRUE "
                    "WHERE id = :user_id"
                ),
                {"role": role, "user_id": user_id},
            )

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == 200, login_response.text
        token = login_response.json()["access_token"]

    return {
        "id": user_id,
        "email": email,
        "password": password,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def set_user_active(user_id, is_active):
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET is_active = :is_active "
                "WHERE id = :user_id"
            ),
            {"is_active": is_active, "user_id": user_id},
        )


def create_customer_profile(customer):
    manager = register_user("SUPPORT_MANAGER")

    response = client.post(
        "/api/v1/customers",
        headers=manager["headers"],
        json={
            "full_name": "Assignment Test Customer",
            "email": customer["email"],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_category(manager):
    response = client.post(
        "/api/v1/categories",
        headers=manager["headers"],
        json={
            "name": f"Assignment Category {uuid4().hex[:8]}",
            "description": "Category for assignment tests",
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_complaint(manager, category_id):
    customer = register_user()
    create_customer_profile(customer)

    response = client.post(
        "/api/v1/complaints",
        headers=customer["headers"],
        json={
            "category_id": category_id,
            "title": f"Assignment complaint {uuid4().hex[:8]}",
            "description": "Testing complaint assignment and tracking.",
            "priority": "HIGH",
            "severity": "MEDIUM",
            "attachment_urls": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def setup_assignment_data():
    manager = register_user("SUPPORT_MANAGER")
    agent = register_user("SUPPORT_AGENT")
    category = create_category(manager)
    complaint = create_complaint(manager, category["id"])

    return manager, agent, category, complaint


def assign(manager, complaint_id, agent_id, note=None):
    return client.post(
        f"{ASSIGNMENT_URL}/complaints/{complaint_id}/assign",
        headers=manager["headers"],
        json={"agent_id": agent_id, "note": note},
    )


def test_manager_can_list_support_agents():
    manager = register_user("SUPPORT_MANAGER")
    agent = register_user("SUPPORT_AGENT")

    response = client.get(
        f"{ASSIGNMENT_URL}/agents",
        headers=manager["headers"],
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)
    assert any(item["id"] == agent["id"] for item in response.json())


def test_agent_list_requires_authentication():
    response = client.get(f"{ASSIGNMENT_URL}/agents")
    assert response.status_code == 401


def test_customer_cannot_list_support_agents():
    customer = register_user()

    response = client.get(
        f"{ASSIGNMENT_URL}/agents",
        headers=customer["headers"],
    )

    assert response.status_code == 403


def test_manager_can_assign_complaint_to_agent():
    manager, agent, _, complaint = setup_assignment_data()

    response = assign(
        manager,
        complaint["id"],
        agent["id"],
        "Initial assignment",
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == complaint["id"]
    assert data["assigned_to"] == agent["id"]
    assert data["assigned_at"] is not None
    assert data["status"] == "ASSIGNED"


def test_assignment_creates_history():
    manager, agent, _, complaint = setup_assignment_data()

    response = assign(
        manager,
        complaint["id"],
        agent["id"],
        "Please investigate",
    )
    assert response.status_code == 200, response.text

    history_response = client.get(
        f"{ASSIGNMENT_URL}/complaints/{complaint['id']}/history",
        headers=manager["headers"],
    )

    assert history_response.status_code == 200, history_response.text
    history = history_response.json()

    assert len(history) == 1
    assert history[0]["complaint_id"] == complaint["id"]
    assert history[0]["previous_agent_id"] is None
    assert history[0]["new_agent_id"] == agent["id"]
    assert history[0]["assigned_by"] == manager["id"]
    assert history[0]["action"] == "ASSIGNED"
    assert history[0]["note"] == "Please investigate"


def test_manager_can_reassign_complaint():
    manager, first_agent, _, complaint = setup_assignment_data()
    second_agent = register_user("SUPPORT_AGENT")

    first_response = assign(manager, complaint["id"], first_agent["id"])
    assert first_response.status_code == 200, first_response.text

    second_response = assign(
        manager,
        complaint["id"],
        second_agent["id"],
        "Reassigned for workload balancing",
    )

    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["assigned_to"] == second_agent["id"]

    history_response = client.get(
        f"{ASSIGNMENT_URL}/complaints/{complaint['id']}/history",
        headers=manager["headers"],
    )
    assert history_response.status_code == 200, history_response.text

    history = history_response.json()
    assert len(history) == 2
    assert history[0]["action"] == "REASSIGNED"
    assert history[0]["previous_agent_id"] == first_agent["id"]
    assert history[0]["new_agent_id"] == second_agent["id"]


def test_cannot_assign_same_agent_twice():
    manager, agent, _, complaint = setup_assignment_data()

    first_response = assign(manager, complaint["id"], agent["id"])
    assert first_response.status_code == 200, first_response.text

    second_response = assign(manager, complaint["id"], agent["id"])
    assert second_response.status_code == 409, second_response.text


def test_assignment_rejects_nonexistent_agent():
    manager, _, _, complaint = setup_assignment_data()

    response = assign(manager, complaint["id"], 999999)

    assert response.status_code == 404, response.text


def test_assignment_rejects_inactive_agent():
    manager, agent, _, complaint = setup_assignment_data()
    set_user_active(agent["id"], False)

    response = assign(manager, complaint["id"], agent["id"])

    assert response.status_code == 409, response.text


def test_assignment_rejects_non_agent_user():
    manager, _, _, complaint = setup_assignment_data()
    customer = register_user("CUSTOMER")

    response = assign(manager, complaint["id"], customer["id"])

    assert response.status_code == 404, response.text


def test_assignment_rejects_nonexistent_complaint():
    manager = register_user("SUPPORT_MANAGER")
    agent = register_user("SUPPORT_AGENT")

    response = assign(manager, 999999, agent["id"])

    assert response.status_code == 404, response.text


def test_customer_cannot_assign_complaint():
    customer = register_user()
    manager = register_user("SUPPORT_MANAGER")
    category = create_category(manager)
    complaint = create_complaint(manager, category["id"])
    agent = register_user("SUPPORT_AGENT")

    response = assign(customer, complaint["id"], agent["id"])

    assert response.status_code == 403, response.text


def test_assignment_requires_authentication():
    response = client.post(
        f"{ASSIGNMENT_URL}/complaints/1/assign",
        json={"agent_id": 1},
    )

    assert response.status_code == 401


def test_manager_can_view_agent_workload():
    manager, agent, _, complaint = setup_assignment_data()

    assignment_response = assign(manager, complaint["id"], agent["id"])
    assert assignment_response.status_code == 200, assignment_response.text

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{agent['id']}/workload",
        headers=manager["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["agent_id"] == agent["id"]
    assert data["agent_email"] == agent["email"]
    assert data["total_assigned"] == 1
    assert data["active_complaints"] == 1
    assert data["resolved_complaints"] == 0


def test_workload_returns_zero_for_agent_without_complaints():
    manager = register_user("SUPPORT_MANAGER")
    agent = register_user("SUPPORT_AGENT")

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{agent['id']}/workload",
        headers=manager["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_assigned"] == 0
    assert data["active_complaints"] == 0
    assert data["resolved_complaints"] == 0


def test_workload_returns_404_for_unknown_agent():
    manager = register_user("SUPPORT_MANAGER")

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/999999/workload",
        headers=manager["headers"],
    )

    assert response.status_code == 404, response.text


def test_customer_cannot_view_agent_workload():
    customer = register_user()
    agent = register_user("SUPPORT_AGENT")

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{agent['id']}/workload",
        headers=customer["headers"],
    )

    assert response.status_code == 403


def test_agent_can_view_own_assigned_complaints():
    manager, agent, _, complaint = setup_assignment_data()

    assignment_response = assign(manager, complaint["id"], agent["id"])
    assert assignment_response.status_code == 200, assignment_response.text

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{agent['id']}/complaints",
        headers=agent["headers"],
    )

    assert response.status_code == 200, response.text
    assert any(
        item["id"] == complaint["id"]
        for item in response.json()
    )


def test_agent_cannot_view_another_agents_complaints():
    manager, first_agent, _, complaint = setup_assignment_data()
    second_agent = register_user("SUPPORT_AGENT")

    assignment_response = assign(
        manager, complaint["id"], first_agent["id"]
    )
    assert assignment_response.status_code == 200, assignment_response.text

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{first_agent['id']}/complaints",
        headers=second_agent["headers"],
    )

    assert response.status_code == 403


def test_manager_can_view_agent_assigned_complaints():
    manager, agent, _, complaint = setup_assignment_data()

    assignment_response = assign(manager, complaint["id"], agent["id"])
    assert assignment_response.status_code == 200, assignment_response.text

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{agent['id']}/complaints",
        headers=manager["headers"],
    )

    assert response.status_code == 200, response.text
    assert any(item["id"] == complaint["id"] for item in response.json())


def test_assigned_complaints_support_pagination():
    manager, agent, category, first_complaint = setup_assignment_data()
    second_complaint = create_complaint(manager, category["id"])

    for complaint in (first_complaint, second_complaint):
        result = assign(manager, complaint["id"], agent["id"])
        assert result.status_code == 200, result.text

    response = client.get(
        f"{ASSIGNMENT_URL}/agents/{agent['id']}/complaints",
        headers=manager["headers"],
        params={"page": 1, "page_size": 1},
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


def test_history_requires_manager_role():
    manager, agent, _, complaint = setup_assignment_data()
    result = assign(manager, complaint["id"], agent["id"])
    assert result.status_code == 200, result.text

    customer = register_user()

    response = client.get(
        f"{ASSIGNMENT_URL}/complaints/{complaint['id']}/history",
        headers=customer["headers"],
    )

    assert response.status_code == 403


def test_history_requires_authentication():
    response = client.get(
        f"{ASSIGNMENT_URL}/complaints/1/history"
    )

    assert response.status_code == 401


def test_history_returns_404_for_unknown_complaint():
    manager = register_user("SUPPORT_MANAGER")

    response = client.get(
        f"{ASSIGNMENT_URL}/complaints/999999/history",
        headers=manager["headers"],
    )

    assert response.status_code == 404, response.text


def test_assignment_note_is_optional():
    manager, agent, _, complaint = setup_assignment_data()

    response = assign(manager, complaint["id"], agent["id"])

    assert response.status_code == 200, response.text
    assert response.json()["assigned_to"] == agent["id"]


def test_assignment_rejects_invalid_payload():
    manager, _, _, complaint = setup_assignment_data()

    response = client.post(
        f"{ASSIGNMENT_URL}/complaints/{complaint['id']}/assign",
        headers=manager["headers"],
        json={"agent_id": 0},
    )

    assert response.status_code == 422


def test_assignment_rejects_overlong_note():
    manager, agent, _, complaint = setup_assignment_data()

    response = client.post(
        f"{ASSIGNMENT_URL}/complaints/{complaint['id']}/assign",
        headers=manager["headers"],
        json={
            "agent_id": agent["id"],
            "note": "x" * 1001,
        },
    )

    assert response.status_code == 422
