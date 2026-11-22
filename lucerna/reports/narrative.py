"""Guarded AI narrative: the model may only restate numbers that exist in the supplied facts.
Any paragraph containing a number not present in the facts is discarded (never shown)."""
from __future__ import annotations

import re

from ..ai import prompts, providers

NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")


def _numbers(text: str) -> set[str]:
    out = set()
    for m in NUM.findall(text or ""):
        v = m.rstrip("%").replace(",", "")
        try:
            f = float(v)
        except ValueError:
            continue
        out.add(f"{f:.1f}")
        out.add(f"{round(f):.1f}")
    return out


def unsupported_numbers(paragraph: str, facts: str) -> list[str]:
    allowed = _numbers(facts)
    bad = []
    for m in NUM.findall(paragraph or ""):
        v = m.rstrip("%").replace(",", "")
        try:
            f = float(v)
        except ValueError:
            continue
        if f"{f:.1f}" not in allowed and not (1900 <= f <= 2100 and float(f).is_integer()):
            bad.append(m)
    return bad


def guarded_paragraph(section: str, facts: list[str], *, project_id: int | None, classification: str | None) -> tuple[str | None, str | None]:
    facts_text = "\n".join(f"- {f}" for f in facts)
    name, version, tmpl = prompts.QUANT_NARRATIVE
    try:
        obj = providers.chat_json([{"role": "user", "content": tmpl.format(section=section, facts=facts_text)}], prompt_name=name,
                                  prompt_version=version, project_id=project_id, classification=classification)
    except providers.AIError as exc:
        return None, f"AI narrative not generated: {exc}"
    para = str(obj.get("paragraph") or "").strip()
    bad = unsupported_numbers(para, facts_text)
    if bad:
        return None, f"AI narrative discarded: it contained numbers not present in the computed results ({', '.join(bad[:5])})."
    return para or None, None
