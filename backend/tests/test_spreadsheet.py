from io import BytesIO

from openpyxl import Workbook
from fastapi.testclient import TestClient
import pytest

import main
from helper.models import EmailOutput
from helper.spreadsheet import read_internship_rows


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Internships"
    sheet.append(["Your specialty", "Internship subject", "Company name", "Contact email", "Country"])
    sheet.append(["BIO", "Cell analysis", "Example Lab", "contact@example.com", "Morocco"])
    sheet.append(["IT", "Software internship", "Example Tech", "invalid-email", "France"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.mark.unit
def test_reads_and_filters_internship_rows_across_sheet_columns() -> None:
    rows, skipped = read_internship_rows(_workbook_bytes(), "morocco")

    assert len(rows) == 1
    assert rows[0]["company"] == "Example Lab"
    assert rows[0]["internship_subject"] == "Cell analysis"
    assert rows[0]["recipient"] == "contact@example.com"
    assert rows[0]["specialty"] == "BIO"
    assert rows[0]["country"] == "Morocco"
    assert skipped == []


@pytest.mark.unit
def test_reports_invalid_contact_rows_instead_of_sending_them() -> None:
    rows, skipped = read_internship_rows(_workbook_bytes())

    assert len(rows) == 1
    assert len(skipped) == 1
    assert skipped[0]["row_number"] == 3
    assert skipped[0]["reason"] == "Missing or invalid contact email"


@pytest.mark.unit
def test_recognizes_current_french_workbook_headers() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([None, "Votre spécialité", "Sujet de stage", "Nom de la Société de stage",
                  "E-mail de contact pour votre encadrant/responsable de la société",
                  "Pays de l'entreprise de stage"])
    sheet.append([None, "BIO", "Cell analysis", "Example Lab", "contact@example.com", "Maroc"])
    output = BytesIO()
    workbook.save(output)

    rows, skipped = read_internship_rows(output.getvalue())

    assert len(rows) == 1
    assert rows[0]["company"] == "Example Lab"
    assert rows[0]["country"] == "Maroc"
    assert rows[0]["recipient"] == "contact@example.com"
    assert skipped == []


@pytest.mark.integration
def test_bulk_route_generates_personalized_drafts_for_filtered_rows(monkeypatch) -> None:
    generated_states = []

    def fake_invoke(state):
        generated_states.append(state)
        return {
            "email_final": EmailOutput(
                subject="Internship application",
                greeting="Hello,",
                body="I am interested in the Cell analysis internship at Example Lab.",
                signature="Best regards",
            )
        }

    monkeypatch.setattr(main, "extract_resume_text", lambda upload: "resume details")
    monkeypatch.setattr(main, "email_graph", type("Graph", (), {"invoke": staticmethod(fake_invoke)})())

    with TestClient(main.app) as client:
        response = client.post(
            "/generate-bulk-emails/from-files",
            files={
                "resume_file": ("resume.txt", b"resume details", "text/plain"),
                "spreadsheet_file": (
                    "internships.xlsx",
                    _workbook_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={"filter_text": "morocco", "sender_name": "Applicant"},
        )

    assert response.status_code == 200
    result = response.json()
    assert result["skipped"] == []
    assert len(result["drafts"]) == 1
    assert result["drafts"][0]["recipient"] == "contact@example.com"
    assert result["drafts"][0]["company"] == "Example Lab"
    assert len(generated_states) == 1
    assert generated_states[0]["sender_name"] == "Applicant"
    assert "Internship subject: Cell analysis" in generated_states[0]["company_description"]
