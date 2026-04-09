from __future__ import annotations

import io
import re
from pathlib import Path
from typing import List
from zipfile import ZipFile

import pandas as pd
import pdfplumber


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md"}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def split_lines(text: str) -> List[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [normalize_whitespace(line) for line in raw if normalize_whitespace(line)]


def extract_text_from_pdf(file_bytes: bytes) -> str:
    parts: List[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
    return "\n".join(parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    with ZipFile(io.BytesIO(file_bytes)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    text = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"</w:tr>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return "\n".join(split_lines(text))


def extract_text_from_xlsx(file_bytes: bytes) -> str:
    workbook = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, header=None)
    lines: List[str] = []
    for sheet_name, frame in workbook.items():
        lines.append(f"[Sheet] {sheet_name}")
        frame = frame.fillna("")
        for row in frame.values.tolist():
            row_text = " | ".join(str(cell).strip() for cell in row if str(cell).strip())
            if row_text:
                lines.append(row_text)
    return "\n".join(lines)


def extract_text_from_xls(file_bytes: bytes) -> str:
    try:
        return extract_text_from_xlsx(file_bytes)
    except Exception:
        decoded = file_bytes.decode("latin1", "ignore")
        tokens = re.findall(r"[A-Za-z0-9*|/_\-\.\(\):, ]{5,}", decoded)
        lines = [normalize_whitespace(token) for token in tokens]
        lines = [line for line in lines if line and any(ch.isalpha() for ch in line)]
        return "\n".join(lines)


def extract_text(file_name: str, file_bytes: bytes) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")
    if suffix == ".pdf":
        text = extract_text_from_pdf(file_bytes)
    elif suffix == ".docx":
        text = extract_text_from_docx(file_bytes)
    elif suffix == ".xlsx":
        text = extract_text_from_xlsx(file_bytes)
    elif suffix == ".xls":
        text = extract_text_from_xls(file_bytes)
    else:
        text = file_bytes.decode("utf-8", "ignore")
    cleaned = "\n".join(split_lines(text))
    if not cleaned:
        raise ValueError("No extractable text found in the uploaded file.")
    return cleaned

