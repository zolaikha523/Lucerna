"""Qualitative service layer: documents, segments, codebook, themes, quotations, analytic notes."""
from __future__ import annotations

import hashlib

from .. import db
from ..security import audit
from ..security.rbac import CurrentUser, PermissionDenied, require
from ..services import files
from . import extract, pii, segment, verify

DOC_TYPES = ["FGD", "KII", "Individual interview", "Open-ended survey responses", "Community consultation", "Field notes",
             "Observation report", "Assessment document", "Research report", "Other"]
NOTE_KINDS = {"ai_summary": "AI-generated summary", "interpretation": "Analytical interpretation", "researcher_conclusion": "Researcher conclusion",
              "contradiction": "Contradictory evidence", "negative_case": "Negative case", "evidence_gap": "Evidence gap",
              "recommendation": "Recommendation", "community_recommendation": "Recommendation voiced by respondents",
              "limitation": "Limitation", "cross_cutting": "Cross-cutting finding", "mixed_methods": "Mixed-methods finding"}


class QualError(Exception):
    pass


# ------------------------------------------------------------------ documents

def _next_code(project_id: int) -> str:
    n = db.query_one("SELECT COUNT(*) n FROM qual_documents WHERE project_id=?", (project_id,))["n"]
    while True:
        n += 1
        code = f"DOC-{n:03d}"
        if not db.query_one("SELECT 1 FROM qual_documents WHERE project_id=? AND document_code=?", (project_id, code)):
            return code


