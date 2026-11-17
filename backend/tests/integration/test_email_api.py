import pytest
from fastapi.testclient import TestClient

import main
from helper.models import EmailOutput


pytestmark = pytest.mark.integration


class FakeEmailGraph:
    def __init__(self) -> None:
        self.states = []
        self.email = EmailOutput(
            subject="Internship application",
            greeting="Hello,",
            body="I am interested in the internship.",
            signature="Best regards",
        )

    def invoke(self, state):
        self.states.append(state)
        return {"email_final": self.email}


def test_generate_email_route_uses_graph_and_returns_structured_email(monkeypatch) -> None:
    graph = FakeEmailGraph()
    monkeypatch.setattr(main, "email_graph", graph)

    with TestClient(main.app) as client:
        response = client.post(
            "/generate-email",
            json={
                "resume_text": "Python developer",
                "company_description": "An AI research company",
                "sender_name": "Applicant",
                "sender_email": "applicant@example.com",
            },
        )

    assert response.status_code == 200
    assert response.json() == graph.email.model_dump()
    assert graph.states[0]["resume_text"] == "Python developer"
    assert graph.states[0]["sender_name"] == "Applicant"


def test_generate_email_route_rejects_missing_required_fields(monkeypatch) -> None:
    graph = FakeEmailGraph()
    monkeypatch.setattr(main, "email_graph", graph)

    with TestClient(main.app) as client:
        response = client.post("/generate-email", json={"resume_text": "Python"})

    assert response.status_code == 422
    assert graph.states == []


def test_health_route_reports_application_status() -> None:
    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
