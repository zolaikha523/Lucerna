from .ingest import normalize


def verify_quote(quote, source_text):
    """
    Verify that a quotation exists exactly inside the source text.

    Verification levels:
    1. exact
    2. normalized_exact
    3. rejected

    No quotation is ever repaired, reconstructed, or invented.
    """

    if not quote or not source_text:
        return {
            "verified": False,
            "method": "empty"
        }

    # Highest-confidence verification
    if quote in source_text:
        return {
            "verified": True,
            "method": "exact"
        }

    # Secondary verification for harmless whitespace differences
    normalized_quote = normalize(quote)
    normalized_source = normalize(source_text)

    if (
        normalized_quote
        and normalized_quote in normalized_source
    ):
        return {
            "verified": True,
            "method": "normalized_exact"
        }

    return {
        "verified": False,
        "method": "rejected"
    }


def validate_candidate(candidate, segments):
    """
    Enterprise evidence gatekeeper.

    A candidate quotation is accepted only when:

    1. Candidate is a valid dictionary.
    2. segment_id exists.
    3. segment_id belongs to the supplied evidence set.
    4. document_id, if supplied, matches the source segment.
    5. quote exists.
    6. quote is an exact or normalized substring of that segment.

    Invalid candidates are explicitly rejected and never receive
    a verified_quote.
    """

    if not isinstance(candidate, dict):
        return {
            "verified": False,
            "verification_method": "invalid_candidate",
            "verified_quote": None,
            "rejection_reason": (
                "Candidate evidence is not a valid object."
            )
        }

    quote = (
        candidate.get("quote") or ""
    ).strip()

    segment_id = (
        candidate.get("segment_id") or ""
    ).strip()

    supplied_document_id = (
        candidate.get("document_id") or ""
    ).strip()

    # ---------------------------------------------------------
    # 1. Validate segment reference
    # ---------------------------------------------------------

    if not segment_id:
        return {
            **candidate,
            "verified": False,
            "verification_method": "missing_segment_id",
            "verified_quote": None,
            "rejection_reason": (
                "Candidate does not contain a segment_id."
            )
        }

    segment_by_id = {
        segment.get("segment_id"): segment
        for segment in segments
        if segment.get("segment_id")
    }

    segment = segment_by_id.get(
        segment_id
    )

    if segment is None:
        return {
            **candidate,
            "verified": False,
            "verification_method": "missing_segment",
            "verified_quote": None,
            "rejection_reason": (
                "The supplied segment_id does not exist "
                "in the evidence set."
            )
        }

    # ---------------------------------------------------------
    # 2. Validate document reference
    # ---------------------------------------------------------

    actual_document_id = (
        segment.get("document_id") or ""
    ).strip()

    if (
        supplied_document_id
        and supplied_document_id
        != actual_document_id
    ):
        return {
            **candidate,
            "document_id": actual_document_id,
            "verified": False,
            "verification_method": "document_mismatch",
            "verified_quote": None,
            "rejection_reason": (
                "Candidate document_id does not match "
                "the document containing the referenced segment."
            )
        }

    # ---------------------------------------------------------
    # 3. Validate quotation content
    # ---------------------------------------------------------

    if not quote:
        return {
            **candidate,
            "document_id": actual_document_id,
            "verified": False,
            "verification_method": "empty_quote",
            "verified_quote": None,
            "rejection_reason": (
                "Candidate contains an empty quotation."
            )
        }

    source_text = (
        segment.get("text") or ""
    )

    result = verify_quote(
        quote,
        source_text
    )

    # ---------------------------------------------------------
    # 4. Verified evidence
    # ---------------------------------------------------------

    if result["verified"]:
        return {
            **candidate,
            "document_id": actual_document_id,
            "verified": True,
            "verification_method": result["method"],
            "verified_quote": quote,
            "rejection_reason": None
        }

    # ---------------------------------------------------------
    # 5. Rejected evidence
    # ---------------------------------------------------------

    return {
        **candidate,
        "document_id": actual_document_id,
        "verified": False,
        "verification_method": result["method"],
        "verified_quote": None,
        "rejection_reason": (
            "Quotation could not be found in the referenced "
            "source segment."
        )
    }


def validate_open_codes(codes, segments):
    """Keep only open-code links that refer to real supplied segments."""
    valid_ids = {s.get("segment_id") for s in segments if s.get("segment_id")}
    cleaned = []
    for item in (codes or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("code") or "").strip()
        if not name:
            continue
        ids = item.get("segment_ids") or []
        if not isinstance(ids, list):
            ids = []
        ids = sorted({str(x).strip() for x in ids if str(x).strip() in valid_ids})
        if ids:
            cleaned.append({**item, "code": name, "segment_ids": ids})
    return cleaned


def validate_themes(themes, codes):
    """Keep theme membership restricted to validated open-code names."""
    valid = {str(c.get("code", "")).strip().lower(): str(c.get("code", "")).strip() for c in (codes or [])}
    cleaned = []
    for item in (themes or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("theme") or "").strip()
        members = item.get("codes") or []
        if not name or not isinstance(members, list):
            continue
        members = list(dict.fromkeys(valid[str(m).strip().lower()] for m in members if str(m).strip().lower() in valid))
        if members:
            cleaned.append({**item, "theme": name, "codes": members})
    return cleaned
