"""Simple, transparent PII detection and redaction for transcripts and exports.
Detection is pattern-based and will miss some identifiers (e.g. names): it supports, but does not
replace, a human de-identification review."""
from __future__ import annotations

import re

PATTERNS = {
    "phone": re.compile(r"(?<!\d)(?:\+|00)?\d[\d\s\-]{7,14}\d(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "id_number": re.compile(r"\b(?:tazkira|tazkera|passport|national id|id no\.?|nid)\s*[:#]?\s*[\w-]{4,}\b", re.I),
}


def detect(text: str) -> list[dict]:
    out = []
    for kind, pat in PATTERNS.items():
        for m in pat.finditer(text or ""):
            out.append({"kind": kind, "start": m.start(), "end": m.end(), "text": m.group(0)})
    return out


def redact(text: str) -> tuple[str, int]:
    n = 0
    for kind, pat in PATTERNS.items():
        text, k = pat.subn(f"[{kind} removed]", text)
        n += k
    return text, n
