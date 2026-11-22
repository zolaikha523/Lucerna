"""Exports of a generated dashboard: PDF (dashboard pages), Excel (all tables + insights) and a detailed Word report.

The exported numbers are exactly the computed results shown in the viewer under the same filters; charts are
re-drawn with matplotlib so exports work offline without a browser.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Callable

import pandas as pd

from ..quant import generator
from ..security import audit
from ..security.rbac import CurrentUser, require
from . import static_charts

SKIP = {"text", "methodology"}


def _kpi_value(v: dict, data) -> str:
    if data is None or data.table.empty:
        return "—"
    raw = data.table["value"].iloc[0]
    if data.extra.get("text"):
        return str(raw)
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "—"
    if v.get("kpi") in ("pct", "completeness"):
        return f"{raw:.1f}%"
    return f"{raw:,.1f}" if isinstance(raw, float) and not float(raw).is_integer() else f"{int(raw):,}"


def _filters_text(flt: dict) -> str:
    if not flt:
        return "No filters applied (all records)."
    parts = []
    for c, f in flt.items():
        if f.get("values"):
            parts.append(f"{c}: {', '.join(map(str, f['values']))}")
        elif f.get("range"):
            parts.append(f"{c}: {f['range'][0]} to {f['range'][1]}")
    return "Filters applied — " + "; ".join(parts)


def _collect(d: dict, compute: Callable) -> list[dict]:
    out = []
    for p in d["spec"]["pages"]:
        items = []
        for v in p["visuals"]:
            if v["type"] in SKIP:
                continue
            data, ex, err, vv = compute(v)
            items.append({"v": vv, "data": data, "ex": ex, "err": err})
        out.append({"page": p, "items": items})
    return out


def export(user: CurrentUser, d: dict, frames: dict, flt: dict, fmt: str, compute: Callable) -> bytes:
    require(user, "export", d["project_id"])
    pages = _collect(d, compute)
    meta = {"title": d["branding"].get("title") or d["name"], "org": generator.org_identity(d["project_id"]),
            "generated": datetime.now().strftime("%d %b %Y %H:%M"), "filters": _filters_text(flt), "plan": d["plan"]}
    data = {"pdf": _pdf, "xlsx": _xlsx, "docx": _docx}[fmt](d, pages, meta)
    audit.log(user.username, "DASHBOARD_EXPORTED", f"{fmt}; {meta['filters'][:120]}", project_id=d["project_id"], object_type="dashboard", object_id=d["id"])
    return data


def _image(item) -> bytes | None:
    if item["data"] is None or item["v"]["type"] in ("kpi", "table", "stat_summary", "compare_table"):
        return None
    try:
        return static_charts.to_bytes(item["v"], item["data"], "png")
    except Exception:  # noqa: BLE001 — fall back to the data table
        return None


def _table(item, limit: int = 15) -> pd.DataFrame | None:
    data = item["data"]
    if data is None or data.table is None or data.table.empty:
        return None
    t = data.table.copy()
    if item["v"]["type"] in ("histogram", "box", "map_points", "scatter"):
        return None
    t = t.head(limit)
    for c in t.columns:
        if pd.api.types.is_float_dtype(t[c]):
            t[c] = t[c].round(1)
        if pd.api.types.is_datetime64_any_dtype(t[c]):
            t[c] = t[c].dt.strftime("%Y-%m-%d")
    return t


# ---------------------------------------------------------------- PDF

def _pdf(d: dict, pages: list[dict], meta: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=meta["title"], author=meta["org"].get("name") or "Lucerna")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=20, leading=24, alignment=0, textColor=colors.HexColor("#0F1B2D"))
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=14, textColor=colors.HexColor("#0F1B2D"), spaceBefore=4)
    H3 = ParagraphStyle("h3", parent=ss["Heading4"], fontSize=10.5, textColor=colors.HexColor("#0F1B2D"), spaceAfter=2)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.6, leading=11, textColor=colors.HexColor("#333B47"))
    S = ParagraphStyle("s", parent=B, fontSize=7.4, leading=9.4, textColor=colors.HexColor("#6B7585"))
    esc = lambda x: (str(x or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731

    story = []
    logo = generator.logo_bytes(d)
    if logo:
        story.append(Image(io.BytesIO(logo), width=38 * mm, height=16 * mm, kind="proportional"))
    org = meta["org"]
    if org.get("name"):
        story.append(Paragraph(esc(org["name"]) + (f" · {esc(org.get('project'))}" if org.get("project") else ""), S))
    story += [Paragraph(esc(meta["title"]), H1), Paragraph(esc(meta["plan"].get("purpose")), B),
              Paragraph(f"Generated {meta['generated']} · dashboard version {d['version']} · {esc(meta['filters'])}", S), Spacer(1, 6)]
    wb = (meta["plan"].get("workbook") or {}).get("explanation", [])
    if wb:
        story.append(Paragraph("How the data was selected", H3))
        story += [Paragraph("• " + esc(x), S) for x in wb[:8]]
    story.append(Paragraph("All figures were computed deterministically from the data. Interpretations and follow-up suggestions are rule-based and "
                           "must be reviewed by an analyst; they are not conclusions.", S))
    for pg in pages:
        story.append(PageBreak())
        story.append(Paragraph(esc(pg["page"]["title"]), H2))
        story.append(Paragraph(esc(pg["page"].get("purpose")), S))
        kpis = [it for it in pg["items"] if it["v"]["type"] == "kpi"]
        if kpis:
            cells = [[Paragraph(f"<b>{esc(_kpi_value(it['v'], it['data']))}</b><br/>{esc(it['v'].get('title'))}", B) for it in kpis[:6]]]
            t = Table(cells, colWidths=[(doc.width / max(1, len(cells[0])))] * len(cells[0]))
            t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .4, colors.HexColor("#DDE3EA")), ("INNERGRID", (0, 0), (-1, -1), .4, colors.HexColor("#DDE3EA")),
                                   ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8FB")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            story += [Spacer(1, 4), t, Spacer(1, 6)]
        for it in pg["items"]:
            if it["v"]["type"] == "kpi":
                continue
            block = [Paragraph(esc(it["v"].get("title")), H3)]
            if it["err"]:
                block.append(Paragraph(esc(it["err"]), S))
                story.append(KeepTogether(block))
                continue
            img = _image(it)
            left = []
            if img:
                left.append(Image(io.BytesIO(img), width=150 * mm, height=72 * mm, kind="proportional"))
            else:
                tab = _table(it)
                if tab is not None:
                    data = [list(map(str, tab.columns))] + [[esc(x)[:40] for x in row] for row in tab.astype(str).values.tolist()]
                    tt = Table(data, repeatRows=1)
                    tt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 6.8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
                                            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#DDE3EA"))]))
                    left.append(tt)
            ex = it["ex"] or {}
            right = []
            if ex.get("findings"):
                right.append(Paragraph("<b>Key findings (verified)</b>", B))
                right += [Paragraph("• " + esc(f), B) for f in ex["findings"][:4]]
            if ex.get("interpretation"):
                right.append(Paragraph("<b>Interpretation</b> — " + esc(ex["interpretation"]), B))
            if ex.get("actions"):
                right.append(Paragraph("<b>Suggested follow-up (for review)</b> — " + esc("; ".join(ex["actions"][:2])), B))
            if ex.get("limitations"):
                right.append(Paragraph("<b>Limitations</b> — " + esc("; ".join(ex["limitations"][:3])), S))
            src = ex.get("source") or {}
            right.append(Paragraph(f"Source: {esc(src.get('sheet'))} · {esc(src.get('formula'))} · {esc(src.get('denominator') or '')}", S))
            row = Table([[left or [Paragraph('', S)], right]], colWidths=[155 * mm, doc.width - 155 * mm])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(KeepTogether(block + [row, Spacer(1, 8)]))
    lim = meta["plan"].get("limitations") or []
    if lim:
        story += [PageBreak(), Paragraph("Limitations of this dashboard", H2)] + [Paragraph("• " + esc(x), B) for x in lim]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#8A94A3"))
        canvas.drawString(14 * mm, 7 * mm, f"{meta['title'][:90]} · {meta['generated']}")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ---------------------------------------------------------------- Excel

def _sheet_name(i: int, title: str, used: set) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", f"{i:02d} {title}")[:31].strip()
    name, k = base, 1
    while name in used:
        k += 1
        name = f"{base[:28]}_{k}"
    used.add(name)
    return name


def _xlsx(d: dict, pages: list[dict], meta: dict) -> bytes:
    buf = io.BytesIO()
    used: set = set()
    insights, index = [], []
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        about = [("Dashboard", meta["title"]), ("Organisation", meta["org"].get("name") or ""), ("Generated", meta["generated"]),
                 ("Filters", meta["filters"]), ("Data", meta["plan"].get("purpose")), ("Method", "All numbers computed deterministically; see each table's source.")]
        about += [("Data selection", x) for x in (meta["plan"].get("workbook") or {}).get("explanation", [])]
        about += [("Limitation", x) for x in meta["plan"].get("limitations", [])]
        pd.DataFrame(about, columns=["Item", "Value"]).to_excel(xw, sheet_name="About", index=False)
        n = 0
        kpi_rows = []
        for pg in pages:
            for it in pg["items"]:
                v, ex = it["v"], it["ex"] or {}
                if v["type"] == "kpi":
                    kpi_rows.append({"Page": pg["page"]["title"], "KPI": v.get("title"), "Value": _kpi_value(v, it["data"]),
                                     "Base n": it["data"].base_n if it["data"] is not None else None, "Formula": (ex.get("source") or {}).get("formula")})
                    continue
                for sec in ("what", "findings", "interpretation", "implications", "actions", "limitations"):
                    val = ex.get(sec)
                    for x in (val if isinstance(val, list) else [val]):
                        if x:
                            insights.append({"Page": pg["page"]["title"], "Visual": v.get("title"), "Section": sec, "Text": x})
                if it["data"] is None or it["data"].table is None or it["data"].table.empty:
                    continue
                n += 1
                name = _sheet_name(n, v.get("title") or v["type"], used)
                tab = it["data"].table.copy()
                if v["type"] in ("histogram", "map_points", "scatter"):
                    continue
                if v["type"] in ("heatmap", "correlation"):
                    tab = tab.reset_index()
                tab.to_excel(xw, sheet_name=name, index=False, startrow=3)
                ws = xw.sheets[name]
                ws["A1"] = v.get("title")
                src = ex.get("source") or {}
                ws["A2"] = f"Source: {src.get('sheet')} · {src.get('formula')} · {src.get('denominator') or ''} · {meta['filters']}"
                index.append({"Sheet": name, "Page": pg["page"]["title"], "Visual": v.get("title"), "Base n": it["data"].base_n})
        if kpi_rows:
            pd.DataFrame(kpi_rows).to_excel(xw, sheet_name="KPIs", index=False)
        pd.DataFrame(insights or [{"Page": "", "Visual": "", "Section": "", "Text": "No insights"}]).to_excel(xw, sheet_name="Insights", index=False)
        pd.DataFrame(index).to_excel(xw, sheet_name="Tables index", index=False)
    return buf.getvalue()


# ---------------------------------------------------------------- Word

def _docx(d: dict, pages: list[dict], meta: dict) -> bytes:
    from docx import Document
    from docx.shared import Cm, Pt

    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2)
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10)
    logo = generator.logo_bytes(d)
    if logo:
        doc.add_picture(io.BytesIO(logo), width=Cm(4))
    if meta["org"].get("name"):
        doc.add_paragraph(meta["org"]["name"] + (f" · {meta['org'].get('project')}" if meta["org"].get("project") else ""))
    doc.add_heading(meta["title"], 0)
    doc.add_paragraph(meta["plan"].get("purpose") or "")
    doc.add_paragraph(f"Generated {meta['generated']}. {meta['filters']}")
    doc.add_heading("How this report was produced", 1)
    for x in (meta["plan"].get("workbook") or {}).get("explanation", []):
        doc.add_paragraph(x, style="List Bullet")
    doc.add_paragraph("Every number in this report was computed deterministically from the data. Interpretations, implications and follow-up "
                      "suggestions are generated by rules from those numbers and are labelled; they require analyst review before use.")
    for pg in pages:
        doc.add_heading(pg["page"]["title"], 1)
        if pg["page"].get("purpose"):
            doc.add_paragraph(pg["page"]["purpose"]).italic = True
        kpis = [it for it in pg["items"] if it["v"]["type"] == "kpi"]
        if kpis:
            t = doc.add_table(rows=1, cols=2)
            t.style = "Light List Accent 1"
            t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Headline figure", "Value"
            for it in kpis:
                r = t.add_row().cells
                r[0].text, r[1].text = str(it["v"].get("title")), _kpi_value(it["v"], it["data"])
        for it in pg["items"]:
            v, ex = it["v"], it["ex"] or {}
            if v["type"] == "kpi":
                continue
            doc.add_heading(v.get("title") or "", 2)
            if it["err"]:
                doc.add_paragraph(it["err"])
                continue
            img = _image(it)
            if img:
                doc.add_picture(io.BytesIO(img), width=Cm(15))
            else:
                tab = _table(it, 20)
                if tab is not None:
                    t = doc.add_table(rows=1, cols=len(tab.columns))
                    t.style = "Light Grid Accent 1"
                    for i, c in enumerate(tab.columns):
                        t.rows[0].cells[i].text = str(c)
                    for row in tab.astype(str).values.tolist():
                        cells = t.add_row().cells
                        for i, x in enumerate(row):
                            cells[i].text = x[:60]
            for label, key in (("What the data shows", "what"), ("Key findings (verified)", "findings"), ("Why this matters", "why"),
                               ("Analytical interpretation", "interpretation"), ("Operational implications", "implications"),
                               ("Recommended follow-up (for analyst review)", "actions"), ("Limitations", "limitations")):
                val = ex.get(key)
                if not val:
                    continue
                p = doc.add_paragraph()
                p.add_run(label + ": ").bold = True
                if isinstance(val, list):
                    for x in val:
                        doc.add_paragraph(x, style="List Bullet")
                else:
                    p.add_run(val)
            src = ex.get("source") or {}
            doc.add_paragraph(f"Source: sheet {src.get('sheet')}; variables {', '.join(src.get('variables', [])[:6])}; formula: {src.get('formula')}; "
                              f"denominator: {src.get('denominator') or '—'}; filters: {src.get('filters')}.").runs[0].font.size = Pt(8)
    if meta["plan"].get("limitations"):
        doc.add_heading("Limitations", 1)
        for x in meta["plan"]["limitations"]:
            doc.add_paragraph(x, style="List Bullet")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
