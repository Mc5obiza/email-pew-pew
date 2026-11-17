from typing import List, Optional, TypedDict

from pydantic import BaseModel, Field


class EmailOutput(BaseModel):
    subject: str
    greeting: str
    body: str
    signature: str


class ResumeSummary(BaseModel):
    skills: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    experiences: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)


class CompanySummary(BaseModel):
    focus: str
    technologies: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    tone: str = Field(
        default="formal",
        description="startup, corporate, ai, data, or formal if unclear",
    )


class MatchSummary(BaseModel):
    relevant_skills: List[str] = Field(default_factory=list)
    relevant_projects: List[str] = Field(default_factory=list)
    rationale: str


class GenerateEmailRequest(BaseModel):
    resume_text: str
    company_description: str
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None


class GraphState(TypedDict):
    resume_text: str
    company_description: str
    sender_name: Optional[str]
    sender_email: Optional[str]
    resume_summary: Optional[ResumeSummary]
    company_summary: Optional[CompanySummary]
    match_summary: Optional[MatchSummary]
    email_draft: Optional[EmailOutput]
    email_final: Optional[EmailOutput]
