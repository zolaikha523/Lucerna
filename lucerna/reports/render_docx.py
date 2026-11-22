"""Editable Word renderer: branded cover, table of contents field, headers/footers with page numbers,
confidentiality marking, heading hierarchy, styled tables, charts, quotations and provenance labels."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .model import PROVENANCE


def _rgb(hexs: str) -> RGBColor:
    h = hexs.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _shade(cell, hexs: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hexs.lstrip("#"))
    tcPr.append(shd)


def _field(paragraph, instr: str, placeholder: str = "") -> None:
    def fc(kind):
        r = paragraph.add_run()
        el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind)
        r._r.append(el)
    fc("begin")
    r = paragraph.add_run()
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instr} "
    r._r.append(it)
    fc("separate")
    paragraph.add_run(placeholder)
    fc("end")


def _left_border(paragraph, hexs: str) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    for k, v in (("w:val", "single"), ("w:sz", "18"), ("w:space", "10"), ("w:color", hexs.lstrip("#"))):
        left.set(qn(k), v)
    bdr.append(left)
    pPr.append(bdr)


def render(report: dict, path: str | Path) -> str:
    brand = report.get("brand") or {}
    primary, accent = brand.get("primary", "#173B68"), brand.get("accent", "#18B6A4")
    ink = "#101B2D"
    d = Document()
    st = d.styles
    st["Normal"].font.name = "Calibri"
    st["Normal"].font.size = Pt(10.5)
    st["Normal"].font.color.rgb = _rgb("#2A3442")
    st["Normal"].paragraph_format.space_after = Pt(6)
    st["Normal"].paragraph_format.line_spacing = 1.15
    rpr = st["Normal"].element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:cs"), "Arial")  # complex-script (Dari/Pashto/Arabic) fallback; Word performs shaping
    rpr.append(fonts)
    for name, size, color in (("Title", 28, ink), ("Heading 1", 16, primary), ("Heading 2", 13, primary), ("Heading 3", 11.5, ink)):
        s = st[name]
        s.font.name = "Calibri Light" if name != "Heading 3" else "Calibri"
        s.font.size = Pt(size)
        s.font.color.rgb = _rgb(color)
        s.font.bold = name != "Title"
    sec = d.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(2.2))
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
    sec.different_first_page_header_footer = True

    # ---------- cover
    meta = report.get("meta", {})
    if brand.get("logo_path") and Path(brand["logo_path"]).exists():
        try:
            d.add_picture(str(brand["logo_path"]), width=Cm(4.5))
        except Exception:
            pass
    bar = d.add_paragraph()
    r = bar.add_run((meta.get("organization") or "").upper())
    r.font.size, r.font.bold, r.font.color.rgb = Pt(10), True, _rgb(accent)
    for _ in range(5):
        d.add_paragraph()
    t = d.add_paragraph(style="Title")
    t.add_run(report["title"])
    if report.get("subtitle"):
        sp = d.add_paragraph()
        rr = sp.add_run(report["subtitle"]); rr.font.size = Pt(14); rr.font.color.rgb = _rgb(primary)
    d.add_paragraph()
    tbl = d.add_table(rows=0, cols=2)
    for k in ("Project", "Geographic coverage", "Reporting period", "Report date", "Prepared by", "Report status"):
        if meta.get(k):
            cells = tbl.add_row().cells
            cells[0].text, cells[1].text = k, str(meta[k])
            cells[0].paragraphs[0].runs[0].font.color.rgb = _rgb("#7B8794")
            cells[0].paragraphs[0].runs[0].font.size = Pt(9)
            cells[0].width, cells[1].width = Cm(4.5), Cm(11)
    d.add_paragraph()
    conf = d.add_paragraph()
    rc = conf.add_run(f"CLASSIFICATION: {meta.get('Confidentiality', 'Restricted').upper()}")
    rc.font.bold, rc.font.size, rc.font.color.rgb = True, Pt(9), _rgb("#B42318")
    if meta.get("status_note"):
        n = d.add_paragraph(); rn = n.add_run(meta["status_note"]); rn.font.size = Pt(9); rn.italic = True
    d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # header/footer for body pages
    hdr = sec.header.paragraphs[0]
    hdr.text = f"{report['title']}  ·  {meta.get('Confidentiality', 'Restricted')}"
    hdr.runs[0].font.size, hdr.runs[0].font.color.rgb = Pt(8), _rgb("#7B8794")
    ftr = sec.footer.paragraphs[0]
    ftr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = ftr.add_run(f"{meta.get('organization') or 'Lucerna'}  ·  Page ")
    run.font.size = Pt(8)
    _field(ftr, "PAGE", "1")
    for rr in ftr.runs:
        rr.font.size, rr.font.color.rgb = Pt(8), _rgb("#7B8794")

    # ---------- TOC
    d.add_heading("Contents", 1)
    tp = d.add_paragraph()
    _field(tp, 'TOC \\o "1-2" \\h \\z \\u', "Right-click and choose 'Update field' (or press F9) to build the table of contents.")
    d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    for s in report["sections"]:
        if not s.get("included", True):
            continue
        d.add_heading(s["title"], s.get("level", 1))
        for b in s["blocks"]:
            k = b["kind"]
            if k == "paragraph":
                para = d.add_paragraph(b["text"])
                if b.get("label") in ("ai_draft",):
                    lab = d.add_paragraph()
                    lr = lab.add_run(f"[{PROVENANCE['ai_draft']}]"); lr.italic = True; lr.font.size = Pt(8); lr.font.color.rgb = _rgb("#B7791F")
            elif k == "bullets":
                for it in b["items"]:
                    d.add_paragraph(str(it), style="List Bullet")
            elif k == "kv":
                tb = d.add_table(rows=0, cols=2)
                tb.style = "Table Grid"
                for kk, vv in b["rows"]:
                    c = tb.add_row().cells
                    c[0].text, c[1].text = str(kk), str(vv)
                    _shade(c[0], "#F1F4F8")
                    c[0].paragraphs[0].runs[0].font.bold = True
                d.add_paragraph()
            elif k == "table":
                cols = b["columns"]
                tb = d.add_table(rows=1, cols=len(cols))
                tb.style = "Table Grid"
                tb.alignment = WD_TABLE_ALIGNMENT.CENTER
                for i, c in enumerate(cols):
                    cell = tb.rows[0].cells[i]
                    cell.text = str(c)
                    _shade(cell, primary)
                    run = cell.paragraphs[0].runs[0]
                    run.font.bold, run.font.color.rgb, run.font.size = True, _rgb("#FFFFFF"), Pt(9)
                for ri, row in enumerate(b["rows"]):
                    cells = tb.add_row().cells
                    for i, val in enumerate(row):
                        cells[i].text = _fmt(val)
                        for pr in cells[i].paragraphs:
                            for rn in pr.runs:
                                rn.font.size = Pt(9)
                        if ri % 2:
                            _shade(cells[i], "#F5F7FA")
                if b.get("caption"):
                    cp = d.add_paragraph(); cr = cp.add_run(b["caption"]); cr.italic = True; cr.font.size = Pt(8.5); cr.font.color.rgb = _rgb("#7B8794")
                else:
                    d.add_paragraph()
            elif k == "chart":
                if b.get("png_path") and Path(b["png_path"]).exists():
                    d.add_picture(b["png_path"], width=Cm(15.5))
                    cp = d.add_paragraph(); cr = cp.add_run(b.get("caption", "")); cr.italic = True; cr.font.size = Pt(8.5); cr.font.color.rgb = _rgb("#7B8794")
            elif k == "quote":
                qp = d.add_paragraph()
                qp.paragraph_format.left_indent = Cm(0.8)
                _left_border(qp, accent)
                qr = qp.add_run(f"“{b['text']}”"); qr.italic = True; qr.font.size = Pt(10.5)
                if b.get("translation"):
                    tp2 = d.add_paragraph(); tp2.paragraph_format.left_indent = Cm(0.8)
                    tr = tp2.add_run(f"Translation ({b.get('translation_language') or 'English'}): “{b['translation']}”"); tr.font.size = Pt(9.5)
                src = d.add_paragraph(); src.paragraph_format.left_indent = Cm(0.8)
                sr = src.add_run(f"— {b['source']}"); sr.font.size = Pt(8.5); sr.font.color.rgb = _rgb("#7B8794")
            elif k == "callout":
                cp = d.add_paragraph()
                _left_border(cp, "#B7791F" if b.get("tone") == "warning" else primary)
                cp.paragraph_format.left_indent = Cm(0.4)
                cr = cp.add_run(b["text"]); cr.font.size = Pt(9.5)
            elif k == "pagebreak":
                d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    d.save(str(path))
    return str(path)


def _fmt(v) -> str:
    if isinstance(v, float):
        if v != v:
            return "–"
        return f"{v:,.1f}" if abs(v) < 1e6 else f"{v:,.0f}"
    if isinstance(v, (list, tuple)):
        return " – ".join(_fmt(x) for x in v)
    return "" if v is None else str(v)
