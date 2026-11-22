"""AI-assisted qualitative pipeline (background job).

open coding (per batch, checkpointed) → quotation verification → axial themes → theme analysis.
Everything the model proposes is stored as 'suggested'/'draft' for analyst review; quotations go
through strict verification; segment ids that do not exist are discarded and counted.
"""
from __future__ import annotations

import json

from .. import db
from ..ai import prompts, providers
from ..security import audit
from ..security.rbac import CurrentUser
from ..services import jobs
from . import store


def _validate_open(obj: dict) -> None:
    if not isinstance(obj.get("codes", []), list) or not isinstance(obj.get("quotes", []), list):
        raise ValueError("'codes' and 'quotes' must be lists")
    for c in obj.get("codes", []):
        if not isinstance(c, dict) or not str(c.get("code", "")).strip() or not isinstance(c.get("segment_ids", []), list):
            raise ValueError("each code needs 'code' and a 'segment_ids' list")


def _validate_axial(obj: dict) -> None:
    if not isinstance(obj.get("themes"), list):
        raise ValueError("'themes' must be a list")
    for t in obj["themes"]:
        if not isinstance(t, dict) or not str(t.get("theme", "")).strip() or not isinstance(t.get("codes", []), list):
            raise ValueError("each theme needs 'theme' and a 'codes' list")


def _validate_theme_analysis(obj: dict) -> None:
    if not isinstance(obj.get("explanation", ""), str):
        raise ValueError("'explanation' must be text")


def _user(uid: int) -> CurrentUser:
    from ..security import auth
    return auth.to_current(auth.get_user_by_id(uid))


