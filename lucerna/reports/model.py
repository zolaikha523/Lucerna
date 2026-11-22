"""Structured report content model shared by the DOCX and PDF renderers.

A report is a dict:
  {"title", "subtitle", "meta": {...cover fields...}, "brand": {...}, "sections": [Section]}
Section = {"id", "title", "level", "blocks": [Block], "included": bool}
Block kinds:
  paragraph {text, label?}           label marks provenance: "AI draft", "Analyst", "Computed"
  bullets   {items}
  table     {columns, rows, caption?}
  chart     {png_path, caption}
  quote     {text, source, translation?, translation_language?}
  callout   {text, tone: info|warning}
  kv        {rows: [[k, v], ...]}
  pagebreak {}
"""
from __future__ import annotations

PROVENANCE = {
    "computed": "Computed from data",
    "analyst": "Analyst-written",
    "ai_draft": "AI-drafted — requires analyst review",
    "verified_quote": "Verified direct quotation",
    "metadata": "From project metadata",
}


def section(sid: str, title: str, blocks: list[dict], level: int = 1) -> dict:
    return {"id": sid, "title": title, "level": level, "blocks": blocks, "included": True}


def p(text: str, label: str | None = None) -> dict:
    return {"kind": "paragraph", "text": text, "label": label}


def bullets(items: list[str]) -> dict:
    return {"kind": "bullets", "items": items}


def table(columns: list[str], rows: list[list], caption: str | None = None) -> dict:
    return {"kind": "table", "columns": columns, "rows": [["" if v is None else v for v in r] for r in rows], "caption": caption}


def chart(path: str, caption: str) -> dict:
    return {"kind": "chart", "png_path": path, "caption": caption}


def quote(text: str, source: str, translation: str | None = None, lang: str | None = None) -> dict:
    return {"kind": "quote", "text": text, "source": source, "translation": translation, "translation_language": lang}


def callout(text: str, tone: str = "info") -> dict:
    return {"kind": "callout", "text": text, "tone": tone}


def kv(rows: list[list]) -> dict:
    return {"kind": "kv", "rows": rows}


def not_provided(v) -> str:
    return "Not provided" if v in (None, "") else str(v)
