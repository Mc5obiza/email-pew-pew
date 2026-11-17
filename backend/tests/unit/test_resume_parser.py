from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
import pytest

from helper.resume_parser import extract_resume_text


pytestmark = pytest.mark.unit


def test_extracts_trimmed_text_resume() -> None:
    upload = UploadFile(
        filename="resume.txt",
        file=BytesIO(b"  Python developer\n  "),
    )

    assert extract_resume_text(upload) == "Python developer"


def test_rejects_empty_resume() -> None:
    upload = UploadFile(filename="resume.txt", file=BytesIO(b""))

    with pytest.raises(HTTPException) as error:
        extract_resume_text(upload)

    assert error.value.status_code == 400
    assert error.value.detail == "Empty resume file uploaded."
