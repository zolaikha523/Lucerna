"""EvidenceQDA report exporters.

Reports deliberately distinguish verified source evidence from analyst-supplied
methodology. Missing study details are labelled as not provided; they are never
fabricated by the exporter.
"""
from pathlib import Path
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
import pandas as pd


def _s(value, fallback="Not provided"):
    if value is None or str(value).strip() == "":
        return fallback
    return str(value).strip()


def _quote_text(q):
    return _s(q.get("verified_quote"), "")


def _theme_map(themes):
    return {str(t.get("theme", "Unclassified")).strip().lower(): t for t in themes if isinstance(t, dict)}


def _codes_for_theme(theme, codes):
    names = {str(x).strip().lower() for x in (theme.get("codes") or [])}
    return [c for c in codes if str(c.get("code", "")).strip().lower() in names]


def _quotes_for_theme(theme, quotes):
    key = str(theme.get("theme", "")).strip().lower()
    return [q for q in quotes if str(q.get("theme", "")).strip().lower() == key]


def _verified_evidence_rows(quotes):
    return [{
        "document_id": q.get("document_id", ""),
        "segment_id": q.get("segment_id", ""),
        "code": q.get("code", ""),
        "theme": q.get("theme", "Unclassified"),
        "verified_quote": q.get("verified_quote", ""),
        "verification_method": q.get("verification_method", ""),
    } for q in quotes if q.get("verified") is True and q.get("verified_quote")]