def import_document(user: CurrentUser, project_id: int, filename: str, data: bytes, meta: dict | None = None) -> int:
    require(user, "data.upload", project_id)
    f = files.store_upload(user, project_id, filename, data, "qualitative")
    ex = extract.extract(data, filename)
    segs = segment.segment(ex)
    suggested = segment.header_metadata(ex)
    meta = {k: v for k, v in (meta or {}).items() if v}
    # values written in the transcript header (e.g. "Location: Herat City") fill fields the user left empty;
    # they remain editable in Documents › Metadata
    for field, keys in (("location", ("location", "district", "province", "village")), ("collection_date", ("date", "collection date")),
                        ("respondent_group", ("group", "respondent group", "participants")), ("language", ("language",))):
        if not meta.get(field):
            val = next((suggested.get(k) for k in keys if suggested.get(k)), None)
            if val:
                meta[field] = str(val)[:120]
    doc_type = meta.get("doc_type") or _match_type(suggested.get("type") or suggested.get("interview type") or filename)
    pii_hits = len(pii.detect(ex.full_text))
    with db.transaction() as con:
        code = _next_code(project_id)
        cur = con.execute(
            "INSERT INTO qual_documents(project_id, data_file_id, document_code, title, original_name, doc_type, location, collection_date, respondent_group,"
            " language, metadata_json, extraction_method, requires_verification, full_text, text_sha256, char_count, page_count, created_by, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, f["id"], code, meta.get("title") or suggested.get("title") or filename, f["original_name"], doc_type,
             meta.get("location"), meta.get("collection_date"), meta.get("respondent_group"), meta.get("language"),
             db.dumps({"suggested_from_header": suggested, "extraction_notes": ex.notes, "pii_patterns_detected": pii_hits}),
             ex.method, int(ex.requires_verification), ex.full_text, hashlib.sha256(ex.full_text.encode()).hexdigest(),
             len(ex.full_text), ex.page_count, user.id, db.now()))
        did = cur.lastrowid
        for s in segs:
            con.execute("INSERT INTO qual_segments(document_id, segment_code, seq, page, paragraph, speaker, speaker_role, start_char, end_char, text)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (did, f"{code}-S{s.seq:04d}", s.seq, s.page, s.paragraph, s.speaker, s.speaker_role, s.start, s.end, s.text))
    audit.log(user.username, "QUAL_DOCUMENT_IMPORTED", f"{code}: {len(segs)} segments, method={ex.method}", project_id=project_id,
              object_type="qual_document", object_id=did)
    return did


def _match_type(s: str) -> str:
    low = (s or "").lower()
    if "fgd" in low or "focus group" in low:
        return "FGD"
    if "kii" in low or "key informant" in low:
        return "KII"
    if "interview" in low:
        return "Individual interview"
    return "Other"


def list_documents(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT d.id, d.document_code, d.title, d.original_name, d.doc_type, d.location, d.collection_date, d.respondent_group, d.language,"
                    " d.extraction_method, d.requires_verification, d.char_count, d.page_count, d.status, d.created_at,"
                    " (SELECT COUNT(*) FROM qual_segments s WHERE s.document_id=d.id) AS n_segments FROM qual_documents d WHERE project_id=? ORDER BY document_code", (project_id,))


def get_document(user: CurrentUser, document_id: int) -> dict:
    d = db.query_one("SELECT * FROM qual_documents WHERE id=?", (document_id,))
    if not d:
        raise QualError("Document not found.")
    require(user, "project.view", d["project_id"])
    d["metadata"] = db.loads(d.get("metadata_json"), {})
    return d


def update_document(user: CurrentUser, document_id: int, **fields) -> None:
    d = get_document(user, document_id)
    require(user, "qual.code", d["project_id"])
    allowed = ("title", "doc_type", "location", "collection_date", "respondent_group", "language")
    vals = {k: (v or None) for k, v in fields.items() if k in allowed}
    if vals:
        db.execute(f"UPDATE qual_documents SET {', '.join(f'{k}=?' for k in vals)} WHERE id=?", (*vals.values(), document_id))
        audit.log(user.username, "QUAL_DOCUMENT_METADATA", ", ".join(vals), project_id=d["project_id"], object_type="qual_document", object_id=document_id)


def segments(user: CurrentUser, document_id: int) -> list[dict]:
    get_document(user, document_id)
    return db.query("SELECT * FROM qual_segments WHERE document_id=? ORDER BY seq", (document_id,))


def project_segments(user: CurrentUser, project_id: int, roles: tuple[str, ...] | None = None) -> list[dict]:
    require(user, "project.view", project_id)
    rows = db.query("SELECT s.*, d.document_code, d.doc_type, d.location, d.respondent_group, d.requires_verification, d.title AS document_title"
                    " FROM qual_segments s JOIN qual_documents d ON d.id=s.document_id WHERE d.project_id=? ORDER BY d.document_code, s.seq", (project_id,))
    return [r for r in rows if not roles or r["speaker_role"] in roles]


def search_segments(user: CurrentUser, project_id: int, query: str, respondents_only: bool = True) -> list[dict]:
    q = (query or "").strip().lower()
    rows = project_segments(user, project_id, ("respondent", "unknown") if respondents_only else None)
    return [r for r in rows if q in r["text"].lower()] if q else rows


def delete_document(user: CurrentUser, document_id: int) -> None:
    d = get_document(user, document_id)
    require(user, "data.delete", d["project_id"])
    db.execute("DELETE FROM qual_documents WHERE id=?", (document_id,))
    audit.log(user.username, "QUAL_DOCUMENT_DELETED", d["document_code"], "WARNING", project_id=d["project_id"])


# ------------------------------------------------------------------ codes

def _code(code_id: int) -> dict:
    c = db.query_one("SELECT * FROM codes WHERE id=?", (code_id,))
    if not c:
        raise QualError("Code not found.")
    return c


def list_codes(user: CurrentUser, project_id: int, include_rejected: bool = False) -> list[dict]:
    require(user, "project.view", project_id)
    rows = db.query("SELECT c.*, (SELECT COUNT(*) FROM code_applications a WHERE a.code_id=c.id AND a.status<>'rejected') AS n_segments,"
                    " (SELECT COUNT(DISTINCT s.document_id) FROM code_applications a JOIN qual_segments s ON s.id=a.segment_id WHERE a.code_id=c.id AND a.status<>'rejected') AS n_documents"
                    " FROM codes c WHERE c.project_id=? ORDER BY c.status='rejected', c.name", (project_id,))
    return [r for r in rows if include_rejected or r["status"] not in ("rejected", "merged")]


def find_or_create_code(user: CurrentUser, project_id: int, name: str, definition: str = "", origin: str = "manual",
                        prompt_version: str | None = None) -> int:
    require(user, "qual.code", project_id)
    name = " ".join((name or "").split())[:120]
    if not name:
        raise QualError("Code name is required.")
    ex = db.query_one("SELECT id, status, merged_into FROM codes WHERE project_id=? AND lower(name)=lower(?)", (project_id, name))
    if ex:
        return ex["merged_into"] or ex["id"]
    status = "approved" if origin == "manual" else "suggested"
    cid = db.execute("INSERT INTO codes(project_id, name, definition, origin, status, prompt_version, created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (project_id, name, definition, origin, status, prompt_version, user.id, db.now(), db.now()))
    audit.log(user.username, "CODE_CREATED", f"{origin}: {name}", project_id=project_id, object_type="code", object_id=cid)
    return cid


def update_code(user: CurrentUser, code_id: int, *, name: str | None = None, definition: str | None = None, category: str | None = None) -> None:
    c = _code(code_id)
    require(user, "qual.code", c["project_id"])
    db.execute("UPDATE codes SET name=COALESCE(?, name), definition=COALESCE(?, definition), category=COALESCE(?, category), updated_at=? WHERE id=?",
               (name, definition, category, db.now(), code_id))
    audit.log(user.username, "CODE_EDITED", f"#{code_id}", project_id=c["project_id"], object_type="code", object_id=code_id)


def review_code(user: CurrentUser, code_id: int, approve: bool) -> None:
    c = _code(code_id)
    require(user, "qual.code", c["project_id"])
    db.execute("UPDATE codes SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?", ("approved" if approve else "rejected", user.id, db.now(), code_id))
    if approve:
        db.execute("UPDATE code_applications SET status='approved' WHERE code_id=? AND status='suggested'", (code_id,))
    audit.log(user.username, "CODE_APPROVED" if approve else "CODE_REJECTED", c["name"], project_id=c["project_id"], object_type="code", object_id=code_id)


def merge_codes(user: CurrentUser, source_ids: list[int], target_id: int) -> None:
    t = _code(target_id)
    require(user, "qual.code", t["project_id"])
    with db.transaction() as con:
        for sid in source_ids:
            if sid == target_id:
                continue
            s = con.execute("SELECT project_id FROM codes WHERE id=?", (sid,)).fetchone()
            if not s or s["project_id"] != t["project_id"]:
                raise PermissionDenied("Codes must belong to the same project.")
            for a in con.execute("SELECT * FROM code_applications WHERE code_id=?", (sid,)).fetchall():
                con.execute("INSERT OR IGNORE INTO code_applications(code_id, segment_id, origin, status, created_by, created_at) VALUES(?,?,?,?,?,?)",
                            (target_id, a["segment_id"], a["origin"], a["status"], a["created_by"], a["created_at"]))
            con.execute("DELETE FROM code_applications WHERE code_id=?", (sid,))
            con.execute("UPDATE quotations SET code_id=? WHERE code_id=?", (target_id, sid))
            con.execute("INSERT OR IGNORE INTO theme_codes(theme_id, code_id) SELECT theme_id, ? FROM theme_codes WHERE code_id=?", (target_id, sid))
            con.execute("DELETE FROM theme_codes WHERE code_id=?", (sid,))
            con.execute("UPDATE codes SET status='merged', merged_into=?, updated_at=? WHERE id=?", (target_id, db.now(), sid))
    audit.log(user.username, "CODES_MERGED", f"{source_ids} -> {target_id}", project_id=t["project_id"], object_type="code", object_id=target_id)


def split_code(user: CurrentUser, code_id: int, new_name: str, segment_ids: list[int], definition: str = "") -> int:
    c = _code(code_id)
    require(user, "qual.code", c["project_id"])
    nid = find_or_create_code(user, c["project_id"], new_name, definition, "manual")
    with db.transaction() as con:
        for sid in segment_ids:
            con.execute("UPDATE OR IGNORE code_applications SET code_id=? WHERE code_id=? AND segment_id=?", (nid, code_id, sid))
            con.execute("DELETE FROM code_applications WHERE code_id=? AND segment_id=?", (code_id, sid))
            con.execute("UPDATE quotations SET code_id=? WHERE code_id=? AND segment_id=?", (nid, code_id, sid))
    audit.log(user.username, "CODE_SPLIT", f"#{code_id} -> #{nid} ({len(segment_ids)} segments)", project_id=c["project_id"], object_type="code", object_id=nid)
    return nid


def apply_code(user: CurrentUser, code_id: int, segment_id: int, origin: str = "manual") -> None:
    c = _code(code_id)
    require(user, "qual.code", c["project_id"])
    seg = db.query_one("SELECT d.project_id FROM qual_segments s JOIN qual_documents d ON d.id=s.document_id WHERE s.id=?", (segment_id,))
    if not seg or seg["project_id"] != c["project_id"]:
        raise PermissionDenied("Segment does not belong to this project.")
    db.execute("INSERT OR IGNORE INTO code_applications(code_id, segment_id, origin, status, created_by, created_at) VALUES(?,?,?,?,?,?)",
               (code_id, segment_id, origin, "approved" if origin == "manual" else "suggested", user.id, db.now()))


def remove_application(user: CurrentUser, code_id: int, segment_id: int) -> None:
    c = _code(code_id)
    require(user, "qual.code", c["project_id"])
    db.execute("UPDATE code_applications SET status='rejected' WHERE code_id=? AND segment_id=?", (code_id, segment_id))


def code_segments(user: CurrentUser, code_id: int) -> list[dict]:
    c = _code(code_id)
    require(user, "project.view", c["project_id"])
    return db.query("SELECT s.*, a.status AS application_status, a.origin AS application_origin, d.document_code, d.doc_type, d.location"
                    " FROM code_applications a JOIN qual_segments s ON s.id=a.segment_id JOIN qual_documents d ON d.id=s.document_id"
                    " WHERE a.code_id=? AND a.status<>'rejected' ORDER BY d.document_code, s.seq", (code_id,))


def snapshot_codebook(user: CurrentUser, project_id: int, note: str = "") -> int:
    require(user, "qual.code", project_id)
    codes = list_codes(user, project_id)
    themes = list_themes(user, project_id)
    v = (db.query_one("SELECT COALESCE(MAX(version),0) v FROM codebooks WHERE project_id=?", (project_id,))["v"]) + 1
    cid = db.execute("INSERT INTO codebooks(project_id, name, version, status, snapshot_json, note, created_by, created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (project_id, "Codebook", v, "snapshot", db.dumps({"codes": codes, "themes": themes}), note, user.id, db.now()))
    audit.log(user.username, "CODEBOOK_VERSION", f"v{v}", project_id=project_id, object_type="codebook", object_id=cid)
    return v


def codebook_versions(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT id, version, note, created_at FROM codebooks WHERE project_id=? ORDER BY version DESC", (project_id,))


# ------------------------------------------------------------------ themes

def list_themes(user: CurrentUser, project_id: int, include_rejected: bool = False) -> list[dict]:
    require(user, "project.view", project_id)
    rows = db.query("SELECT * FROM themes WHERE project_id=? ORDER BY parent_id IS NOT NULL, sort_order, name", (project_id,))
    for r in rows:
        r["code_ids"] = [x["code_id"] for x in db.query("SELECT code_id FROM theme_codes WHERE theme_id=?", (r["id"],))]
    return [r for r in rows if include_rejected or r["status"] != "rejected"]


def save_theme(user: CurrentUser, project_id: int, name: str, definition: str = "", code_ids: list[int] | None = None,
               parent_id: int | None = None, theme_id: int | None = None, origin: str = "manual", analytic_explanation: str | None = None,
               limitations: str | None = None) -> int:
    require(user, "qual.code", project_id)
    if not (name or "").strip():
        raise QualError("Theme name is required.")
    if theme_id:
        t = db.query_one("SELECT project_id FROM themes WHERE id=?", (theme_id,))
        if not t or t["project_id"] != project_id:
            raise PermissionDenied("Theme not in this project.")
        db.execute("UPDATE themes SET name=?, definition=?, parent_id=?, analytic_explanation=COALESCE(?, analytic_explanation), limitations=COALESCE(?, limitations), updated_at=? WHERE id=?",
                   (name.strip(), definition, parent_id, analytic_explanation, limitations, db.now(), theme_id))
        tid = theme_id
    else:
        tid = db.execute("INSERT INTO themes(project_id, parent_id, name, definition, analytic_explanation, limitations, origin, status, created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (project_id, parent_id, name.strip(), definition, analytic_explanation, limitations, origin, "approved" if origin == "manual" else "suggested", user.id, db.now(), db.now()))
    if code_ids is not None:
        valid = {r["id"] for r in db.query("SELECT id FROM codes WHERE project_id=?", (project_id,))}
        with db.transaction() as con:
            con.execute("DELETE FROM theme_codes WHERE theme_id=?", (tid,))
            for c in code_ids:
                if c in valid:
                    con.execute("INSERT OR IGNORE INTO theme_codes(theme_id, code_id) VALUES(?,?)", (tid, c))
    audit.log(user.username, "THEME_SAVED", name[:80], project_id=project_id, object_type="theme", object_id=tid)
    return tid


def review_theme(user: CurrentUser, theme_id: int, approve: bool) -> None:
    t = db.query_one("SELECT * FROM themes WHERE id=?", (theme_id,))
    require(user, "qual.code", t["project_id"])
    db.execute("UPDATE themes SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?", ("approved" if approve else "rejected", user.id, db.now(), theme_id))
    audit.log(user.username, "THEME_APPROVED" if approve else "THEME_REJECTED", t["name"][:80], project_id=t["project_id"], object_type="theme", object_id=theme_id)


def theme_evidence(user: CurrentUser, theme_id: int) -> dict:
    """Deterministic evidence profile for a theme (from non-rejected code applications)."""
    t = db.query_one("SELECT * FROM themes WHERE id=?", (theme_id,))
    require(user, "project.view", t["project_id"])
    sub_ids = [r["id"] for r in db.query("SELECT id FROM themes WHERE parent_id=?", (theme_id,))]
    code_ids = [r["code_id"] for r in db.query(f"SELECT code_id FROM theme_codes WHERE theme_id IN ({','.join('?' * (1 + len(sub_ids)))})", (theme_id, *sub_ids))]
    if not code_ids:
        return {"segments": [], "n_segments": 0, "n_documents": 0, "n_identified_speakers": 0, "by_doc_type": {}, "by_location": {}, "by_group": {}, "code_ids": []}
    marks = ",".join("?" * len(code_ids))
    segs = db.query(f"SELECT DISTINCT s.*, d.document_code, d.doc_type, d.location, d.respondent_group FROM code_applications a JOIN qual_segments s ON s.id=a.segment_id"
                    f" JOIN qual_documents d ON d.id=s.document_id WHERE a.code_id IN ({marks}) AND a.status<>'rejected' ORDER BY d.document_code, s.seq", code_ids)
    docs = {s["document_id"] for s in segs}
    speakers = {(s["document_id"], s["speaker"]) for s in segs if s.get("speaker")}
    by = lambda key: dict(sorted(((k, len({s["document_id"] for s in segs if (s.get(key) or "Not recorded") == k})) for k in {(s.get(key) or "Not recorded") for s in segs}), key=lambda x: -x[1]))
    return {"segments": segs, "n_segments": len(segs), "n_documents": len(docs), "n_identified_speakers": len(speakers),
            "by_doc_type": by("doc_type"), "by_location": by("location"), "by_group": by("respondent_group"), "code_ids": code_ids,
            "counting_note": "Counts are documents and distinct speaker labels within documents that contain coded evidence. They are not counts of people holding a view, and do not indicate prevalence."}


# ------------------------------------------------------------------ quotations

def add_quotation(user: CurrentUser, project_id: int, candidate: str, *, segment_id: int | None = None, segment_code: str | None = None,
                  code_id: int | None = None, theme_id: int | None = None, origin: str = "manual") -> dict:
    """Run strict verification and store the result (verified, manual_review or rejected)."""
    require(user, "quote.review" if origin == "manual" else "ai.use", project_id)
    seg = None
    if segment_id:
        seg = db.query_one("SELECT s.*, d.project_id, d.requires_verification FROM qual_segments s JOIN qual_documents d ON d.id=s.document_id WHERE s.id=?", (segment_id,))
    elif segment_code:
        seg = db.query_one("SELECT s.*, d.project_id, d.requires_verification FROM qual_segments s JOIN qual_documents d ON d.id=s.document_id"
                           " WHERE s.segment_code=? AND d.project_id=?", (segment_code.strip(), project_id))
    if seg and seg["project_id"] != project_id:
        seg = None
    candidate = (candidate or "").strip()
    if not seg:
        res = verify.VerificationResult("rejected", "none", None, None, None, "The referenced segment does not exist in this project.")
        doc_id, seg_id = None, None
    else:
        res = verify.verify_against_segment(candidate, seg["text"], seg["speaker_role"], bool(seg["requires_verification"]))
        doc_id, seg_id = seg["document_id"], seg["id"]
        if res.status == "rejected" and res.reason and "does not appear" in res.reason:
            others = verify.find_in_document(candidate, db.query("SELECT * FROM qual_segments WHERE document_id=?", (doc_id,)))
            if others:
                res = verify.VerificationResult("manual_review", "none", None, None, None,
                                                f"Text not in the claimed segment {seg['segment_code']} but found in {', '.join(o['segment_code'] for o in others[:3])}. "
                                                "An analyst must confirm the correct segment and speaker; it is not auto-verified.")
    ms = me = None
    if seg and res.start is not None:
        ms, me = seg["start_char"] + res.start, seg["start_char"] + res.end
    qid = db.execute("INSERT INTO quotations(project_id, document_id, segment_id, claimed_segment_code, code_id, theme_id, candidate_text, verified_text,"
                     " verification_status, verification_method, match_start, match_end, rejection_reason, origin, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (project_id, doc_id, seg_id, segment_code or (seg["segment_code"] if seg else None), code_id, theme_id, candidate,
                      res.verified_text if res.status == "verified" else None, res.status, res.method, ms, me, res.reason, origin, db.now()))
    # Self-check: a verified quotation must reproduce exactly from the stored document text.
    if res.status == "verified":
        doc = db.query_one("SELECT full_text FROM qual_documents WHERE id=?", (doc_id,))
        if doc["full_text"][ms:me] != res.verified_text:
            db.execute("UPDATE quotations SET verification_status='rejected', verified_text=NULL, rejection_reason='Internal offset check failed.' WHERE id=?", (qid,))
            res = verify.VerificationResult("rejected", res.method, None, None, None, "Internal offset check failed.")
    audit.log(user.username, f"QUOTE_{res.status.upper()}", f"#{qid} {origin}", project_id=project_id, object_type="quotation", object_id=qid)
    return {"id": qid, "status": res.status, "method": res.method, "reason": res.reason, "verified_text": res.verified_text}


def list_quotations(user: CurrentUser, project_id: int, status: str | None = None) -> list[dict]:
    require(user, "project.view", project_id)
    sql = ("SELECT q.*, s.segment_code, s.speaker, s.speaker_role, s.page, s.paragraph, d.document_code, d.doc_type, d.location, d.respondent_group,"
           " d.collection_date, c.name AS code_name, t.name AS theme_name FROM quotations q LEFT JOIN qual_segments s ON s.id=q.segment_id"
           " LEFT JOIN qual_documents d ON d.id=q.document_id LEFT JOIN codes c ON c.id=q.code_id LEFT JOIN themes t ON t.id=q.theme_id WHERE q.project_id=?")
    params = [project_id]
    if status:
        sql += " AND q.verification_status=?"
        params.append(status)
    return db.query(sql + " ORDER BY q.id DESC", params)


def verified_register(user: CurrentUser, project_id: int, approved_only: bool = True) -> list[dict]:
    """The ONLY source of direct quotations for reports."""
    rows = [q for q in list_quotations(user, project_id, "verified") if q["verified_text"]]
    if approved_only:
        rows = [q for q in rows if q["analyst_decision"] == "approved"]
    # Defence in depth: re-verify against stored source text at read time.
    out = []
    for q in rows:
        doc = db.query_one("SELECT full_text FROM qual_documents WHERE id=?", (q["document_id"],))
        if doc and q["match_start"] is not None and doc["full_text"][q["match_start"]:q["match_end"]] == q["verified_text"]:
            out.append(q)
    return out


def decide_quotation(user: CurrentUser, quotation_id: int, decision: str) -> None:
    q = db.query_one("SELECT * FROM quotations WHERE id=?", (quotation_id,))
    if not q:
        raise QualError("Quotation not found.")
    require(user, "quote.review", q["project_id"])
    if decision not in ("approved", "excluded", "pending"):
        raise QualError("Decision must be approved, excluded or pending.")
    if decision == "approved" and q["verification_status"] != "verified":
        raise QualError("Only programmatically verified quotations can be approved for reports.")
    db.execute("UPDATE quotations SET analyst_decision=?, reviewed_by=?, reviewed_at=? WHERE id=?", (decision, user.id, db.now(), quotation_id))
    audit.log(user.username, f"QUOTE_{decision.upper()}", f"#{quotation_id}", project_id=q["project_id"], object_type="quotation", object_id=quotation_id)


def confirm_manual_review(user: CurrentUser, quotation_id: int, segment_id: int, exact_text: str) -> dict:
    """Analyst confirmation for manual_review quotes: the analyst selects the correct segment and the
    exact text as it appears in the original document. Re-verified programmatically; OCR documents
    record method 'analyst_confirmed_against_original'."""
    q = db.query_one("SELECT * FROM quotations WHERE id=?", (quotation_id,))
    require(user, "quote.review", q["project_id"])
    seg = db.query_one("SELECT s.*, d.project_id, d.requires_verification FROM qual_segments s JOIN qual_documents d ON d.id=s.document_id WHERE s.id=?", (segment_id,))
    if not seg or seg["project_id"] != q["project_id"]:
        raise PermissionDenied("Segment not in this project.")
    res = verify.verify_against_segment(exact_text, seg["text"], seg["speaker_role"], False)
    if res.status != "verified":
        raise QualError(f"Not confirmed: {res.reason}")
    method = "analyst_confirmed_against_original" if seg["requires_verification"] else res.method
    db.execute("UPDATE quotations SET segment_id=?, document_id=?, verified_text=?, verification_status='verified', verification_method=?, match_start=?, match_end=?,"
               " rejection_reason=NULL, reviewed_by=?, reviewed_at=? WHERE id=?",
               (segment_id, seg["document_id"], res.verified_text, method, seg["start_char"] + res.start, seg["start_char"] + res.end, user.id, db.now(), quotation_id))
    audit.log(user.username, "QUOTE_MANUAL_CONFIRMED", f"#{quotation_id}", "WARNING", project_id=q["project_id"], object_type="quotation", object_id=quotation_id)
    return {"status": "verified", "method": method}


def set_translation(user: CurrentUser, quotation_id: int, text: str, language: str, translator: str) -> None:
    q = db.query_one("SELECT * FROM quotations WHERE id=?", (quotation_id,))
    require(user, "quote.review", q["project_id"])
    db.execute("UPDATE quotations SET translation_text=?, translation_language=?, translation_by=? WHERE id=?", (text, language, translator, quotation_id))
    audit.log(user.username, "QUOTE_TRANSLATION_SET", f"#{quotation_id}", project_id=q["project_id"])


def assign_quotation(user: CurrentUser, quotation_id: int, code_id: int | None = None, theme_id: int | None = None) -> None:
    q = db.query_one("SELECT * FROM quotations WHERE id=?", (quotation_id,))
    require(user, "quote.review", q["project_id"])
    db.execute("UPDATE quotations SET code_id=COALESCE(?, code_id), theme_id=? WHERE id=?", (code_id, theme_id, quotation_id))


def quotes_for_theme(user: CurrentUser, theme_id: int, approved_only: bool = True) -> list[dict]:
    t = db.query_one("SELECT * FROM themes WHERE id=?", (theme_id,))
    ev = theme_evidence(user, theme_id)
    reg = verified_register(user, t["project_id"], approved_only)
    sub = {r["id"] for r in db.query("SELECT id FROM themes WHERE parent_id=?", (theme_id,))} | {theme_id}
    codes = set(ev["code_ids"])
    return [q for q in reg if q["theme_id"] in sub or (q["theme_id"] is None and q["code_id"] in codes)]


# ------------------------------------------------------------------ analytic notes

def add_note(user: CurrentUser, project_id: int, kind: str, text: str, *, theme_id: int | None = None, origin: str = "analyst",
             segment_ids: list[int] | None = None, priority: str | None = None, stakeholder: str | None = None, follow_up: str | None = None) -> int:
    require(user, "qual.code", project_id)
    if kind not in NOTE_KINDS:
        raise QualError("Unknown note type.")
    if not (text or "").strip():
        raise QualError("Text is required.")
    valid = {r["id"] for r in project_segments(user, project_id)}
    segs = [s for s in (segment_ids or []) if s in valid]
    nid = db.execute("INSERT INTO analytic_notes(project_id, theme_id, kind, text, origin, status, segment_ids_json, priority, stakeholder, follow_up, created_by, created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (project_id, theme_id, kind, text.strip(), origin, "draft" if origin == "ai" else "approved", db.dumps(segs), priority, stakeholder, follow_up, user.id, db.now()))
    return nid


def list_notes(user: CurrentUser, project_id: int, kind: str | None = None, theme_id: int | None = None, approved_only: bool = False) -> list[dict]:
    require(user, "project.view", project_id)
    sql, p = "SELECT * FROM analytic_notes WHERE project_id=?", [project_id]
    if kind:
        sql += " AND kind=?"; p.append(kind)
    if theme_id is not None:
        sql += " AND theme_id=?"; p.append(theme_id)
    if approved_only:
        sql += " AND status='approved'"
    rows = db.query(sql + " ORDER BY id", p)
    for r in rows:
        r["segment_ids"] = db.loads(r.get("segment_ids_json"), []) or []
    return rows


def review_note(user: CurrentUser, note_id: int, status: str, text: str | None = None, **fields) -> None:
    n = db.query_one("SELECT * FROM analytic_notes WHERE id=?", (note_id,))
    require(user, "qual.code", n["project_id"])
    if status not in ("draft", "approved", "excluded"):
        raise QualError("Invalid status.")
    db.execute("UPDATE analytic_notes SET status=?, text=COALESCE(?, text), priority=COALESCE(?, priority), stakeholder=COALESCE(?, stakeholder),"
               " follow_up=COALESCE(?, follow_up), reviewed_by=?, reviewed_at=? WHERE id=?",
               (status, text, fields.get("priority"), fields.get("stakeholder"), fields.get("follow_up"), user.id, db.now(), note_id))
    audit.log(user.username, "NOTE_REVIEWED", f"#{note_id} -> {status}", project_id=n["project_id"], object_type="note", object_id=note_id)


def project_summary(user: CurrentUser, project_id: int) -> dict:
    require(user, "project.view", project_id)
    q = lambda sql: db.query_one(sql, (project_id,))["n"]
    return {
        "documents": q("SELECT COUNT(*) n FROM qual_documents WHERE project_id=?"),
        "segments": q("SELECT COUNT(*) n FROM qual_segments s JOIN qual_documents d ON d.id=s.document_id WHERE d.project_id=?"),
        "codes": q("SELECT COUNT(*) n FROM codes WHERE project_id=? AND status IN ('suggested','approved')"),
        "codes_approved": q("SELECT COUNT(*) n FROM codes WHERE project_id=? AND status='approved'"),
        "themes": q("SELECT COUNT(*) n FROM themes WHERE project_id=? AND status<>'rejected'"),
        "themes_approved": q("SELECT COUNT(*) n FROM themes WHERE project_id=? AND status='approved'"),
        "quotes_verified": q("SELECT COUNT(*) n FROM quotations WHERE project_id=? AND verification_status='verified'"),
        "quotes_approved": q("SELECT COUNT(*) n FROM quotations WHERE project_id=? AND verification_status='verified' AND analyst_decision='approved'"),
        "quotes_rejected": q("SELECT COUNT(*) n FROM quotations WHERE project_id=? AND verification_status='rejected'"),
        "quotes_manual": q("SELECT COUNT(*) n FROM quotations WHERE project_id=? AND verification_status='manual_review'"),
    }
