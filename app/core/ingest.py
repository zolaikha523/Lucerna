from pathlib import Path
import re
import hashlib

from docx import Document
from pypdf import PdfReader


def read_file(path: str):
    """
    Read supported qualitative research files.

    Supported:
    - TXT
    - DOCX
    - PDF

    Returns:
        str: extracted text
    """

    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".txt":
        return p.read_text(
            encoding="utf-8",
            errors="replace"
        )

    if ext == ".docx":
        document = Document(path)

        paragraphs = [
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        return "\n\n".join(paragraphs)

    if ext == ".pdf":
        pages = []

        for page in PdfReader(path).pages:
            text = page.extract_text() or ""

            if text.strip():
                pages.append(text.strip())

        return "\n\n".join(pages)

    raise ValueError(
        f"Unsupported file type: {ext}"
    )


def normalize(s: str):
    """
    Normalize text for tolerant quote verification.

    This does NOT modify the original evidence.
    It is used only as a secondary verification method.
    """

    s = (s or "").replace(
        "\u00a0",
        " "
    )

    # Repair common UTF-8/Windows mojibake
    s = s.replace("â€œ", '"')
    s = s.replace("â€", '"')
    s = s.replace("â€™", "'")

    return re.sub(
        r"\s+",
        " ",
        s
    ).strip()


def source_hash(text: str):
    """
    Generate a SHA-256 fingerprint of the original
    extracted source text.
    """

    return hashlib.sha256(
        (text or "").encode("utf-8")
    ).hexdigest()


def _split_long_text(text, target_chars):
    """
    Split a very long paragraph into smaller pieces.

    This is a safety mechanism for transcripts where one
    paragraph contains a very large amount of text.
    """

    text = (text or "").strip()

    if not text:
        return []

    if len(text) <= target_chars:
        return [text]

    pieces = []

    start = 0

    while start < len(text):

        end = min(
            start + target_chars,
            len(text)
        )

        # Prefer a natural sentence boundary.
        if end < len(text):

            search_start = max(
                start,
                end - 300
            )

            boundary = max(
                text.rfind(". ", search_start, end),
                text.rfind("? ", search_start, end),
                text.rfind("! ", search_start, end),
                text.rfind("\n", search_start, end)
            )

            if boundary > start:
                end = boundary + 1

        piece = text[start:end].strip()

        if piece:
            pieces.append(piece)

        start = end

    return pieces


def make_chunks(
    text,
    document_id,
    target_chars=2600,
    overlap=350
):
    """
    Convert a transcript into deterministic evidence segments.

    Design goals:
    - Keep segments close to target_chars.
    - Preserve paragraph boundaries whenever possible.
    - Split unusually large paragraphs safely.
    - Maintain controlled overlap between adjacent segments.
    - Preserve stable document/segment identifiers.
    - Never alter the actual evidence text.
    """

    text = (text or "").replace(
        "\r\n",
        "\n"
    ).replace(
        "\r",
        "\n"
    )

    # ---------------------------------------------------------
    # Extract meaningful paragraphs.
    # ---------------------------------------------------------

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(
            r"\n\s*\n",
            text
        )
        if paragraph.strip()
    ]

    # ---------------------------------------------------------
    # Split paragraphs that are individually too large.
    # ---------------------------------------------------------

    units = []

    for paragraph in paragraphs:

        units.extend(
            _split_long_text(
                paragraph,
                target_chars
            )
        )

    if not units:
        return []

    # ---------------------------------------------------------
    # Build deterministic chunks.
    # ---------------------------------------------------------

    chunks = []

    current_parts = []
    current_length = 0

    for unit in units:

        unit_length = len(unit)

        # If adding this unit would exceed the target,
        # finalize the current chunk first.
        if (
            current_parts
            and current_length + 2 + unit_length > target_chars
        ):

            chunk_text = "\n\n".join(
                current_parts
            ).strip()

            if chunk_text:
                chunks.append(
                    chunk_text
                )

            # -------------------------------------------------
            # Controlled overlap.
            #
            # We take the tail of the completed chunk and
            # carry it into the next segment.
            # -------------------------------------------------

            tail = chunk_text[-overlap:].strip()

            if tail:
                current_parts = [
                    tail,
                    unit
                ]

                current_length = (
                    len(tail)
                    + 2
                    + unit_length
                )

            else:
                current_parts = [
                    unit
                ]

                current_length = unit_length

        else:

            current_parts.append(
                unit
            )

            if current_length:
                current_length += 2

            current_length += unit_length

    # ---------------------------------------------------------
    # Final chunk.
    # ---------------------------------------------------------

    if current_parts:

        chunk_text = "\n\n".join(
            current_parts
        ).strip()

        if chunk_text:
            chunks.append(
                chunk_text
            )

    # ---------------------------------------------------------
    # Create immutable evidence records.
    # ---------------------------------------------------------

    evidence_segments = []

    search_cursor = 0

    for index, chunk_text in enumerate(
        chunks,
        start=1
    ):

        # Locate the chunk in the normalized source text.
        position = text.find(
            chunk_text,
            search_cursor
        )

        if position >= 0:

            start = position
            end = position + len(
                chunk_text
            )

            search_cursor = max(
                start + 1,
                end - overlap
            )

        else:

            # Overlap may create a synthetic boundary that
            # is difficult to locate exactly. In that case
            # retain deterministic metadata without failing
            # the ingestion process.

            start = 0
            end = len(chunk_text)

        evidence_segments.append(
            {
                "document_id": document_id,
                "segment_id": (
                    f"{document_id}_SEG_{index:04d}"
                ),
                "start": start,
                "end": end,
                "text": chunk_text
            }
        )

    return evidence_segments