@jobs.register("qual_ai_coding")
def run_ai_coding(ctx: jobs.JobContext, project_id: int, user_id: int, document_ids: list[int] | None = None,
                  run_axial: bool = True, run_theme_analysis: bool = True) -> dict:
    user = _user(user_id)
    proj = db.query_one("SELECT classification FROM projects WHERE id=?", (project_id,))
    cls = proj["classification"] if proj else None
    from ..config import settings
    batch_size = max(1, settings().llm_batch)

    ctx.update("Preparing data", 0.02, "Loading segments")
    all_segs = store.project_segments(user, project_id)
    if document_ids:
        all_segs = [s for s in all_segs if s["document_id"] in set(document_ids)]
    # moderator question preceding each respondent turn is supplied as context (never quotable)
    context, last_q = {}, {}
    for s in all_segs:
        if s["speaker_role"] == "moderator":
            last_q[s["document_id"]] = s["text"]
        else:
            context[s["id"]] = last_q.get(s["document_id"], "")
    targets = [s for s in all_segs if s["speaker_role"] in ("respondent", "unknown")]
    by_code = {s["segment_code"]: s for s in all_segs}
    ck = ctx.load_checkpoint({"done": 0, "stats": {"codes": 0, "applications": 0, "quotes_verified": 0, "quotes_rejected": 0,
                                                   "quotes_manual": 0, "invalid_segment_refs": 0, "failed_batches": 0, "warnings": []}})
    st = ck["stats"]
    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    for bi in range(ck["done"], len(batches)):
        batch = batches[bi]
        ctx.update("Running analysis", 0.05 + 0.6 * bi / max(1, len(batches)), f"Open coding batch {bi + 1} of {len(batches)}")
        existing = [c["name"] for c in store.list_codes(user, project_id) if c["status"] == "approved"][:60]
        payload = [{"segment_id": s["segment_code"], "speaker": s.get("speaker") or "unknown", "context": context.get(s["id"], "")[:400], "text": s["text"]} for s in batch]
        name, version, tmpl = prompts.OPEN_CODING
        try:
            obj = providers.chat_json([{"role": "system", "content": prompts.SYSTEM_QUAL},
                                       {"role": "user", "content": tmpl.format(existing_codes=json.dumps(existing, ensure_ascii=False),
                                                                               segments=json.dumps(payload, ensure_ascii=False, indent=1))}],
                                      prompt_name=name, prompt_version=version, project_id=project_id, classification=cls, job_id=ctx.job_id,
                                      validator=_validate_open)
        except providers.PrivacyBlocked:
            raise
        except providers.AIError as exc:
            st["failed_batches"] += 1
            st["warnings"].append(f"Batch {bi + 1}: {exc}")
            if st["failed_batches"] >= 3 and st["failed_batches"] == bi + 1:
                raise providers.AIError(f"The first {st['failed_batches']} batches all failed; stopping. Last error: {exc}")
            ck["done"] = bi + 1
            ctx.save_checkpoint(ck)
            continue
        allowed = {s["segment_code"] for s in batch}
        name_to_id = {}
        for c in obj.get("codes", []):
            refs = [r for r in c.get("segment_ids", []) if r in allowed]
            st["invalid_segment_refs"] += len(c.get("segment_ids", [])) - len(refs)
            if not refs:
                continue
            cid = store.find_or_create_code(user, project_id, c["code"], str(c.get("definition") or ""), "ai", version)
            name_to_id[c["code"].strip().lower()] = cid
            st["codes"] += 1
            for r in refs:
                store.apply_code(user, cid, by_code[r]["id"], origin="ai")
                st["applications"] += 1
        ctx.update("Verifying evidence", None, f"Verifying quotations from batch {bi + 1}")
        for q in obj.get("quotes", []):
            if not isinstance(q, dict):
                continue
            ref = str(q.get("segment_id") or "")
            res = store.add_quotation(user, project_id, str(q.get("quote") or ""), segment_code=ref if ref in by_code else f"__invalid__{ref}",
                                      code_id=name_to_id.get(str(q.get("code") or "").strip().lower()), origin="ai")
            st[{"verified": "quotes_verified", "rejected": "quotes_rejected", "manual_review": "quotes_manual"}[res["status"]]] += 1
        ck["done"] = bi + 1
        ctx.save_checkpoint(ck)

    if st["failed_batches"] == len(batches) and batches:
        raise providers.AIError("Every coding batch failed. " + (st["warnings"][-1] if st["warnings"] else ""))

    if run_axial:
        ctx.update("Running analysis", 0.7, "Axial coding: grouping codes into themes")
        codes = store.list_codes(user, project_id)
        if codes:
            name, version, tmpl = prompts.AXIAL_CODING
            listing = "\n".join(f"- {c['name']} — {c.get('definition') or ''} — {c['n_segments']}" for c in codes[:150])
            try:
                obj = providers.chat_json([{"role": "system", "content": prompts.SYSTEM_QUAL}, {"role": "user", "content": tmpl.format(codes=listing)}],
                                          prompt_name=name, prompt_version=version, project_id=project_id, classification=cls, job_id=ctx.job_id,
                                          validator=_validate_axial)
                lookup = {c["name"].lower(): c["id"] for c in codes}
                for t in obj["themes"]:
                    ids = [lookup[str(x).strip().lower()] for x in t.get("codes", []) if str(x).strip().lower() in lookup]
                    if not ids:
                        continue
                    tid = store.save_theme(user, project_id, t["theme"], str(t.get("definition") or ""), ids, origin="ai")
                    for sub in t.get("subthemes") or []:
                        sids = [lookup[str(x).strip().lower()] for x in (sub.get("codes") or []) if str(x).strip().lower() in lookup]
                        if sids and str(sub.get("theme", "")).strip():
                            store.save_theme(user, project_id, sub["theme"], str(sub.get("definition") or ""), sids, parent_id=tid, origin="ai")
                    st.setdefault("themes", 0)
                    st["themes"] += 1
            except providers.AIError as exc:
                st["warnings"].append(f"Axial coding failed: {exc}. Codes remain available; group them manually in Themes.")

    if run_theme_analysis:
        themes = [t for t in store.list_themes(user, project_id) if t["parent_id"] is None]
        for i, t in enumerate(themes):
            ctx.update("Running analysis", 0.75 + 0.2 * i / max(1, len(themes)), f"Analysing theme {i + 1} of {len(themes)}")
            ev = store.theme_evidence(user, t["id"])
            if not ev["segments"]:
                continue
            seg_lookup = {s["segment_code"]: s["id"] for s in ev["segments"]}
            lines = "\n".join(f"[{s['segment_code']}] ({s['document_code']}, {s.get('doc_type') or ''}, {s.get('speaker') or 'unknown speaker'}) {s['text'][:700]}"
                              for s in ev["segments"][:40])
            name, version, tmpl = prompts.THEME_ANALYSIS
            try:
                obj = providers.chat_json([{"role": "system", "content": prompts.SYSTEM_QUAL},
                                           {"role": "user", "content": tmpl.format(theme=t["name"], definition=t.get("definition") or "", segments=lines)}],
                                          prompt_name=name, prompt_version=version, project_id=project_id, classification=cls, job_id=ctx.job_id,
                                          validator=_validate_theme_analysis)
            except providers.AIError as exc:
                st["warnings"].append(f"Theme analysis for '{t['name']}' failed: {exc}")
                continue

            def ids(lst):
                return [seg_lookup[x] for x in (lst or []) if x in seg_lookup]
            if obj.get("explanation") and ids(obj.get("explanation_segment_ids")):
                store.add_note(user, project_id, "ai_summary", obj["explanation"], theme_id=t["id"], origin="ai", segment_ids=ids(obj.get("explanation_segment_ids")))
            for kind, key in (("contradiction", "contradictions"), ("negative_case", "negative_cases"), ("community_recommendation", "community_recommendations")):
                for item in obj.get(key) or []:
                    if isinstance(item, dict) and item.get("text") and ids(item.get("segment_ids")):
                        store.add_note(user, project_id, kind, item["text"], theme_id=t["id"], origin="ai", segment_ids=ids(item.get("segment_ids")))
            for gap in obj.get("evidence_gaps") or []:
                if isinstance(gap, str) and gap.strip():
                    store.add_note(user, project_id, "evidence_gap", gap, theme_id=t["id"], origin="ai")
    db.execute("UPDATE qual_documents SET status='coded' WHERE project_id=?", (project_id,))
    audit.log(user.username, "QUAL_AI_CODING_COMPLETED", json.dumps({k: v for k, v in st.items() if k != "warnings"}), project_id=project_id)
    return st


