"""PDF renderer (ReportLab) from the same content model: cover, table of contents, running headers,
page numbers, branded tables, charts and quotation styling.

Limitation: ReportLab does not perform Arabic-script shaping/bidi. Dari/Pashto/Arabic text is shown
with the bundled DejaVu font but may not be joined correctly; use the DOCX export (Word shapes text)
for reports with Arabic-script quotations. This is stated in docs/KNOWN_LIMITATIONS.md."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.doctemplate import BaseDocTemplate, PageTemplate
from reportlab.platypus.frames import Frame
from reportlab.platypus.tableofcontents import TableOfContents

from ..config import PROJECT_ROOT
from .model import PROVENANCE

_FONT = "Helvetica"
_BOLD = "Helvetica-Bold"


def _fonts() -> None:
    global _FONT, _BOLD
    fdir = PROJECT_ROOT / "assets" / "fonts"
    try:
        if "LucernaSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("LucernaSans", str(fdir / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("LucernaSans-Bold", str(fdir / "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily("LucernaSans", normal="LucernaSans", bold="LucernaSans-Bold", italic="LucernaSans", boldItalic="LucernaSans-Bold")
        _FONT, _BOLD = "LucernaSans", "LucernaSans-Bold"
    except Exception:
        pass


class _Doc(BaseDocTemplate):
    def __init__(self, path, report, **kw):
        super().__init__(path, pagesize=A4, leftMargin=2.1 * cm, rightMargin=2.1 * cm, topMargin=2.2 * cm, bottomMargin=2 * cm, **kw)
        self.report = report
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=self._cover),
                               PageTemplate(id="body", frames=[frame], onPage=self._body)])

    def _cover(self, canv, doc):
        b = self.report.get("brand") or {}
        canv.saveState()
        canv.setFillColor(colors.HexColor(b.get("primary", "#173B68")))
        canv.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor(b.get("accent", "#18B6A4")))
        canv.rect(0, A4[1] - 1.25 * cm, A4[0], 0.15 * cm, fill=1, stroke=0)
        canv.restoreState()

    def _body(self, canv, doc):
        meta = self.report.get("meta", {})
        canv.saveState()
        canv.setFont(_FONT, 7.5)
        canv.setFillColor(colors.HexColor("#7B8794"))
        canv.drawString(self.leftMargin, A4[1] - 1.3 * cm, f"{self.report['title'][:90]}  ·  {meta.get('Confidentiality', 'Restricted')}")
        canv.drawRightString(A4[0] - self.rightMargin, 1.2 * cm, f"{meta.get('organization') or 'Lucerna'}  ·  Page {doc.page}")
        canv.setStrokeColor(colors.HexColor("#E3E8EF"))
        canv.line(self.leftMargin, A4[1] - 1.45 * cm, A4[0] - self.rightMargin, A4[1] - 1.45 * cm)
        canv.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "_toc_level", None) is not None:
            self.notify("TOCEntry", (flowable._toc_level, flowable.getPlainText(), self.page))


def render(report: dict, path: str | Path) -> str:
    _fonts()
    from reportlab.platypus import NextPageTemplate
    b = report.get("brand") or {}
    primary, accent = colors.HexColor(b.get("primary", "#173B68")), colors.HexColor(b.get("accent", "#18B6A4"))
    S = {
        "title": ParagraphStyle("t", fontName=_BOLD, fontSize=24, leading=30, textColor=colors.HexColor("#101B2D"), spaceAfter=10),
        "sub": ParagraphStyle("s", fontName=_FONT, fontSize=13, leading=17, textColor=primary, spaceAfter=18),
        "h1": ParagraphStyle("h1", keepWithNext=1, fontName=_BOLD, fontSize=15, leading=19, textColor=primary, spaceBefore=12, spaceAfter=8),
        "h2": ParagraphStyle("h2", keepWithNext=1, fontName=_BOLD, fontSize=12, leading=15, textColor=primary, spaceBefore=10, spaceAfter=6),
        "h3": ParagraphStyle("h3", keepWithNext=1, fontName=_BOLD, fontSize=10.5, leading=13, textColor=colors.HexColor("#101B2D"), spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("b", fontName=_FONT, fontSize=9.5, leading=13.5, textColor=colors.HexColor("#2A3442"), spaceAfter=6, alignment=TA_LEFT),
        "small": ParagraphStyle("sm", fontName=_FONT, fontSize=7.8, leading=10, textColor=colors.HexColor("#7B8794"), spaceAfter=6),
        "label": ParagraphStyle("lb", fontName=_FONT, fontSize=7.5, leading=9, textColor=colors.HexColor("#B7791F"), spaceAfter=6),
        "quote": ParagraphStyle("q", fontName=_FONT, fontSize=10, leading=14, textColor=colors.HexColor("#101B2D"), leftIndent=14, borderPadding=(4, 4, 4, 10)),
        "cell": ParagraphStyle("c", fontName=_FONT, fontSize=8, leading=10),
        "cellh": ParagraphStyle("ch", fontName=_BOLD, fontSize=8, leading=10, textColor=colors.white),
        "bullet": ParagraphStyle("bl", fontName=_FONT, fontSize=9.5, leading=13, leftIndent=12, bulletIndent=2, spaceAfter=3),
    }
    meta = report.get("meta", {})
    story = [Spacer(1, 3 * cm)]
    if b.get("logo_path") and Path(b["logo_path"]).exists():
        try:
            story += [Image(b["logo_path"], width=4.5 * cm, height=1.6 * cm, kind="proportional"), Spacer(1, 1 * cm)]
        except Exception:
            pass
    story += [Paragraph(escape((meta.get("organization") or "").upper()), ParagraphStyle("o", parent=S["small"], textColor=accent, fontName=_BOLD, fontSize=9)),
              Spacer(1, 1.2 * cm), Paragraph(escape(report["title"]), S["title"])]
    if report.get("subtitle"):
        story.append(Paragraph(escape(report["subtitle"]), S["sub"]))
    rows = [[Paragraph(escape(k), S["small"]), Paragraph(escape(str(meta[k])), S["body"])] for k in
            ("Project", "Geographic coverage", "Reporting period", "Report date", "Prepared by", "Report status") if meta.get(k)]
    if rows:
        story.append(Table(rows, colWidths=[4.2 * cm, 12 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 1 * cm), Paragraph(f"CLASSIFICATION: {escape(meta.get('Confidentiality', 'Restricted').upper())}",
                                           ParagraphStyle("cl", parent=S["small"], fontName=_BOLD, textColor=colors.HexColor("#B42318")))]
    if meta.get("status_note"):
        story.append(Paragraph(escape(meta["status_note"]), S["small"]))
    story += [NextPageTemplate("body"), PageBreak(), Paragraph("Contents", S["h1"])]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("toc1", fontName=_FONT, fontSize=9.5, leading=14, leftIndent=0),
                       ParagraphStyle("toc2", fontName=_FONT, fontSize=8.8, leading=12, leftIndent=14, textColor=colors.HexColor("#4B5563"))]
    story += [toc, PageBreak()]

    for s in report["sections"]:
        if not s.get("included", True):
            continue
        lvl = s.get("level", 1)
        h = Paragraph(escape(s["title"]), S["h1" if lvl == 1 else ("h2" if lvl == 2 else "h3")])
        h._toc_level = min(lvl - 1, 1) if lvl <= 2 else None
        story.append(h)
        for bl in s["blocks"]:
            k = bl["kind"]
            if k == "paragraph":
                story.append(Paragraph(escape(bl["text"]).replace("\n", "<br/>"), S["body"]))
                if bl.get("label") == "ai_draft":
                    story.append(Paragraph(f"[{PROVENANCE['ai_draft']}]", S["label"]))
            elif k == "bullets":
                for it in bl["items"]:
                    story.append(Paragraph(escape(str(it)), S["bullet"], bulletText="•"))
            elif k in ("table", "kv"):
                if k == "kv":
                    data = [[Paragraph(f"<b>{escape(str(a))}</b>", S["cell"]), Paragraph(escape(str(v)), S["cell"])] for a, v in bl["rows"]]
                    t = Table(data, colWidths=[5 * cm, 11.8 * cm], repeatRows=0)
                    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D5DCE5")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F4F8")),
                                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                else:
                    cols = bl["columns"]
                    data = [[Paragraph(escape(str(c)), S["cellh"]) for c in cols]] + [[Paragraph(escape(_fmt(v)), S["cell"]) for v in r] for r in bl["rows"]]
                    t = Table(data, repeatRows=1, colWidths=[16.8 * cm / len(cols)] * len(cols))
                    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), primary), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D5DCE5")),
                                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                story.append(t)
                story.append(Paragraph(escape(bl.get("caption") or ""), S["small"]) if bl.get("caption") else Spacer(1, 6))
            elif k == "chart":
                if bl.get("png_path") and Path(bl["png_path"]).exists():
                    img = Image(bl["png_path"])
                    ratio = img.imageHeight / img.imageWidth
                    w = 16.2 * cm
                    img.drawWidth, img.drawHeight = w, min(w * ratio, 18 * cm)
                    story.append(KeepTogether([img, Paragraph(escape(bl.get("caption", "")), S["small"])]))
            elif k == "quote":
                parts = [Paragraph(f"“{escape(bl['text'])}”", S["quote"])]
                if bl.get("translation"):
                    parts.append(Paragraph(f"Translation ({escape(bl.get('translation_language') or 'English')}): “{escape(bl['translation'])}”", S["body"]))
                parts.append(Paragraph(f"— {escape(bl['source'])}", S["small"]))
                t = Table([[parts]], colWidths=[16.6 * cm])
                t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 2.5, accent), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8F8")),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
                story += [t, Spacer(1, 6)]
            elif k == "callout":
                t = Table([[Paragraph(escape(bl["text"]), S["body"])]], colWidths=[16.6 * cm])
                t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#B7791F") if bl.get("tone") == "warning" else primary),
                                       ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8EB") if bl.get("tone") == "warning" else colors.HexColor("#F1F5FB"))]))
                story += [t, Spacer(1, 6)]
            elif k == "pagebreak":
                story.append(PageBreak())
    doc = _Doc(str(path), report)
    doc.multiBuild(story)
    return str(path)


def _fmt(v) -> str:
    if isinstance(v, float):
        if v != v:
            return "–"
        return f"{v:,.1f}"
    if isinstance(v, (list, tuple)):
        return " – ".join(_fmt(x) for x in v)
    return "" if v is None else str(v)
