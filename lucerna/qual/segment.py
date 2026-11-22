"""Speaker-aware segmentation.

* One segment never mixes two speakers: each speaker turn starts a new segment.
* Long turns are split at sentence boundaries (no overlap, so each sentence lives in exactly one segment).
* Offsets are exact: full_text[start:end] == segment text.
* Moderator / interviewer turns are kept (as context) but flagged speaker_role='moderator'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import SPEAKER_LINE, Extracted

MODERATOR = re.compile(r"^(moderator|facilitator|interviewer|note[- ]?taker|enumerator|researcher|mod|fac|int|q|question)\b", re.I)
HEADER_KEY = re.compile(r"^\s*(title|type|location|date|group|district|province|site|language|interview type|respondent group|participants?)\s*:\s*(.+)$", re.I)


@dataclass
class Segment:
    seq: int
    page: int | None
    paragraph: int
    speaker: str | None
    speaker_role: str
    start: int
    end: int
    text: str


def _speaker(text: str) -> tuple[str | None, str, int]:
    """Return (label, role, end of the label). The label itself ("P3 (female, 28):") is not part of the
    segment text, so it can never end up inside a quotation."""
    m = SPEAKER_LINE.match(text)
    if not m:
        return None, "unknown", 0
    label = " ".join(m.group("label").split())
    return label, "moderator" if MODERATOR.match(label) else "respondent", m.end()


def _sentence_splits(text: str, target: int) -> list[tuple[int, int]]:
    if len(text) <= target:
        return [(0, len(text))]
    bounds = [m.end() for m in re.finditer(r"(?<=[.!?؟。])\s+", text)]
    out, start = [], 0
    last_ok = None
    for b in bounds + [len(text)]:
        if b - start > target and last_ok and last_ok > start:
            out.append((start, last_ok))
            start = last_ok
        last_ok = b
    out.append((start, len(text)))
    return [(a, b) for a, b in out if text[a:b].strip()]


def header_metadata(ex: Extracted, max_lines: int = 12) -> dict:
    """'Key: value' lines at the top of a transcript (suggested metadata — user confirms)."""
    meta = {}
    for p in ex.paragraphs[:3]:
        for line in p.text.split("\n")[:max_lines]:
            m = HEADER_KEY.match(line)
            if m:
                meta[m.group(1).strip().lower()] = m.group(2).strip()
    return meta


def segment(ex: Extracted, target_chars: int = 1200) -> list[Segment]:
    segs: list[Segment] = []
    current_speaker, current_role = None, "unknown"
    seq = 0
    for p in ex.paragraphs:
        if HEADER_KEY.match(p.text.split("\n")[0]) and all(HEADER_KEY.match(l) or not l.strip() for l in p.text.split("\n")):
            role, spk, skip = "metadata", None, 0
        else:
            spk, role, skip = _speaker(p.text)
            if spk is None:          # continuation of the previous speaker's turn
                spk, role = current_speaker, current_role
            current_speaker, current_role = spk, role
        body = p.text[skip:]
        for a, b in _sentence_splits(body, target_chars):
            a, b = a + skip, b + skip
            # trim whitespace but keep offsets exact
            chunk = p.text[a:b]
            lead = len(chunk) - len(chunk.lstrip())
            trail = len(chunk) - len(chunk.rstrip())
            start, end = p.start + a + lead, p.start + b - trail
            seq += 1
            segs.append(Segment(seq, p.page, p.number, spk, role, start, end, ex.full_text[start:end]))
    return segs
