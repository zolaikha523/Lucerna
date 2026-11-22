"""INGO / donor-ready qualitative report builder.

Direct quotations come ONLY from the verified, analyst-approved register (re-verified against the
stored source at build time). Themes, explanations, conclusions and recommendations come only from
analyst-approved items. Missing methodology is marked 'Not provided' — never inferred.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from .. import db
from ..qual import store
from ..security.rbac import CurrentUser
from ..services import orgs
from . import model as M

MAX_QUOTES_PER_THEME = 6


def source_label(q: dict) -> str:
    parts = [q.get("doc_type"), q.get("respondent_group"), q.get("location"), q.get("collection_date")]
    who = q.get("speaker") or "speaker not identified"
    loc = f"{q.get('document_code')}, segment {str(q.get('segment_code') or '').split('-')[-1]}"
    if q.get("paragraph"):
        loc += f", para. {q['paragraph']}"
    if q.get("page"):
        loc += f", p. {q['page']}"
    return f"{who}; " + ", ".join(p for p in parts if p) + f" ({loc})"


def build(user: CurrentUser, project_id: int, metadata: dict, *, include_unreviewed_themes: bool = False, redact_contacts: bool = True) -> dict:
    proj = orgs.get_project(user, project_id)
    docs = store.list_documents(user, project_id)
    themes_all = store.list_themes(user, project_id)
    top_themes = [t for t in themes_all if t["parent_id"] is None and (t["status"] == "approved" or (include_unreviewed_themes and t["status"] == "suggested"))]
    md = lambda k: M.not_provided(metadata.get(k))
    notes = store.list_notes(user, project_id, approved_only=True)
    summ = store.project_summary(user, project_id)
    codes = {c["id"]: c for c in store.list_codes(user, project_id)}
    from ..qual import pii
    secs = []

    # B executive summary
    ex = [M.p(metadata["executive_summary"], "analyst")] if metadata.get("executive_summary") else [M.callout("The executive summary has not been written yet. It must be written or approved by the research team.", "warning")]
    ex.append(M.kv([["Purpose", md("purpose")], ["Context", md("context")], ["Research objectives", md("objectives")],
                    ["Methodology overview", f"{len(docs)} source document(s): " + ", ".join(f"{n} {k}" for k, n in Counter(d['doc_type'] or 'Other' for d in docs).items())]]))
    if top_themes:
        ex.append(M.p("Main findings (approved themes):", "analyst"))
        ex.append(M.bullets([f"{t['name']}: {t.get('definition') or ''}".strip(": ") for t in top_themes]))
    pri = [n for n in notes if n["kind"] == "recommendation" and (n.get("priority") or "").lower() in ("high", "1", "priority 1")]
    if pri:
        ex.append(M.p("Priority recommendations:", "analyst"))
        ex.append(M.bullets([n["text"] for n in pri]))
    secs.append(M.section("executive_summary", "Executive Summary", ex))

    # C background
    secs.append(M.section("background", "Background and Context", [
        M.kv([["Humanitarian context", md("context")], ["Programme context", md("programme_context")], ["Assessment rationale", md("rationale")],
              ["Research objectives", md("objectives")], ["Research questions", md("research_questions")]])]))

    # D methodology
    by_type = Counter(d["doc_type"] or "Other" for d in docs)
    locs = sorted({d["location"] for d in docs if d.get("location")})
    groups = sorted({d["respondent_group"] for d in docs if d.get("respondent_group")})
    dates = sorted({d["collection_date"] for d in docs if d.get("collection_date")})
    meth = [M.kv([["Research design", md("design")], ["Qualitative approach", md("approach")], ["FGD methodology", md("fgd_method")],
                  ["KII methodology", md("kii_method")], ["Sampling approach", md("sampling")], ["Sample size", md("sample_size")],
                  ["Respondent categories (from document metadata)", "; ".join(groups) or "Not recorded in document metadata"],
                  ["Geographic coverage (from document metadata)", "; ".join(locs) or "Not recorded in document metadata"],
                  ["Data collection dates (from document metadata)", f"{dates[0]} to {dates[-1]}" if dates else "Not recorded"],
                  ["Data collection process", md("data_collection")], ["Ethical considerations", md("ethics")]]),
            M.p(f"Data processing: {len(docs)} document(s) ({', '.join(f'{n} {k}' for k, n in by_type.items())}) were imported into Lucerna, segmented by speaker turn "
                f"({summ['segments']} segments) and coded with AI assistance followed by analyst review. Direct quotations were verified programmatically "
                "against the source text (exact or controlled whitespace/typographic normalisation) and approved by an analyst before inclusion.", "computed"),
            M.p("Counts of documents or speakers are reported to show where evidence comes from; they are not measures of prevalence and do not indicate how many people in the population hold a view.", "computed")]
    secs.append(M.section("methodology", "Methodology", meth))

    # E findings
    fb_sections = []
    if not top_themes:
        fb_sections.append(M.section("findings", "Detailed Findings and Thematic Analysis",
                                     [M.callout("No themes have been approved yet. Review and approve themes in Qualitative Intelligence → Themes before generating findings.", "warning")]))
    else:
        fb_sections.append(M.section("findings", "Detailed Findings and Thematic Analysis",
                                     [M.p(f"This section presents {len(top_themes)} theme(s). Each finding is supported by coded transcript evidence; quotations are verbatim and traceable to their source.", "computed")]))
        for i, t in enumerate(top_themes, 1):
            ev = store.theme_evidence(user, t["id"])
            blocks = []
            if t["status"] != "approved":
                blocks.append(M.callout("This theme has NOT been reviewed by an analyst.", "warning"))
            if t.get("definition"):
                blocks.append(M.p(t["definition"], "analyst" if t["origin"] == "manual" else ("analyst" if t["status"] == "approved" else "ai_draft")))
            if t.get("analytic_explanation"):
                blocks.append(M.p(t["analytic_explanation"], "analyst"))
            for n in [n for n in notes if n["theme_id"] == t["id"] and n["kind"] in ("ai_summary", "interpretation")]:
                blocks.append(M.p(n["text"], "analyst"))
            subs = [s for s in themes_all if s["parent_id"] == t["id"] and s["status"] != "rejected"]
            if subs:
                blocks.append(M.p("Subthemes:", None))
                blocks.append(M.bullets([f"{s['name']}" + (f": {s['definition']}" if s.get("definition") else "") for s in subs]))
            blocks.append(M.table(["Evidence base", "Value"], [["Documents with coded evidence", ev["n_documents"]], ["Coded segments", ev["n_segments"]],
                                                               ["Distinct identified speakers", ev["n_identified_speakers"]],
                                                               ["By document type", ", ".join(f"{k}: {v}" for k, v in ev["by_doc_type"].items())],
                                                               ["By location", ", ".join(f"{k}: {v}" for k, v in ev["by_location"].items())]],
                                  ev.get("counting_note")))
            qs = store.quotes_for_theme(user, t["id"], approved_only=True)[:MAX_QUOTES_PER_THEME]
            if qs:
                for q in qs:
                    text = q["verified_text"]
                    if redact_contacts:
                        text, nred = pii.redact(text)
                    blocks.append(M.quote(text, source_label(q), q.get("translation_text"), q.get("translation_language")))
            else:
                blocks.append(M.callout("No verified, analyst-approved quotation is linked to this theme.", "warning"))
            for kind, title in (("contradiction", "Contradictory evidence"), ("negative_case", "Negative cases"), ("evidence_gap", "Evidence gaps"), ("limitation", "Limitations")):
                items = [n["text"] for n in notes if n["theme_id"] == t["id"] and n["kind"] == kind]
                if kind == "limitation" and t.get("limitations"):
                    items.insert(0, t["limitations"])
                if items:
                    blocks.append(M.p(f"{title}:", None))
                    blocks.append(M.bullets(items))
            fb_sections.append(M.section(f"theme_{t['id']}", f"{i}. {t['name']}", blocks, level=2))
    secs += fb_sections

    cc = [n for n in notes if n["kind"] == "cross_cutting"]
    secs.append(M.section("cross_cutting", "Cross-Cutting Analysis",
                          [M.bullets([n["text"] for n in cc])] if cc else [M.p("No cross-cutting findings (gender, age, disability inclusion, protection, AAP, etc.) have been recorded and approved by the analysis team.", "computed")]))
    concl = [n["text"] for n in notes if n["kind"] == "researcher_conclusion"]
    secs.append(M.section("conclusions", "Conclusions", [M.bullets(concl)] if concl else [M.callout("Conclusions have not been written. They must be written by the research team from the approved findings.", "warning")]))

    recs = [n for n in notes if n["kind"] == "recommendation"]
    theme_name = {t["id"]: t["name"] for t in themes_all}
    rb = []
    if recs:
        rb.append(M.table(["Priority", "Recommended action", "Supporting finding", "Suggested stakeholder", "Follow-up"],
                          [[n.get("priority") or "—", n["text"], theme_name.get(n["theme_id"], "—"), n.get("stakeholder") or "Not assigned", n.get("follow_up") or "—"] for n in recs]))
    else:
        rb.append(M.callout("No recommendations have been approved.", "warning"))
    comm = [n for n in notes if n["kind"] == "community_recommendation"]
    if comm:
        rb.append(M.p("Recommendations voiced by respondents (as expressed in the source data):", None))
        rb.append(M.bullets([n["text"] for n in comm]))
    secs.append(M.section("recommendations", "Recommendations", rb))

    # I annexes
    secs.append(M.section("annex_profile", "Annex A: Respondent and Source Profile",
                          [M.table(["Document", "Type", "Respondent group", "Location", "Date", "Language"],
                                   [[d["document_code"], d["doc_type"] or "—", d.get("respondent_group") or "Not recorded", d.get("location") or "Not recorded",
                                     d.get("collection_date") or "Not recorded", d.get("language") or "Not recorded"] for d in docs])]))
    appr_codes = [c for c in codes.values() if c["status"] == "approved"]
    secs.append(M.section("annex_codebook", "Annex B: Codebook",
                          [M.table(["Code", "Definition", "Segments", "Documents", "Origin"], [[c["name"], c.get("definition") or "", c["n_segments"], c["n_documents"], c["origin"]] for c in appr_codes])]
                          if appr_codes else [M.p("No approved codes.", "computed")]))
    if top_themes:
        doc_codes = [d["document_code"] for d in docs]
        rows = []
        for t in top_themes:
            ev = store.theme_evidence(user, t["id"])
            cnt = Counter(s["document_code"] for s in ev["segments"])
            rows.append([t["name"]] + [cnt.get(dc, 0) for dc in doc_codes])
        secs.append(M.section("annex_matrix", "Annex C: Thematic Matrix", [M.table(["Theme"] + doc_codes, rows, "Number of coded segments per theme and document.")]))
    reg = store.verified_register(user, project_id, approved_only=True)
    secs.append(M.section("annex_quotes", "Annex D: Verified Quotation Register",
                          [M.table(["#", "Quotation (verbatim)", "Source", "Verification"], [[i + 1, q["verified_text"], source_label(q), q["verification_method"]] for i, q in enumerate(reg)])]
                          if reg else [M.p("No approved verified quotations.", "computed")]))
    files = db.query("SELECT d.document_code, d.original_name, d.extraction_method, d.text_sha256 FROM qual_documents d WHERE project_id=? ORDER BY document_code", (project_id,))
    secs.append(M.section("annex_sources", "Annex E: Source Document List",
                          [M.table(["Document", "File", "Extraction", "SHA-256 (extracted text)"], [[f["document_code"], f["original_name"], f["extraction_method"], f["text_sha256"][:16] + "…"] for f in files])]))
    lim = [metadata["limitations"]] if metadata.get("limitations") else []
    ocr = [d["document_code"] for d in docs if d["requires_verification"]]
    if ocr:
        lim.append(f"Documents {', '.join(ocr)} were produced by OCR; their quotations were manually confirmed against the original documents.")
    missing_meta = [d["document_code"] for d in docs if not (d.get("location") and d.get("respondent_group"))]
    if missing_meta:
        lim.append(f"{len(missing_meta)} document(s) lack location or respondent-group metadata, limiting cross-group comparison.")
    lim.append("AI-assisted coding was reviewed by analysts; AI suggestions that were not approved are excluded from this report.")
    lim.append(f"Quality assurance: {summ['quotes_verified']} quotation(s) passed programmatic verification, {summ['quotes_rejected']} were rejected (not found in source, moderator speech, too short, or invalid reference) and {summ['quotes_manual']} await manual review. Rejected quotations never appear in this report.")
    secs.append(M.section("annex_limitations", "Annex F: Methodological Limitations and Quality Assurance", [M.bullets(lim)]))

    approved = metadata.get("_approved", False)
    return {"title": metadata.get("title") or f"Qualitative Assessment Report: {proj['name']}", "subtitle": metadata.get("subtitle") or "Findings from FGDs and KIIs",
            "template": "qualitative",
            "meta": {"organization": proj.get("org_name"), "Project": proj["name"], "Geographic coverage": metadata.get("geography") or proj.get("geography") or "Not provided",
                     "Reporting period": metadata.get("period") or "Not provided", "Report date": date.today().isoformat(), "Prepared by": metadata.get("authors") or "Not provided",
                     "Confidentiality": metadata.get("classification") or proj.get("classification") or "Restricted",
                     "Report status": "Approved" if approved else "DRAFT — not yet approved",
                     "status_note": None if approved else "Draft for review. It has not completed the human review and approval workflow."},
            "brand": {"primary": proj.get("brand_primary") or "#173B68", "accent": proj.get("brand_accent") or "#18B6A4", "logo_path": proj.get("logo_path")},
            "sections": secs, "source": {"project_id": project_id, "verified_quotes": len(reg)}}
