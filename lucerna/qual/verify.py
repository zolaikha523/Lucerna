"""STRICT quotation verification — the non-negotiable core of Lucerna's qualitative pillar.

Rules
-----
1. A quotation is VERIFIED only if its text is found in the referenced segment by:
     a. exact substring match, or
     b. controlled normalisation, limited to: Unicode NFC, whitespace runs → single space, and
        typographic quote/apostrophe/dash variants → ASCII. Nothing else (no case folding, no
        spelling repair, no fuzzy matching, no ellipses).
   The stored `verified_text` is always the EXACT original substring of the source (mapped back
   through the normalisation), never the candidate text.
2. The segment must exist in the same project; the quote must not span segments or speakers.
3. Moderator/interviewer speech is never accepted as respondent evidence.
4. Quotes shorter than MIN_WORDS words are rejected as non-evidential.
5. Text found only in a DIFFERENT segment than claimed → manual_review (never auto-verified).
6. Documents produced by OCR (or flagged as uncertain) → manual_review, never auto-verified.
7. Rejected quotations keep their original candidate text for audit but never enter the
   verified register or any report quotation section. No AI repair is attempted.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

MIN_WORDS = 4

_TRANS = {ord(k): v for k, v in {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", "‒": "-", "−": "-", " ": " ", " ": " ", " ": " ",
}.items()}


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Normalise and return, for each output char, the index of the source char it came from."""
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(text):
        c = unicodedata.normalize("NFC", ch).translate(_TRANS)
        for cc in c:
            if cc.isspace():
                if prev_space:
                    continue
                out.append(" ")
                idx.append(i)
                prev_space = True
            else:
                out.append(cc)
                idx.append(i)
                prev_space = False
    return "".join(out), idx


def normalise(text: str) -> str:
    return _norm_with_map(text)[0].strip()


@dataclass
class VerificationResult:
    status: str                 # verified | rejected | manual_review
    method: str                 # exact | normalized | none
    verified_text: str | None
    start: int | None           # offsets relative to the segment text
    end: int | None
    reason: str | None


def _strip_wrapping_quotes(q: str) -> str:
    q = q.strip()
    pairs = [('"', '"'), ("“", "”"), ("'", "'"), ("‘", "’"), ("«", "»")]
    for a, b in pairs:
        if len(q) >= 2 and q.startswith(a) and q.endswith(b):
            return q[1:-1].strip()
    return q


def locate(candidate: str, source: str) -> tuple[str, int, int] | None:
    """Return (method, start, end) of the candidate in source, or None."""
    if not candidate:
        return None
    i = source.find(candidate)
    if i >= 0:
        return "exact", i, i + len(candidate)
    ns, mp = _norm_with_map(source)
    nq = normalise(candidate)
    if not nq:
        return None
    j = ns.find(nq)
    if j < 0:
        return None
    start = mp[j]
    end = mp[j + len(nq) - 1] + 1
    return "normalized", start, end


def verify_against_segment(candidate: str, segment_text: str, speaker_role: str | None = "respondent",
                           requires_manual: bool = False) -> VerificationResult:
    q = _strip_wrapping_quotes(candidate or "")
    if not q:
        return VerificationResult("rejected", "none", None, None, None, "Empty quotation.")
    if "..." in q or "…" in q:
        return VerificationResult("rejected", "none", None, None, None, "Quotation contains an ellipsis; only continuous source text can be verified.")
    if len(q.split()) < MIN_WORDS:
        return VerificationResult("rejected", "none", None, None, None, f"Quotation is shorter than {MIN_WORDS} words and is not meaningful evidence.")
    loc = locate(q, segment_text)
    if not loc:
        return VerificationResult("rejected", "none", None, None, None, "The quotation does not appear in the referenced source segment.")
    method, a, b = loc
    if speaker_role == "moderator":
        return VerificationResult("rejected", method, None, a, b, "The text belongs to the moderator/interviewer, not a respondent.")
    exact = segment_text[a:b]
    if requires_manual:
        return VerificationResult("manual_review", method, exact, a, b,
                                  "Source text came from OCR or uncertain extraction; confirm against the original document before use.")
    return VerificationResult("verified", method, exact, a, b, None)


def find_in_document(candidate: str, segments: list[dict]) -> list[dict]:
    """All segments (in a document) that contain the candidate — used to detect wrong segment references."""
    q = _strip_wrapping_quotes(candidate or "")
    return [s for s in segments if q and locate(q, s["text"])]
