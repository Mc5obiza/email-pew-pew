from typing import Any, Dict

from fastapi import HTTPException
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from .llm import get_llm
from .models import CompanySummary, EmailOutput, GraphState, MatchSummary, ResumeSummary
from .prompts import SYSTEM_PROMPT
from .utils import word_count


def build_email_graph() -> Any:
    llm = get_llm()

    resume_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert resume analyst. Extract only relevant skills, projects, "
                "experiences, and highlights for an internship application.",
            ),
            ("human", "Resume text:\n{resume_text}"),
        ]
    )
    resume_chain = resume_prompt | llm.with_structured_output(ResumeSummary)

    company_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You analyze company or internship descriptions. Identify focus, tech, "
                "requirements, and tone (startup, corporate, ai, data, formal).",
            ),
            ("human", "Company description:\n{company_description}"),
        ]
    )
    company_chain = company_prompt | llm.with_structured_output(CompanySummary)

    match_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Match resume strengths to company needs. Provide concise rationale.",
            ),
            (
                "human",
                "Resume summary: {resume_summary}\n\nCompany summary: {company_summary}",
            ),
        ]
    )
    match_chain = match_prompt | llm.with_structured_output(MatchSummary)

    draft_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "Resume summary: {resume_summary}\n"
                "Company summary: {company_summary}\n"
                "Match summary: {match_summary}\n"
                "Sender name: {sender_name}\n"
                "Sender email: {sender_email}\n"
                "Write the email.",
            ),
        ]
    )
    draft_chain = draft_prompt | llm.with_structured_output(EmailOutput)

    tone_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Adjust the email tone to match the company type. Ensure it is at least "
                "300 words, avoids robotic phrasing, and does not include the full resume text, "
                "and uses \\n for line breaks inside JSON values. Return the same JSON structure.",
            ),
            ("human", "Company tone: {tone}\n\nEmail draft: {email_draft}"),
        ]
    )
    tone_chain = tone_prompt | llm.with_structured_output(EmailOutput)

    validate_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Validate and fix the email if needed. Ensure it is at least 300 words, "
                "do not include the full resume text, avoid banned phrases, and stay professional. "
                "Use \\n for line breaks inside JSON values. Return the same JSON structure.",
            ),
            ("human", "Email draft: {email_draft}"),
        ]
    )
    validate_chain = validate_prompt | llm.with_structured_output(EmailOutput)

    def parse_resume(state: GraphState) -> Dict[str, Any]:
        result = resume_chain.invoke({"resume_text": state["resume_text"]})
        return {"resume_summary": result}

    def analyze_company(state: GraphState) -> Dict[str, Any]:
        result = company_chain.invoke(
            {"company_description": state["company_description"]}
        )
        return {"company_summary": result}

    def match_relevance(state: GraphState) -> Dict[str, Any]:
        result = match_chain.invoke(
            {
                "resume_summary": state["resume_summary"],
                "company_summary": state["company_summary"],
            }
        )
        return {"match_summary": result}

    def draft_email(state: GraphState) -> Dict[str, Any]:
        result = draft_chain.invoke(
            {
                "resume_summary": state["resume_summary"],
                "company_summary": state["company_summary"],
                "match_summary": state["match_summary"],
                "sender_name": state.get("sender_name") or "",
                "sender_email": state.get("sender_email") or "",
            }
        )
        return {"email_draft": result}

    def optimize_tone(state: GraphState) -> Dict[str, Any]:
        fallback_company = CompanySummary(
            focus="",
            technologies=[],
            requirements=[],
        )
        tone = (state.get("company_summary") or fallback_company).tone
        result = tone_chain.invoke({"tone": tone, "email_draft": state["email_draft"]})
        return {"email_draft": result}

    def finalize_email(state: GraphState) -> Dict[str, Any]:
        email = state.get("email_draft")
        if email is None:
            raise HTTPException(status_code=500, detail="Email draft missing.")

        banned_phrases = [
            "I am writing this email to",
            "Please find attached",
            "I would like to express my interest",
        ]
        needs_fix = any(phrase.lower() in email.body.lower() for phrase in banned_phrases)
        needs_fix = needs_fix or word_count(email.body) < 300

        if needs_fix:
            email = validate_chain.invoke({"email_draft": email})

        resume_text = (state.get("resume_text") or "").strip()
        if resume_text and resume_text in email.body:
            email.body = email.body.replace(resume_text, "").strip()

        return {"email_final": email}

    graph = StateGraph(GraphState)
    graph.add_node("parse_resume", parse_resume)
    graph.add_node("analyze_company", analyze_company)
    graph.add_node("match_relevance", match_relevance)
    graph.add_node("draft_email", draft_email)
    graph.add_node("optimize_tone", optimize_tone)
    graph.add_node("finalize_email", finalize_email)

    graph.set_entry_point("parse_resume")
    graph.add_edge("parse_resume", "analyze_company")
    graph.add_edge("analyze_company", "match_relevance")
    graph.add_edge("match_relevance", "draft_email")
    graph.add_edge("draft_email", "optimize_tone")
    graph.add_edge("optimize_tone", "finalize_email")
    graph.add_edge("finalize_email", END)

    return graph.compile()
