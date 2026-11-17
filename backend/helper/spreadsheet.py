import re
import unicodedata
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _header_columns(values: Tuple[Any, ...]) -> Optional[Dict[str, int]]:
    headers = [_normalized(value) for value in values]
    indexes: Dict[str, int] = {}
    for index, header in enumerate(headers):
        if not header:
            continue
        if "email" in header or "e mail" in header or "courriel" in header:
            indexes["email"] = index
        elif "sujet" in header or "internship subject" in header or header == "subject":
            indexes["subject"] = index
        elif "pays" in header or "country" in header:
            indexes["country"] = index
        elif "specialite" in header or "specialty" in header or "field" == header:
            indexes["specialty"] = index
        elif any(term in header for term in ("societe", "entreprise", "company", "employeur")):
            indexes["company"] = index

    if all(name in indexes for name in ("subject", "company", "email")):
        return indexes
    return None


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_internship_rows(
    content: bytes,
    filter_text: str = "",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError) as error:
        raise ValueError("Could not read this workbook. Upload a valid .xlsx file.") from error

    matched: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    query = _normalized(filter_text)
    try:
        for sheet in workbook.worksheets:
            header_row = None
            indexes = None
            header_values: Tuple[Any, ...] = ()
            for row_number, values in enumerate(
                sheet.iter_rows(min_row=1, max_row=50, values_only=True),
                start=1,
            ):
                detected = _header_columns(values)
                if detected:
                    header_row = row_number
                    indexes = detected
                    header_values = values
                    break
            if header_row is None or indexes is None:
                continue

            for row_number, values in enumerate(
                sheet.iter_rows(min_row=header_row + 1, values_only=True),
                start=header_row + 1,
            ):
                row_text = " ".join(_cell_text(value) for value in values)
                if not row_text.strip():
                    continue
                if query and query not in _normalized(row_text):
                    continue

                company = _cell_text(values[indexes["company"]] if indexes["company"] < len(values) else "")
                subject = _cell_text(values[indexes["subject"]] if indexes["subject"] < len(values) else "")
                recipient = _cell_text(values[indexes["email"]] if indexes["email"] < len(values) else "")
                reason = None
                if not company:
                    reason = "Missing company name"
                elif not subject:
                    reason = "Missing internship subject"
                elif not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", recipient):
                    reason = "Missing or invalid contact email"

                entry = {
                    "worksheet": sheet.title,
                    "row_number": row_number,
                    "company": company,
                    "internship_subject": subject,
                    "recipient": recipient,
                }
                if reason:
                    skipped.append({**entry, "reason": reason})
                    continue

                details = []
                for column, header in enumerate(header_values):
                    if column < len(values) and _cell_text(values[column]):
                        details.append(f"{_cell_text(header) or f'Column {column + 1}'}: {_cell_text(values[column])}")

                matched.append(
                    {
                        **entry,
                        "specialty": _cell_text(values[indexes["specialty"]])
                        if indexes.get("specialty", len(values)) < len(values)
                        else "",
                        "country": _cell_text(values[indexes["country"]])
                        if indexes.get("country", len(values)) < len(values)
                        else "",
                        "company_description": "\n".join(details),
                    }
                )
    finally:
        workbook.close()

    return matched, skipped
