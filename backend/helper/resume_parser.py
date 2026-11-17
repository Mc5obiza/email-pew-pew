import io
 # type: ignore
import pdfplumber  # type: ignore
from fastapi import HTTPException, UploadFile
from unstructured.partition.auto import partition  # type: ignore


def _extract_text_from_pdf(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
        if text:
            return text

    raise HTTPException(
        status_code=500,
        detail="Unable to parse PDF with pdfplumber.",
    )



def extract_resume_text(upload: UploadFile) -> str:
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty resume file uploaded.")

    filename = (upload.filename or "").lower()
    if filename.endswith(".pdf"):
        return _extract_text_from_pdf(content)
    if filename.endswith(".txt"):
        return content.decode("utf-8", errors="ignore").strip()

    elements = partition(file=io.BytesIO(content))
    text = "\n".join(str(element) for element in elements).strip()
    if text:
        return text

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Use PDF, DOCX, or TXT.",
    )