@jobs.register("evidence_qa")
def run_evidence_qa(ctx: jobs.JobContext, project_id: int, user_id: int, question: str) -> dict:
    user = _user(user_id)
    proj = db.query_one("SELECT classification FROM projects WHERE id=?", (project_id,))
    terms = [w.lower() for w in question.split() if len(w) > 3]
    segs = store.project_segments(user, project_id, ("respondent", "unknown"))
    scored = sorted(segs, key=lambda s: -sum(s["text"].lower().count(t) for t in terms))[:12]
    name, version, tmpl = prompts.EVIDENCE_QA
    ctx.update("Running analysis", 0.3, "Asking the local model")
    obj = providers.chat_json([{"role": "system", "content": prompts.SYSTEM_QUAL},
                               {"role": "user", "content": tmpl.format(question=question, segments="\n".join(f"[{s['segment_code']}] {s['text']}" for s in scored))}],
                              prompt_name=name, prompt_version=version, project_id=project_id, classification=proj["classification"], job_id=ctx.job_id)
    valid = {s["segment_code"]: s for s in scored}
    from . import verify
    quotes = []
    for q in obj.get("quotes") or []:
        s = valid.get(str(q.get("segment_id")))
        if s:
            r = verify.verify_against_segment(str(q.get("quote") or ""), s["text"], s["speaker_role"], bool(s["requires_verification"]))
            quotes.append({"segment_code": s["segment_code"], "status": r.status, "text": r.verified_text, "candidate": q.get("quote"), "reason": r.reason})
    return {"answer": str(obj.get("answer") or ""), "citations": [c for c in obj.get("segment_ids") or [] if c in valid],
            "invalid_citations": [c for c in obj.get("segment_ids") or [] if c not in valid], "quotes": quotes,
            "note": "AI-generated answer from retrieved segments. Only quotations marked 'verified' are exact source text."}
