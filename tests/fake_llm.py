"""Deterministic stand-in for the local model, used by tests and the demo seed script.

It is NOT an AI: it assigns codes by keyword, proposes one genuine quotation (the first words of
the segment), and deliberately proposes a fabricated quotation and an invalid segment reference
so that the verification gate can be exercised.
"""
from __future__ import annotations

import json
import re

KEYWORDS = [
    ("Distance to distribution point", ["far", "distance", "walk", "hours", "kilometre", "km", "transport"]),
    ("Safety concerns", ["safe", "afraid", "harass", "security", "night", "dark"]),
    ("Market prices", ["price", "expensive", "market", "cost", "afford"]),
    ("Water access", ["water", "well", "tank", "queue", "pump"]),
    ("Information gaps", ["know", "inform", "told", "announce", "list", "registration"]),
    ("Exclusion of vulnerable groups", ["widow", "disab", "elderly", "excluded", "left out", "not on the list"]),
    ("Use of cash", ["cash", "money", "bought", "spent", "debt", "rent", "food"]),
]
FABRICATED = "We were treated like kings and everything was perfect in every way"


def _segments(text: str) -> list[tuple[str, str]]:
    text = text[text.find("SEGMENTS"):] if "SEGMENTS" in text else text
    ids = re.findall(r'"segment_id": "([^"]+)"', text)
    texts = [json.loads('"' + t + '"') for t in re.findall(r'"text": "((?:[^"\\]|\\.)*)"', text)]
    return list(zip(ids, texts))


def fake_chat_json(messages, *, prompt_name: str, prompt_version: str, validator=None, **_kw) -> dict:
    user = messages[-1]["content"]
    if prompt_name.startswith("open_coding") or prompt_name == "open_coding":
        codes, quotes = {}, []
        for i, (sid, text) in enumerate(_segments(user)):
            low = text.lower()
            hit = [name for name, kws in KEYWORDS if any(k in low for k in kws)] or ["Other experiences"]
            for h in hit[:2]:
                codes.setdefault(h, []).append(sid)
            words = text.split()
            if len(words) >= 6:
                quotes.append({"segment_id": sid, "quote": " ".join(words[:min(12, len(words))]), "code": hit[0]})
            if i == 0:
                quotes.append({"segment_id": sid, "quote": FABRICATED, "code": hit[0]})
        out = {"codes": [{"code": k, "definition": f"Segments describing {k.lower()}.", "segment_ids": v + (["DOC-999-S9999"] if k == "Other experiences" else [])}
                         for k, v in codes.items()],
               "quotes": quotes}
    elif "axial" in prompt_name:
        names = re.findall(r"^- (.+?) — ", user, flags=re.M)
        access = [n for n in names if n in ("Distance to distribution point", "Safety concerns", "Water access", "Information gaps")]
        rest = [n for n in names if n not in access]
        themes = []
        if access:
            themes.append({"theme": "Barriers to accessing assistance", "definition": "Practical and safety obstacles respondents described.", "codes": access})
        if rest:
            themes.append({"theme": "Use and adequacy of assistance", "definition": "How assistance was used and whether it met needs.", "codes": rest})
        out = {"themes": themes}
    elif "theme" in prompt_name:
        ids = re.findall(r"\[(DOC-\d+-S\d+)\]", user)
        out = {"explanation": "Respondents in several documents described this pattern (deterministic test summary).", "explanation_segment_ids": ids[:3],
               "contradictions": [{"text": "Some respondents reported no difficulty.", "segment_ids": ids[-1:]}] if len(ids) > 3 else [],
               "negative_cases": [], "community_recommendations": [], "evidence_gaps": ["No data from people with disabilities in this sample."]}
    else:  # evidence Q&A
        ids = re.findall(r"\[(DOC-\d+-S\d+)\]", user)
        out = {"answer": "Respondents mainly described distance and safety (deterministic test answer).", "segment_ids": ids[:2] + ["DOC-404-S0001"], "quotes": []}
    if validator:
        validator(out)
    return out
