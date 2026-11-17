import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    load_dotenv(backend_dir / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Set OPENAI_API_KEY in the environment or backend/.env to run the live LLM smoke test.",
            file=sys.stderr,
        )
        return 2

    from fastapi.testclient import TestClient

    from main import app

    workbook_path = backend_dir / "samples" / "mock_internships.xlsx"
    resume = (
        "Alex Morgan is a computer science student with experience building "
        "Python applications, REST APIs, data pipelines, and machine learning "
        "prototypes. Alex has collaborated on small software teams and is "
        "seeking an internship focused on practical engineering and learning."
    )
    with TestClient(app) as client, workbook_path.open("rb") as workbook:
        response = client.post(
            "/generate-bulk-emails/from-files",
            files={
                "resume_file": ("mock_resume.txt", resume.encode("utf-8"), "text/plain"),
                "spreadsheet_file": (
                    workbook_path.name,
                    workbook,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            data={
                "sender_name": "Alex Morgan",
                "sender_email": "alex@example.com",
            },
        )

    if response.status_code != 200:
        print(
            f"Pipeline request failed ({response.status_code}): {response.text}",
            file=sys.stderr,
        )
        return 1

    result = response.json()
    drafts = result["drafts"]
    skipped = result["skipped"]
    print(f"Generated drafts: {len(drafts)}")
    print(f"Skipped rows: {len(skipped)}")
    for draft in drafts:
        print(f"- {draft['company']}: {draft['subject']}")

    if len(drafts) != 10 or skipped:
        print("Expected 10 generated drafts and no skipped rows.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
