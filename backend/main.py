import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).with_name(".env"))
os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)

from helper.gmail import (
    SendEmailRequest,
    disconnect_gmail,
    gmail_callback,
    gmail_login,
    gmail_status,
    send_gmail,
)
from helper.graph import build_email_graph
from helper.models import EmailOutput, GenerateEmailRequest,  GraphState
from helper.resume_parser import extract_resume_text
from helper.spreadsheet import read_internship_rows


app = FastAPI(title="AI Internship Email Generator")
frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

email_graph: Optional[Any] = None


def _get_email_graph() -> Any:
    global email_graph
    if email_graph is None:
        email_graph = build_email_graph()
    return email_graph


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/gmail/status")
def get_gmail_status(request: Request, response: Response) -> Dict[str, object]:
    return gmail_status(request, response)


@app.get("/auth/gmail/login")
def start_gmail_login(request: Request, response: Response) -> Dict[str, str]:
    return gmail_login(request, response)


@app.get("/auth/gmail/callback", name="gmail_callback")
def complete_gmail_login(
    request: Request,
    error: Optional[str] = None,
    state: Optional[str] = None,
) -> Response:
    return gmail_callback(request, error, state)


@app.post("/auth/gmail/send")
def send_email_with_gmail(request: Request, payload: SendEmailRequest) -> Dict[str, object]:
    return send_gmail(request, payload)


@app.delete("/auth/gmail/disconnect")
def disconnect_gmail_account(request: Request, response: Response) -> Dict[str, bool]:
    return disconnect_gmail(request, response)


@app.post("/generate-email", response_model=EmailOutput)
def generate_email(payload: GenerateEmailRequest) -> EmailOutput:
    state: GraphState = {
        "resume_text": payload.resume_text,
        "company_description": payload.company_description,
        "sender_name": payload.sender_name,
        "sender_email": payload.sender_email,
        "resume_summary": None,
        "company_summary": None,
        "match_summary": None,
        "email_draft": None,
        "email_final": None,
    }
    result = _get_email_graph().invoke(state)
    email = result.get("email_final")
    if email is None:
        raise HTTPException(status_code=500, detail="Email generation failed.")
    return email


@app.post("/generate-email/from-file", response_model=EmailOutput)
def generate_email_from_file(
    resume_file: UploadFile = File(...),
    company_description: str = Form(...),
    sender_name: Optional[str] = Form(None),
    sender_email: Optional[str] = Form(None),
) -> EmailOutput:
    resume_text = extract_resume_text(resume_file)
    payload = GenerateEmailRequest(
        resume_text=resume_text,
        company_description=company_description,
        sender_name=sender_name,
        sender_email=sender_email,
    )
    return generate_email(payload)


@app.post("/generate-bulk-emails/from-files")
def generate_bulk_emails_from_files(
    resume_file: UploadFile = File(...),
    spreadsheet_file: UploadFile = File(...),
    filter_text: str = Form(""),
    sender_name: Optional[str] = Form(None),
    sender_email: Optional[str] = Form(None),
) -> Dict[str, object]:
    if not (spreadsheet_file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload an Excel .xlsx workbook.")

    try:
        rows, skipped = read_internship_rows(spreadsheet_file.file.read(), filter_text)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if not rows and not skipped:
        raise HTTPException(
            status_code=422,
            detail="No internship rows matched the filter. Check the filter or workbook headers.",
        )

    resume_text = extract_resume_text(resume_file)
    drafts = []
    for row in rows:
        state: GraphState = {
            "resume_text": resume_text,
            "company_description": (
                f"Company: {row['company']}\n"
                f"Internship subject: {row['internship_subject']}\n"
                f"Specialty: {row['specialty']}\n"
                f"Country: {row['country']}\n\n"
                f"Spreadsheet details:\n{row['company_description']}"
            ),
            "sender_name": sender_name,
            "sender_email": sender_email,
            "resume_summary": None,
            "company_summary": None,
            "match_summary": None,
            "email_draft": None,
            "email_final": None,
        }
        result = _get_email_graph().invoke(state)
        email = result.get("email_final")
        if email is None:
            raise HTTPException(
                status_code=500,
                detail=f"Email generation failed for {row['company']} (row {row['row_number']}).",
            )
        drafts.append(
            {
                "worksheet": row["worksheet"],
                "row_number": row["row_number"],
                "company": row["company"],
                "internship_subject": row["internship_subject"],
                "recipient": row["recipient"],
                "subject": email.subject,
                "greeting": email.greeting,
                "body": email.body,
                "signature": email.signature,
            }
        )

    return {"drafts": drafts, "skipped": skipped}