def _report_context(title, docs, segments, codes, themes, quotes, metadata, analysis_status, warnings):
    metadata = metadata or {}
    n_fgd = sum(1 for d in docs if "fgd" in (d.get("document_type", "") + " " + d.get("filename", "")).lower() or "focus group" in (d.get("document_type", "") + " " + d.get("filename", "")).lower())
    n_kii = sum(1 for d in docs if "kii" in (d.get("document_type", "") + " " + d.get("filename", "")).lower() or "key informant" in (d.get("document_type", "") + " " + d.get("filename", "")).lower())
    findings = len(themes) if themes else len(codes)
    return {
        "title": title, "organization": _s(metadata.get("organization")),
        "project": _s(metadata.get("project")), "sector": _s(metadata.get("sector")),
        "geography": _s(metadata.get("geography")), "study_period": _s(metadata.get("study_period")),
        "purpose": _s(metadata.get("purpose")), "sampling": _s(metadata.get("sampling")),
        "participant_selection": _s(metadata.get("participant_selection")),
        "fgd_details": _s(metadata.get("fgd_details")), "kii_details": _s(metadata.get("kii_details")),
        "inclusion_criteria": _s(metadata.get("inclusion_criteria")), "ethics": _s(metadata.get("ethics")),
        "limitations": _s(metadata.get("limitations")), "analyst": _s(metadata.get("analyst")),
        "methodology_notes": _s(metadata.get("methodology_notes")),
        "documents": docs, "segments": segments, "codes": codes, "themes": themes,
        "quotes": quotes, "verified_count": len(_verified_evidence_rows(quotes)),
        "rejected_count": len(metadata.get("rejected_quotes", [])), "analysis_status": analysis_status or "Not recorded",
        "warnings": warnings or [], "theme_count": len(themes), "code_count": len(codes),
        "document_count": len(docs), "segment_count": len(segments), "finding_count": findings,
        "fgd_document_count": n_fgd, "kii_document_count": n_kii,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _add_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Shading Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = _s(value, "")
            cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    return table


def _setup_doc(title):
    d = Document()
    sec = d.sections[0]
    sec.top_margin = Inches(.7); sec.bottom_margin = Inches(.7)
    sec.left_margin = Inches(.8); sec.right_margin = Inches(.8)
    styles = d.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(10)
    styles["Normal"].font.color.rgb = RGBColor(35, 48, 52)
    for name in ("Title", "Heading 1", "Heading 2"):
        styles[name].font.name = "Aptos Display"
        styles[name].font.color.rgb = RGBColor(43, 61, 65)
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("EVIDENCEQDA  |  RESEARCH REPORT")
    r.bold = True; r.font.size = Pt(11); r.font.color.rgb = RGBColor(43, 61, 65)
    d.add_heading(title, 0)
    return d


def export_docx(title, themes, quotes, path, chat_messages=None, metadata=None, docs=None, segments=None, codes=None, rejected_quotes=None, analysis_status=None, warnings=None):
    docs, segments, codes = docs or [], segments or [], codes or []
    metadata = dict(metadata or {})
    metadata["rejected_quotes"] = rejected_quotes or []
    c = _report_context(title, docs, segments, codes, themes or [], quotes or [], metadata, analysis_status, warnings)
    d = _setup_doc(title)
    d.add_paragraph(f"{c['organization']}  |  {c['geography']}  |  Generated {c['generated_at']}")
    d.add_paragraph("Evidence status: source quotations shown in this report have passed programmatic source-text validation. Interpretation and recommendations require review by the responsible researcher before external/donor use.")

    d.add_heading("1. Executive Summary", 1)
    d.add_paragraph(f"Purpose: {c['purpose']}")
    d.add_paragraph(f"This report package is based on {c['document_count']} uploaded source document(s), segmented into {c['segment_count']} evidence segment(s). The current analysis contains {c['code_count']} open code(s), {c['theme_count']} axial theme(s), and {c['verified_count']} verified quotation(s).")
    if c["verified_count"] == 0:
        d.add_paragraph("No source-verified quotations are currently available. This is not a findings report yet. Review the analysis status and warnings, confirm the local model is working, and rerun analysis before using this document for decision-making.")
    elif c["theme_count"] == 0:
        d.add_paragraph("Open codes and verified quotations are included below, but axial theme synthesis did not produce a usable result. Findings are therefore organized by open code and should be reviewed and clustered by a qualitative researcher.")
    else:
        d.add_paragraph("Key findings are organized by themes below. Each included quotation is linked to its source document and immutable segment identifier to support auditability and independent review.")
    d.add_paragraph("This automated package does not infer sample size, participant demographics, field locations, consent status, or study methods unless those details were supplied by the study team. Missing details are explicitly marked ‘Not provided’ in the methodology section.")

    d.add_heading("2. Introduction and Background", 1)
    d.add_paragraph(f"Project / assessment: {c['project']}")
    d.add_paragraph(f"Sector: {c['sector']}; Geography: {c['geography']}; Study period: {c['study_period']}")
    d.add_paragraph(f"Purpose and problem statement: {c['purpose']}")
    d.add_paragraph("Background and contextual claims should be completed or verified by the study team using approved project documents. EvidenceQDA does not add external contextual claims to transcript findings.")

    d.add_heading("3. Methodology", 1)
    method_rows = [
        ("Data sources", "; ".join(d.get("filename", "") for d in docs) or "Not provided"),
        ("Sampling approach", c["sampling"]), ("Participant selection", c["participant_selection"]),
        ("FGD sessions / locations", c["fgd_details"]), ("Key informant interviews", c["kii_details"]),
        ("Inclusion criteria", c["inclusion_criteria"]), ("Ethics, consent and confidentiality", c["ethics"]),
        ("Limitations", c["limitations"]), ("Analyst / reviewer", c["analyst"]),
        ("Additional methodology notes", c["methodology_notes"]),
    ]
    _add_table(d, ["Method element", "Study-team supplied details"], method_rows)
    d.add_paragraph(f"Processing summary: {c['document_count']} source document(s); {c['segment_count']} deterministic evidence segment(s); SHA-256 fingerprints recorded for uploaded documents in the application.")
    d.add_paragraph("Ethics note: verify that informed consent was obtained and remove or generalize identifying details before external circulation. The application cannot determine whether consent was actually obtained.")

    d.add_heading("4. Key Findings", 1)
    if themes:
        for i, theme in enumerate(themes, 1):
            name = _s(theme.get("theme"), f"Theme {i}")
            d.add_heading(f"4.{i} {name}", 2)
            d.add_paragraph(_s(theme.get("description"), "Theme description not returned by the model; researcher review required."))
            related_codes = _codes_for_theme(theme, codes)
            if related_codes:
                d.add_paragraph("Related open codes: " + "; ".join(_s(x.get("code"), "") for x in related_codes))
            qs = _quotes_for_theme(theme, quotes)
            if not qs:
                d.add_paragraph("No verified quotation was linked to this theme. Do not treat the theme as quote-supported until reviewed.")
            for q in qs:
                p = d.add_paragraph(style="Quote") if "Quote" in d.styles else d.add_paragraph()
                p.add_run("“" + _quote_text(q) + "”").italic = True
                d.add_paragraph(f"Source: {q.get('document_id','')} | Segment: {q.get('segment_id','')} | Code: {q.get('code','')} | Verification: {q.get('verification_method','')}")
    elif codes:
        d.add_paragraph("No axial themes were available; findings are presented by open code without claiming that the codes constitute validated thematic clusters.")
        for i, code in enumerate(codes, 1):
            d.add_heading(f"4.{i} {_s(code.get('code'), 'Open code')}", 2)
            d.add_paragraph(_s(code.get("description"), "Description not available."))
            ids = set(code.get("segment_ids") or [])
            qs = [q for q in quotes if q.get("segment_id") in ids and (not q.get("code") or str(q.get("code")).lower() == str(code.get("code", "")).lower())]
            for q in qs:
                d.add_paragraph(f"“{_quote_text(q)}”")
                d.add_paragraph(f"Source: {q.get('document_id','')} | Segment: {q.get('segment_id','')}")
    else:
        d.add_paragraph("No open codes or verified quotes were returned by the analysis engine. See Section 9 (Analysis Status and Limitations). No findings have been fabricated to fill this section.")

    d.add_heading("5. Analysis and Discussion", 1)
    d.add_paragraph("This section is intentionally evidence-led. Interpretive claims about root causes, group differences, agreement, disagreement, or change over time should be added only after the researcher compares supporting segments and confirms the study design and participant groups.")
    if len(docs) > 1:
        d.add_paragraph("Multiple source documents are present. Document-level triangulation has not been asserted automatically: source labels and study metadata must first confirm which files represent FGDs, KIIs, locations, participant groups, and collection periods.")
    else:
        d.add_paragraph("The current upload contains one source document; FGD–KII triangulation cannot be established from this upload alone.")
    d.add_paragraph("Potential contradictions and negative cases should be documented by the analyst rather than omitted. A code or theme frequency is not, by itself, proof of prevalence or population representativeness.")

    d.add_heading("6. Conclusions and Recommendations", 1)
    if themes or codes:
        d.add_paragraph("The evidence-derived topics below can inform draft actions. They are not presented as final donor recommendations until the responsible team confirms feasibility, mandate, budget, target population, and supporting evidence.")
        rec_rows = []
        items = themes if themes else [{"theme": x.get("code", "Open code"), "description": x.get("description", "")} for x in codes]
        for item in items:
            label = _s(item.get("theme"), "Evidence topic")
            rec_rows.append((label, "Review the linked verified quotations and source segments; validate the finding with the research team and affected participants where appropriate.", "Project / MEAL / research lead (proposed; confirm locally)", "Before final report approval", "To be defined after validation and costing"))
        _add_table(d, ["Evidence topic", "Draft action for validation", "Proposed owner", "Suggested timing", "Resource / indicator"] , rec_rows)
        d.add_paragraph("Before finalization, replace the draft actions with SMART recommendations that specify activity, accountable owner, target group, timeframe, budget/resource implications, and a measurable indicator. Do not attribute these draft actions to participants unless they explicitly proposed them in the source data.")
    else:
        d.add_paragraph("Recommendations are withheld because no analysis findings are available. Generating substantive recommendations without findings would risk inventing evidence.")

    d.add_heading("7. Triangulation and Evidence Matrix", 1)
    matrix = []
    for q in quotes:
        if q.get("verified") is True and q.get("verified_quote"):
            matrix.append((q.get("theme", "Unclassified"), q.get("code", ""), q.get("document_id", ""), q.get("segment_id", ""), q.get("verified_quote", "")))
    if matrix:
        _add_table(d, ["Theme", "Code", "Source document", "Segment ID", "Verified direct quote"], matrix)
    else:
        d.add_paragraph("No verified evidence rows are available for a triangulation matrix.")
    d.add_paragraph("Triangulation status: not automatically confirmed. The study team must classify each document by method (FGD/KII/other), location, group, and collection date before drawing cross-source conclusions.")

    d.add_heading("8. Annexes", 1)
    d.add_heading("Annex A. Source register", 2)
    if docs:
        _add_table(d, ["Document ID", "Filename", "Characters", "SHA-256"], [(x.get("document_id", ""), x.get("filename", ""), x.get("characters", ""), x.get("sha256", "")) for x in docs])
    else:
        d.add_paragraph("No source register available.")
    d.add_heading("Annex B. Open codebook", 2)
    if codes:
        _add_table(d, ["Code", "Description", "Linked segment IDs"], [(x.get("code", ""), x.get("description", ""), ", ".join(x.get("segment_ids") or [])) for x in codes])
    else:
        d.add_paragraph("No open codes available.")
    d.add_heading("Annex C. Study tools and participant profile", 2)
    d.add_paragraph("FGD/KII guides, consent forms, and de-identified demographic summaries were not included in the uploaded source package unless separately supplied by the study team. Attach approved versions before final donor submission. Never include names, phone numbers, exact addresses, or other direct identifiers in this annex.")

    d.add_heading("9. Analysis Status, Quality Assurance and Limitations", 1)
    d.add_paragraph(f"Analysis status: {c['analysis_status']}")
    d.add_paragraph(f"Counts: {c['document_count']} documents; {c['segment_count']} segments; {c['code_count']} codes; {c['theme_count']} themes; {c['verified_count']} verified quotes; {c['rejected_count']} rejected quote candidates.")
    d.add_paragraph("Quote QA: only quotations that match the cited source segment exactly or after whitespace normalization are included in the verified evidence matrix. Rejected candidates are excluded from findings and exports.")
    if c["warnings"]:
        for w in c["warnings"]:
            d.add_paragraph(f"Warning: {w}", style="List Bullet")
    d.add_paragraph("AI-assisted qualitative analysis is not a substitute for trained researcher review. Confirm coding consistency, translation accuracy, context, consent, safeguarding risks, negative cases, and the suitability of any interpretation before external use.")

    if chat_messages:
        d.add_heading("Annex D. Evidence chat log", 1)
        for m in chat_messages:
            d.add_paragraph(f"{m.get('role','').upper()}: {m.get('content','')}")
    d.save(path)


def export_markdown(title, themes, quotes, path, chat_messages=None, metadata=None, docs=None, segments=None, codes=None, rejected_quotes=None, analysis_status=None, warnings=None):
    docs, segments, codes = docs or [], segments or [], codes or []
    metadata = metadata or {}
    lines = [f"# {title}", "", f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "> EvidenceQDA includes only source-verified direct quotations. Researcher review is required before donor submission.", "", "## 1. Executive Summary", "", f"- Source documents: {len(docs)}", f"- Evidence segments: {len(segments)}", f"- Open codes: {len(codes)}", f"- Axial themes: {len(themes or [])}", f"- Verified quotations: {len(_verified_evidence_rows(quotes or []))}", "", f"**Purpose:** {_s(metadata.get('purpose'))}", "", "## 2. Introduction and Background", "", f"**Project:** {_s(metadata.get('project'))}", f"**Organization:** {_s(metadata.get('organization'))}", f"**Sector:** {_s(metadata.get('sector'))}", f"**Geography:** {_s(metadata.get('geography'))}", f"**Study period:** {_s(metadata.get('study_period'))}", "", "## 3. Methodology", "", f"- Sampling: {_s(metadata.get('sampling'))}", f"- Participant selection: {_s(metadata.get('participant_selection'))}", f"- FGD sessions/locations: {_s(metadata.get('fgd_details'))}", f"- KIIs: {_s(metadata.get('kii_details'))}", f"- Inclusion criteria: {_s(metadata.get('inclusion_criteria'))}", f"- Ethics/consent: {_s(metadata.get('ethics'))}", f"- Limitations: {_s(metadata.get('limitations'))}", "", "Missing study details are not inferred or fabricated.", "", "## 4. Key Findings", ""]
    if themes:
        for t in themes:
            lines += [f"### {_s(t.get('theme'), 'Theme')}", "", _s(t.get("description"), "Theme description not available."), ""]
            for q in _quotes_for_theme(t, quotes or []):
                lines += [f"> “{_quote_text(q)}”", f"> Source: {q.get('document_id','')} | Segment: {q.get('segment_id','')} | Code: {q.get('code','')}", ""]
    elif codes:
        lines += ["Axial themes were unavailable; the code-level findings below require researcher clustering.", ""]
        for code in codes:
            lines += [f"### {_s(code.get('code'), 'Open code')}", "", _s(code.get('description'), ""), ""]
    else:
        lines += ["No open codes or verified quotations were returned. Check analysis status before using this as a findings report.", ""]
    lines += ["## 5. Analysis and Discussion", "", "Interpretive conclusions, root causes, group differences, and contradictions require researcher validation against the underlying segments. Cross-document presence alone does not establish FGD–KII triangulation.", "", "## 6. Conclusions and Recommendations", "", "Draft actions must be added after evidence validation, feasibility review, costing, assignment of accountable owners, and definition of measurable indicators. The exporter does not invent final recommendations.", "", "## 7. Triangulation / Evidence Matrix", ""]
    for q in _verified_evidence_rows(quotes or []):
        lines += [f"- **{q['theme']} / {q['code']}** — {q['document_id']} / {q['segment_id']}: “{q['verified_quote']}”", ""]
    lines += ["## 8. Annexes", "", "### Source register", ""]
    for d in docs:
        lines += [f"- {d.get('document_id','')} | {d.get('filename','')} | {d.get('characters','')} characters | SHA-256: {d.get('sha256','')}"]
    lines += ["", "### Open codebook", ""]
    for c in codes:
        lines += [f"- **{c.get('code','')}** — {c.get('description','')} (segments: {', '.join(c.get('segment_ids') or [])})"]
    lines += ["", "### Tools and ethics annex", "", "FGD/KII guides, consent forms and de-identified demographic summaries must be attached by the study team if approved and available. Do not include direct identifiers.", "", "## 9. QA Status and Limitations", "", f"Analysis status: {_s(analysis_status)}", "", "Only exact or whitespace-normalized source-matching quotations are included as verified evidence."]
    for w in warnings or []: lines.append(f"- Warning: {w}")
    if chat_messages:
        lines += ["", "## Evidence chat", ""]
        for m in chat_messages: lines += [f"**{m.get('role','').title()}:** {m.get('content','')}", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def export_excel(rows, path, sheets=None):
    """Write an analysis workbook with separate traceability sheets."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows or []).to_excel(writer, sheet_name="Verified Evidence", index=False)
        for name, data in (sheets or {}).items():
            safe_name = str(name)[:31] or "Data"
            frame = pd.DataFrame(data or [])
            if frame.empty:
                frame = pd.DataFrame({"status": ["No data available"]})
            frame.to_excel(writer, sheet_name=safe_name, index=False)


def export_csv(rows, path):
    pd.DataFrame(rows or []).to_csv(path, index=False, encoding="utf-8-sig")
