import pytest
from langchain_core.runnables import RunnableLambda

from helper.graph import build_email_graph
from helper.models import (
    CompanySummary,
    EmailOutput,
    MatchSummary,
    ResumeSummary,
)


pytestmark = pytest.mark.unit


class FakeLLM(RunnableLambda):
    def __init__(self) -> None:
        super().__init__(lambda value: value)
        self.structured_calls = []
        self.email = EmailOutput(
            subject="Internship application",
            greeting="Hello,",
            body="Relevant experience " * 150,
            signature="Best regards",
        )

    def with_structured_output(self, schema):
        def respond(_prompt):
            self.structured_calls.append(schema)
            if schema is ResumeSummary:
                return ResumeSummary(skills=["Python"], projects=["Email platform"])
            if schema is CompanySummary:
                return CompanySummary(focus="AI", technologies=["Python"])
            if schema is MatchSummary:
                return MatchSummary(
                    relevant_skills=["Python"],
                    relevant_projects=["Email platform"],
                    rationale="The project uses the company's core technology.",
                )
            return self.email

        return RunnableLambda(respond)


def test_email_graph_runs_with_stubbed_structured_llm(monkeypatch) -> None:
    fake_llm = FakeLLM()
    monkeypatch.setattr("helper.graph.get_llm", lambda: fake_llm)
    graph = build_email_graph()

    result = graph.invoke(
        {
            "resume_text": "Python developer with an email automation project.",
            "company_description": "An AI company using Python.",
            "sender_name": "Applicant",
            "sender_email": "applicant@example.com",
            "resume_summary": None,
            "company_summary": None,
            "match_summary": None,
            "email_draft": None,
            "email_final": None,
        }
    )

    assert result["email_final"] == fake_llm.email
    assert fake_llm.structured_calls == [
        ResumeSummary,
        CompanySummary,
        MatchSummary,
        EmailOutput,
        EmailOutput,
    ]
