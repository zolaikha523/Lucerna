"""Text extraction that preserves structure (pages, paragraphs) and character offsets.

`full_text` is the exact text used as the verification source of truth. Every paragraph records
its page and paragraph number and its [start, end) offsets in `full_text`.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path


class ExtractionError(Exception):
    pass


@dataclass
class Paragraph:
    page: int | None
    number: int
    start: int
    end: int
    text: str


@dataclass
class Extracted:
    full_text: str
    paragraphs: list[Paragraph]
    method: str
    page_count: int | None = None
    requires_verification: bool = False
    notes: list[str] = field(default_factory=list)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1256", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _build(blocks: list[tuple[int | None, str]], method: str, page_count=None, requires_verification=False, notes=None) -> Extracted:
    parts, paras, pos, n = [], [], 0, 0
    for page, text in blocks:
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            continue
        if parts:
            parts.append("\n\n")
            pos += 2
        n += 1
        paras.append(Paragraph(page, n, pos, pos + len(text), text))
        parts.append(text)
        pos += len(text)
    full = "".join(parts)
    if not full.strip():
        raise ExtractionError("No text could be extracted.")
    return Extracted(full, paras, method, page_count, requires_verification, notes or [])


def extract(data: bytes, filename: str) -> Extracted:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        text = _decode(data).replace("\r\n", "\n").replace("\r", "\n")
        blocks = [(None, b) for b in re.split(r"\n\s*\n", text)]
        # Single-newline speaker lines ("P1: ...\nP2: ...") are also paragraph boundaries.
        split = []
        for page, b in blocks:
            lines = b.split("\n")
            if len(lines) > 1 and sum(bool(SPEAKER_LINE.match(l)) for l in lines) >= 2:
                cur = []
                for l in lines:
                    if SPEAKER_LINE.match(l) and cur:
                        split.append((page, "\n".join(cur)))
                        cur = []
                    cur.append(l)
                if cur:
                    split.append((page, "\n".join(cur)))
            else:
                split.append((page, b))
        return _build(split, "txt")
    if ext == ".docx":
        from docx import Document
        try:
            doc = Document(io.BytesIO(data))
        except Exception as exc:
            raise ExtractionError(f"Could not open the Word document: {exc}") from exc
        blocks = [(None, p.text) for p in doc.paragraphs]
        for t in doc.tables:
            for row in t.rows:
                blocks.append((None, " | ".join(c.text.strip() for c in row.cells)))
        return _build(blocks, "docx", notes=["Word page numbers are not stored in .docx files; paragraph numbers are used for references."])
    if ext == ".pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as exc:
            raise ExtractionError(f"Could not open the PDF: {exc}") from exc
        blocks = []
        for i, page in enumerate(reader.pages, 1):
            txt = page.extract_text() or ""
            for b in re.split(r"\n\s*\n", txt):
                blocks.append((i, b))
        chars = sum(len(b) for _, b in blocks)
        if chars < 40 * max(1, len(reader.pages)) * 0.2:
            return _ocr_pdf(data, len(reader.pages))
        return _build(blocks, "pdf_text", len(reader.pages),
                      notes=["PDF text extraction can alter line breaks and hyphenation; quotations spanning line breaks are matched with whitespace normalisation only."])
    raise ExtractionError(f"Unsupported document type {ext}")


def _ocr_pdf(data: bytes, pages: int) -> Extracted:
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError as exc:
        raise ExtractionError("This PDF appears to be scanned (no text layer). OCR needs Tesseract installed plus the Python packages "
                              "'pytesseract' and 'pypdfium2'. See docs/TROUBLESHOOTING.md → OCR.") from exc
    pdf = pdfium.PdfDocument(data)
    blocks = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=2).to_pil()
        txt = pytesseract.image_to_string(img)
        for b in re.split(r"\n\s*\n", txt):
            blocks.append((i + 1, b))
    return _build(blocks, "ocr", pages, requires_verification=True,
                  notes=["Text was produced by OCR. Quotations from this document are held for manual review against the original scan; they are never auto-verified."])


SPEAKER_LINE = re.compile(
    r"^\s*(?P<label>(?:moderator|facilitator|interviewer|note[- ]?taker|enumerator|researcher|mod|fac|int|q|question|"
    r"respondent|participant|informant|ki|kii|r|p|a|answer|speaker|resp)\s*[-#]?\s*\d{0,3}(?:\s*\([^)]{0,60}\))?)\s*[:：\-–]\s+",
    re.IGNORECASE)
