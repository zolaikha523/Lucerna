"""Qualitative pages: documents, coding & codebook, themes & findings, quotations & evidence, evidence Q&A."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...qual import store
from ...qual.store import NOTE_KINDS
from ...services import jobs
from ...services.files import QUAL_EXT
from .. import common, theme

DOC_TYPES = ["FGD", "KII", "Individual interview", "Observation", "Other"]


def _doc_label(d: dict) -> str:
    return f"{d['document_code']} · {d.get('doc_type') or ''} · {d.get('title') or d.get('original_name')}"


# ---------------------------------------------------------------- Documents

def documents() -> None:
    u = common.cu()
    theme.page_header("Documents", "Transcripts and notes from FGDs, KIIs and interviews. Text is segmented by speaker turn with page and paragraph references.", "file-text")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    if common.can(u, "data.upload"):
        with st.expander("Upload transcripts", icon=":material/upload:", expanded=not store.list_documents(u, pid)):
            st.caption(f"Accepted: {', '.join(sorted(QUAL_EXT))}. Scanned PDFs are read with OCR only if Tesseract is installed; OCR text is always flagged for manual verification "
                       "and its quotations are never auto-verified.")
            with st.form("upq", clear_on_submit=True):
                files_ = st.file_uploader("Files", type=[e.strip(".") for e in QUAL_EXT], accept_multiple_files=True)
                c1, c2, c3 = st.columns(3)
                dtype = c1.selectbox("Type (leave as Detect to read it from the file)", ["Detect"] + DOC_TYPES)
                loc = c2.text_input("Location (optional)")
                grp = c3.text_input("Respondent group (optional)", placeholder="e.g. Women, returnees")
                c1, c2 = st.columns(2)
                date = c1.text_input("Collection date (optional)", placeholder="YYYY-MM-DD")
                lang = c2.text_input("Language (optional)", placeholder="e.g. Dari")
                if st.form_submit_button("Upload and segment", type="primary") and files_:
                    for f in files_:
                        with common.guard(f"Imported {f.name}"):
                            store.import_document(u, pid, f.name, f.getvalue(), {"doc_type": None if dtype == "Detect" else dtype, "location": loc,
                                                                                 "respondent_group": grp, "collection_date": date, "language": lang})
    docs = store.list_documents(u, pid)
    if not docs:
        theme.empty_state("No documents yet", "Upload FGD or KII transcripts (TXT, DOCX or PDF).", "file-text")
        return
    df = pd.DataFrame(docs)
    df["verification"] = df["requires_verification"].map({1: "OCR — manual verification", 0: "Text layer"})
    common.table(df, {"document_code": "Code", "title": "Title", "doc_type": "Type", "location": "Location", "respondent_group": "Group",
                      "collection_date": "Date", "language": "Language", "n_segments": "Segments", "verification": "Extraction", "status": "Status"})
    did = st.selectbox("Open document", [d["id"] for d in docs], format_func={d["id"]: _doc_label(d) for d in docs}.get)
    d = store.get_document(u, did)
    t1, t2, t3 = st.tabs(["Segments", "Metadata", "Original text"])
    with t1:
        segs = store.segments(u, did)
        role_f = st.segmented_control("Show", ["All", "Respondents", "Moderator"], default="All", key="segrole")
        for s in segs:
            if role_f == "Respondents" and s["speaker_role"] == "moderator" or role_f == "Moderator" and s["speaker_role"] != "moderator":
                continue
            tone = {"moderator": "neutral", "respondent": "teal"}.get(s["speaker_role"], "info")
            ref = f"{s['segment_code']} · p.{s['page'] or '—'} ¶{s['paragraph'] or '—'}"
            st.markdown(f"{theme.pill(s['speaker'] or 'Unattributed', tone)} <span class='lc-muted'>{theme.esc(ref)}</span><br>{theme.esc(s['text'])}",
                        unsafe_allow_html=True)
    with t2:
        sugg = d["metadata"].get("suggested_from_header") or {}
        if sugg:
            st.caption("Found in the document header: " + "; ".join(f"{k}: {v}" for k, v in sugg.items()))
        for n in d["metadata"].get("extraction_notes") or []:
            st.caption(f"Extraction: {n}")
        if d["metadata"].get("pii_patterns_detected"):
            st.warning(f"{d['metadata']['pii_patterns_detected']} phone/e-mail/ID-like pattern(s) detected. They are redacted in reports by default.")
        with st.form("docmeta"):
            c1, c2 = st.columns(2)
            title = c1.text_input("Title", d.get("title") or "")
            dt = c2.selectbox("Type", DOC_TYPES, index=DOC_TYPES.index(d["doc_type"]) if d.get("doc_type") in DOC_TYPES else len(DOC_TYPES) - 1)
            c1, c2 = st.columns(2)
            loc = c1.text_input("Location", d.get("location") or sugg.get("location") or "")
            grp = c2.text_input("Respondent group", d.get("respondent_group") or "")
            c1, c2 = st.columns(2)
            date = c1.text_input("Collection date", d.get("collection_date") or sugg.get("date") or "")
            lang = c2.text_input("Language", d.get("language") or "")
            if st.form_submit_button("Save metadata", disabled=not common.can(u, "qual.code")):
                with common.guard("Saved"):
                    store.update_document(u, did, title=title, doc_type=dt, location=loc, respondent_group=grp, collection_date=date, language=lang)
                    st.rerun()
        if common.can(u, "data.delete"):
            if st.button("Delete document", icon=":material/delete:"):
                st.session_state["confirm_del_doc"] = did
            if st.session_state.get("confirm_del_doc") == did:
                st.warning("This removes the document, its segments, code applications and quotations.")
                if st.button("Yes, delete permanently", type="primary"):
                    with common.guard("Deleted"):
                        store.delete_document(u, did)
                        st.session_state.pop("confirm_del_doc", None)
                        st.rerun()
    with t3:
        st.caption(f"SHA-256 {d['text_sha256'][:16]}… · {d['char_count']:,} characters · extraction method: {d['extraction_method']}")
        st.text_area("Extracted text (read-only)", d["full_text"], height=420, disabled=True)


# ---------------------------------------------------------------- Coding

def coding() -> None:
    u = common.cu()
    theme.page_header("Coding & Codebook", "AI suggestions are drafts. Analysts approve, rename, merge, split or reject codes, and every change is recorded.", "tags")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    docs = store.list_documents(u, pid)
    if not docs:
        theme.empty_state("No documents yet", "Upload transcripts in Documents first.", "file-text")
        return
    can_code = common.can(u, "qual.code")
    with st.expander("AI-assisted coding (local model)", icon=":material/auto_awesome:"):
        st.caption("Runs open coding, then axial grouping into themes, using the configured local model (Ollama by default). The run continues in the background: "
                   "you can leave this page. Quotes the model proposes are verified against the source; anything that does not match exactly is rejected or held for review.")
        sel = st.multiselect("Documents", [d["id"] for d in docs], default=[d["id"] for d in docs], format_func={d["id"]: _doc_label(d) for d in docs}.get)
        c1, c2 = st.columns(2)
        axial = c1.checkbox("Group codes into themes (axial coding)", value=True)
        ta = c2.checkbox("Theme analysis (contradictions, gaps, recommendations)", value=True)
        if st.button("Start AI coding", type="primary", disabled=not common.can(u, "ai.use") or bool(st.session_state.get("job_coding"))):
            with common.guard():
                st.session_state["job_coding"] = jobs.submit("qual_ai_coding", {"project_id": pid, "user_id": u.id, "document_ids": sel,
                                                                                  "run_axial": axial, "run_theme_analysis": ta}, project_id=pid, user_id=u.id)
                st.rerun()
        common.job_panel("job_coding")
        failed = [j for j in jobs.list_for_project(pid, 5) if j["kind"] == "qual_ai_coding" and j["status"] in ("failed", "cancelled")]
        if failed and not st.session_state.get("job_coding"):
            if st.button("Resume last interrupted run from its checkpoint", icon=":material/replay:"):
                with common.guard():
                    j = jobs.get(failed[0]["id"])
                    st.session_state["job_coding"] = jobs.submit("qual_ai_coding", j["params"], project_id=pid, user_id=u.id, resume_from=failed[0]["id"])
                    st.rerun()
    codes = store.list_codes(u, pid)
    s = store.project_summary(u, pid)
    theme.kpi_row([("Codes", s["codes"], f"{s['codes_approved']} approved", "tags"), ("Segments", s["segments"], f"in {s['documents']} documents", "rows-3"),
                   ("Themes", s["themes"], f"{s['themes_approved']} approved", "network"), ("Verified quotes", s["quotes_verified"], f"{s['quotes_approved']} approved for reports", "quote")])
    st.write("")
    t1, t2, t3, t4 = st.tabs(["Codebook", "Code a segment", "Merge / split", "Codebook versions"])
    with t1:
        if not codes:
            st.caption("No codes yet. Run AI coding or add codes manually.")
        else:
            df = pd.DataFrame(codes)
            ed = st.data_editor(df[["id", "name", "definition", "category", "origin", "status", "n_segments", "n_documents"]], hide_index=True, width="stretch",
                                key="cb_ed", disabled=["id", "origin", "status", "n_segments", "n_documents"] if can_code else True,
                                column_config={"id": None, "n_segments": "Segments", "n_documents": "Documents"})
            c1, c2, c3 = st.columns(3)
            if can_code and c1.button("Save edits", icon=":material/save:"):
                with common.guard("Codebook updated"):
                    for (_, a), (_, b) in zip(df.iterrows(), ed.iterrows()):
                        if (a["name"], a["definition"], a["category"]) != (b["name"], b["definition"], b["category"]):
                            store.update_code(u, int(a["id"]), name=b["name"], definition=b["definition"], category=b["category"])
                    st.rerun()
            pend = [c for c in codes if c["status"] == "suggested"]
            if pend and can_code:
                ids = c2.multiselect("Suggested codes to review", [c["id"] for c in pend], format_func={c["id"]: c["name"] for c in pend}.get, key="rev_codes")
                a1, a2 = c3.columns(2)
                if a1.button("Approve", disabled=not ids):
                    with common.guard("Approved"):
                        for i in ids:
                            store.review_code(u, i, True)
                        st.rerun()
                if a2.button("Reject", disabled=not ids):
                    with common.guard("Rejected"):
                        for i in ids:
                            store.review_code(u, i, False)
                        st.rerun()
            cid = st.selectbox("Inspect code", [c["id"] for c in codes], format_func={c["id"]: c["name"] for c in codes}.get, key="insp_code")
            for sg in store.code_segments(u, cid):
                c1, c2 = st.columns([8, 1])
                c1.markdown(f"<span class='lc-muted'>{theme.esc(sg['segment_code'])} · {theme.esc(sg.get('speaker') or '')} · {theme.status_pill(sg.get('application_status') or sg.get('status') or 'suggested')}</span><br>"
                            f"{theme.esc(sg['text'][:600])}", unsafe_allow_html=True)
                if can_code and c2.button("Remove", key=f"rmap_{cid}_{sg['id']}"):
                    with common.guard("Removed"):
                        store.remove_application(u, cid, sg["id"])
                        st.rerun()
    with t2:
        if not can_code:
            st.info("Your role cannot code.")
        else:
            q = st.text_input("Find segments", placeholder="Search respondent text…")
            res = store.search_segments(u, pid, q)[:30]
            if res:
                sid = st.radio("Segment", [r["id"] for r in res], format_func={r["id"]: f"{r['segment_code']} · {r.get('speaker') or ''}: {r['text'][:140]}" for r in res}.get)
                seg = next(r for r in res if r["id"] == sid)
                st.markdown(theme.quote_html(seg["text"], f"{seg['segment_code']} · {seg.get('doc_type') or ''} · {seg.get('location') or ''}"), unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                existing = c1.multiselect("Apply existing codes", [c["id"] for c in codes], format_func={c["id"]: c["name"] for c in codes}.get, key="apply_ex")
                new = c2.text_input("…or create a new code")
                newdef = c2.text_input("Definition of the new code")
                if st.button("Apply codes", type="primary"):
                    with common.guard("Coded"):
                        ids = list(existing)
                        if new.strip():
                            ids.append(store.find_or_create_code(u, pid, new, newdef))
                        for c in ids:
                            store.apply_code(u, c, sid)
                        st.rerun()
    with t3:
        if not can_code or len(codes) < 2:
            st.caption("Needs at least two codes and coding permission.")
        else:
            st.markdown("**Merge codes**")
            src = st.multiselect("Codes to merge", [c["id"] for c in codes], format_func={c["id"]: c["name"] for c in codes}.get, key="m_src")
            tgt = st.selectbox("Into", [c["id"] for c in codes if c["id"] not in src], format_func={c["id"]: c["name"] for c in codes}.get, key="m_tgt")
            if st.button("Merge", disabled=not src):
                with common.guard("Merged; the source codes are kept as 'merged' for the audit trail"):
                    store.merge_codes(u, src, tgt)
                    st.rerun()
            st.divider()
            st.markdown("**Split a code**")
            sc = st.selectbox("Code to split", [c["id"] for c in codes], format_func={c["id"]: c["name"] for c in codes}.get, key="s_src")
            segs = store.code_segments(u, sc)
            move = st.multiselect("Segments to move to the new code", [x["id"] for x in segs], format_func={x["id"]: f"{x['segment_code']}: {x['text'][:90]}" for x in segs}.get)
            nn = st.text_input("New code name", key="s_new")
            nd = st.text_input("New code definition", key="s_def")
            if st.button("Split", disabled=not (move and nn.strip())):
                with common.guard("Split"):
                    store.split_code(u, sc, nn, move, nd)
                    st.rerun()
    with t4:
        vs = store.codebook_versions(u, pid)
        common.table(vs, {"version": "Version", "note": "Note", "n_codes": "Codes", "created_at": "Saved"})
        note = st.text_input("Snapshot note", placeholder="e.g. After second coding pass")
        if can_code and st.button("Save codebook snapshot", icon=":material/save:"):
            with common.guard("Snapshot saved"):
                store.snapshot_codebook(u, pid, note)
                st.rerun()


# ---------------------------------------------------------------- Themes & findings

def themes() -> None:
    u = common.cu()
    theme.page_header("Themes & Findings", "Themes, subthemes and the analyst's interpretation, kept separate from AI summaries and from verified evidence.", "network")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    can_code = common.can(u, "qual.code")
    ths = store.list_themes(u, pid)
    codes = store.list_codes(u, pid)
    cname = {c["id"]: c["name"] for c in codes}
    with st.expander("Create or edit a theme", icon=":material/add:", expanded=not ths):
        if not can_code:
            st.info("Your role cannot edit themes.")
        else:
            edit = st.selectbox("Theme", [None] + [t["id"] for t in ths], format_func=lambda i: "New theme" if i is None else next(t["name"] for t in ths if t["id"] == i))
            cur = next((t for t in ths if t["id"] == edit), {})
            name = st.text_input("Name", cur.get("name") or "")
            definition = st.text_area("Definition", cur.get("definition") or "")
            parents = [t["id"] for t in ths if not t.get("parent_id") and t["id"] != edit]
            parent = st.selectbox("Subtheme of (optional)", [None] + parents, index=([None] + parents).index(cur.get("parent_id")) if cur.get("parent_id") in parents else 0,
                                  format_func=lambda i: "—" if i is None else next(t["name"] for t in ths if t["id"] == i))
            cids = st.multiselect("Codes", list(cname), default=[c for c in cur.get("code_ids") or [] if c in cname], format_func=cname.get)
            expl = st.text_area("Analytical explanation (analyst)", cur.get("analytic_explanation") or "")
            lim = st.text_area("Limitations of the evidence", cur.get("limitations") or "")
            if st.button("Save theme", type="primary"):
                with common.guard("Theme saved"):
                    store.save_theme(u, pid, name, definition, cids, parent, edit, analytic_explanation=expl, limitations=lim)
                    st.rerun()
    if not ths:
        theme.empty_state("No themes yet", "Create themes manually or run AI coding with axial grouping.", "network")
        return
    tid = st.selectbox("Open theme", [t["id"] for t in ths], format_func={t["id"]: ("↳ " if t.get("parent_id") else "") + f"{t['name']} ({t['status']})" for t in ths}.get)
    t = next(x for x in ths if x["id"] == tid)
    ev = store.theme_evidence(u, tid)
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"### {theme.esc(t['name'])} {theme.status_pill(t['status'])}", unsafe_allow_html=True)
    c1.caption(t.get("definition") or "No definition yet.")
    if can_code and t["status"] == "suggested":
        a1, a2 = c2.columns(2)
        if a1.button("Approve", key="th_ap"):
            with common.guard("Approved"):
                store.review_theme(u, tid, True)
                st.rerun()
        if a2.button("Reject", key="th_rj"):
            with common.guard("Rejected"):
                store.review_theme(u, tid, False)
                st.rerun()
    theme.kpi_row([("Documents", ev["n_documents"], "containing coded evidence", "file-text"), ("Segments", ev["n_segments"], "coded", "rows-3"),
                   ("Speaker labels", ev["n_identified_speakers"], "distinct, within documents", "users"),
                   ("Approved quotes", len(store.quotes_for_theme(u, tid)), "verified and approved", "quote")])
    st.caption(ev.get("counting_note") or "")
    tabs = st.tabs(["Evidence", "Separated outputs", "Add analyst note"])
    with tabs[0]:
        c1, c2, c3 = st.columns(3)
        for col, key, label in ((c1, "by_doc_type", "By document type"), (c2, "by_location", "By location"), (c3, "by_group", "By respondent group")):
            col.markdown(f"**{label}**")
            col.dataframe(pd.DataFrame(list(ev[key].items()), columns=["", "documents"]), hide_index=True, width="stretch")
        for sg in ev["segments"][:40]:
            st.markdown(theme.quote_html(sg["text"][:700], f"{sg['segment_code']} · {sg.get('speaker') or ''} · {sg.get('doc_type') or ''} · {sg.get('location') or ''}",
                                         "coded segment (not yet a verified quotation)"), unsafe_allow_html=True)
    with tabs[1]:
        st.caption("Lucerna keeps these categories apart. AI summaries stay drafts until an analyst approves them; only approved items reach reports.")
        notes = store.list_notes(u, pid, theme_id=tid)
        if not notes:
            st.caption("No notes for this theme yet.")
        for n in notes:
            with st.container(border=True):
                c1, c2 = st.columns([6, 2])
                origin = theme.pill("AI draft" if n["origin"] == "ai" else "Analyst", "violet" if n["origin"] == "ai" else "teal")
                c1.markdown(f"{theme.pill(NOTE_KINDS.get(n['kind'], n['kind']), 'info')} {origin} {theme.status_pill(n['status'])}", unsafe_allow_html=True)
                txt = c1.text_area("Text", n["text"], key=f"nt_{n['id']}", label_visibility="collapsed", disabled=not can_code)
                if n["segment_ids"]:
                    c1.caption(f"Supported by {len(n['segment_ids'])} segment(s).")
                if can_code:
                    if c2.button("Approve", key=f"na_{n['id']}", width="stretch"):
                        with common.guard("Approved"):
                            store.review_note(u, n["id"], "approved", txt)
                            st.rerun()
                    if c2.button("Exclude", key=f"nx_{n['id']}", width="stretch"):
                        with common.guard("Excluded"):
                            store.review_note(u, n["id"], "excluded")
                            st.rerun()
    with tabs[2]:
        if can_code:
            kinds = [k for k in NOTE_KINDS if k != "ai_summary"]
            kind = st.selectbox("Type", kinds, format_func=NOTE_KINDS.get)
            text = st.text_area("Text")
            pr = st.selectbox("Priority (recommendations)", [None, "High", "Medium", "Low"], format_func=lambda x: x or "—") if "recommendation" in kind else None
            stake = st.text_input("Responsible stakeholder") if "recommendation" in kind else None
            segs = st.multiselect("Supporting segments", [s["id"] for s in ev["segments"]], format_func={s["id"]: f"{s['segment_code']}: {s['text'][:80]}" for s in ev["segments"]}.get)
            if st.button("Add note", type="primary"):
                with common.guard("Added"):
                    store.add_note(u, pid, kind, text, theme_id=tid, segment_ids=segs, priority=pr, stakeholder=stake)
                    st.rerun()


# ---------------------------------------------------------------- Quotations

def quotations() -> None:
    u = common.cu()
    theme.page_header("Quotations & Evidence", "Every quotation is checked character-by-character against the stored source. Only verified quotations can be approved for reports.", "quote")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    can_r = common.can(u, "quote.review")
    s = store.project_summary(u, pid)
    theme.kpi_row([("Verified", s["quotes_verified"], "exact match with source", "circle-check", "#0ca30c"), ("Approved", s["quotes_approved"], "ready for reports", "badge-check"),
                   ("Manual review", s["quotes_manual"], "OCR or wrong segment", "triangle-alert", "#B7791F"), ("Rejected", s["quotes_rejected"], "not found in source", "circle-x", "#d03b3b")])
    st.write("")
    ths = store.list_themes(u, pid)
    tname = {t["id"]: t["name"] for t in ths}
    t1, t2, t3, t4 = st.tabs(["Review", "Manual review queue", "Rejected (audit)", "Add a quotation"])
    with t1:
        rows = store.list_quotations(u, pid, "verified")
        if not rows:
            st.caption("No verified quotations yet.")
        flt = st.segmented_control("Decision", ["pending", "approved", "excluded"], default="pending", key="qdec")
        for q in [r for r in rows if r["analyst_decision"] == flt][:60]:
            with st.container(border=True):
                src = f"{q['segment_code']} · {q.get('speaker') or ''} · {q.get('doc_type') or ''} · {q.get('location') or ''} · {q.get('respondent_group') or ''}"
                st.markdown(theme.quote_html(q["verified_text"], src, f"verified ({q['verification_method']})"), unsafe_allow_html=True)
                if q.get("translation_text"):
                    st.caption(f"Translation ({q['translation_language']}, by {q['translation_by']}): {q['translation_text']}")
                if can_r:
                    c = st.columns([1, 1, 2, 3])
                    if c[0].button("Approve", key=f"qa_{q['id']}", type="primary"):
                        with common.guard("Approved"):
                            store.decide_quotation(u, q["id"], "approved")
                            st.rerun()
                    if c[1].button("Exclude", key=f"qx_{q['id']}"):
                        with common.guard("Excluded"):
                            store.decide_quotation(u, q["id"], "excluded")
                            st.rerun()
                    if ths:
                        ti = c[2].selectbox("Theme", [None] + list(tname), index=([None] + list(tname)).index(q.get("theme_id")) if q.get("theme_id") in tname else 0,
                                            format_func=lambda i: "— theme —" if i is None else tname[i], key=f"qt_{q['id']}", label_visibility="collapsed")
                        if ti != q.get("theme_id"):
                            with common.guard():
                                store.assign_quotation(u, q["id"], theme_id=ti)
                                st.rerun()
                    with c[3].popover("Translation"):
                        tt = st.text_area("Translated text", q.get("translation_text") or "", key=f"tr_{q['id']}")
                        tl = st.text_input("Language", q.get("translation_language") or "English", key=f"tl_{q['id']}")
                        tb = st.text_input("Translator", q.get("translation_by") or u.full_name or u.username, key=f"tb_{q['id']}")
                        if st.button("Save translation", key=f"ts_{q['id']}"):
                            with common.guard("Saved; the original-language text remains the verified evidence"):
                                store.set_translation(u, q["id"], tt, tl, tb)
    with t2:
        rows = store.list_quotations(u, pid, "manual_review")
        if not rows:
            st.caption("Nothing waiting for manual review.")
        for q in rows:
            with st.container(border=True):
                st.markdown(f"**Candidate:** “{theme.esc(q['candidate_text'])}”  \n<span class='lc-muted'>Claimed segment: {theme.esc(q.get('claimed_segment_code') or '—')} · "
                            f"Reason: {theme.esc(q.get('rejection_reason') or '')}</span>", unsafe_allow_html=True)
                if can_r:
                    qs = store.search_segments(u, pid, " ".join(q["candidate_text"].split()[:4]))[:10] or store.search_segments(u, pid, "")[:10]
                    sid = st.selectbox("Correct segment", [x["id"] for x in qs], format_func={x["id"]: f"{x['segment_code']}: {x['text'][:100]}" for x in qs}.get, key=f"mr_s_{q['id']}")
                    seg = next(x for x in qs if x["id"] == sid)
                    st.caption(seg["text"][:1200])
                    txt = st.text_area("Exact text as it appears in the source", q["candidate_text"], key=f"mr_t_{q['id']}")
                    c1, c2 = st.columns(2)
                    if c1.button("Verify against this segment", key=f"mr_v_{q['id']}", type="primary"):
                        with common.guard():
                            r = store.confirm_manual_review(u, q["id"], sid, txt)
                            st.success(f"Verified ({r['method']}).")
                            st.rerun()
                    if c2.button("Exclude", key=f"mr_x_{q['id']}"):
                        with common.guard("Excluded"):
                            store.decide_quotation(u, q["id"], "excluded")
                            st.rerun()
    with t3:
        rows = store.list_quotations(u, pid, "rejected")
        st.caption("Rejected candidates are kept for transparency and never appear in reports.")
        common.table(rows, {"candidate_text": "Candidate text", "claimed_segment_code": "Claimed segment", "rejection_reason": "Reason", "origin": "Origin"})
    with t4:
        if can_r:
            st.caption("Paste a passage and choose the segment it comes from. Lucerna verifies it; it is stored only as verified, manual review or rejected.")
            q = st.text_input("Search segments", key="aq_q")
            res = store.search_segments(u, pid, q)[:25]
            if res:
                sid = st.selectbox("Segment", [r["id"] for r in res], format_func={r["id"]: f"{r['segment_code']} · {r.get('speaker') or ''}: {r['text'][:110]}" for r in res}.get)
                st.caption(next(r for r in res if r["id"] == sid)["text"])
                txt = st.text_area("Quotation")
                ti = st.selectbox("Theme (optional)", [None] + list(tname), format_func=lambda i: "—" if i is None else tname[i], key="aq_t")
                if st.button("Verify and add", type="primary"):
                    with common.guard():
                        r = store.add_quotation(u, pid, txt, segment_id=sid, theme_id=ti)
                        (st.success if r["status"] == "verified" else st.warning)(f"Result: {r['status']} — {r.get('reason') or r.get('method')}")


# ---------------------------------------------------------------- Evidence Q&A

def evidence_qa() -> None:
    u = common.cu()
    theme.page_header("Evidence Q&A", "Ask a question; the local model answers only from retrieved segments and cites them. Quotes in the answer are verified like any other.", "messages-square")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    q = st.text_area("Question", placeholder="e.g. What barriers to accessing cash assistance did women describe?")
    if st.button("Ask", type="primary", disabled=not (q.strip() and common.can(u, "ai.use"))):
        with common.guard():
            st.session_state["job_qa"] = jobs.submit("evidence_qa", {"project_id": pid, "user_id": u.id, "question": q}, project_id=pid, user_id=u.id)
            st.rerun()
    common.job_panel("job_qa")
    jid = st.session_state.get("job_qa") or st.session_state.get("job_qa_handled")
    j = jobs.get(jid) if jid else None
    if j and j["status"] == "completed" and j.get("result"):
        r = j["result"]
        with st.container(border=True):
            st.markdown(f"{theme.pill('AI-generated answer', 'violet')}", unsafe_allow_html=True)
            st.markdown(theme.esc(r["answer"]))
            st.caption(r["note"])
            if r["citations"]:
                st.caption("Cited segments: " + ", ".join(r["citations"]))
            if r["invalid_citations"]:
                st.warning("The model cited segment IDs that do not exist; they were discarded: " + ", ".join(map(str, r["invalid_citations"])))
            for qq in r["quotes"]:
                if qq["status"] == "verified":
                    st.markdown(theme.quote_html(qq["text"], qq["segment_code"], "verified"), unsafe_allow_html=True)
                else:
                    st.caption(f"Quote not shown ({qq['status']}): {qq.get('reason')}")
