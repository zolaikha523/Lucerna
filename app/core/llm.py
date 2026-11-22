import os
import json
import requests


OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma3:4b"
)

MAX_SEGMENTS = int(
    os.getenv(
        "MAX_SEGMENTS_PER_LLM_BATCH",
        "1"
    )
)

LLM_TIMEOUT = int(
    os.getenv(
        "OLLAMA_TIMEOUT_SECONDS",
        "120"
    )
)

MAX_JSON_RETRIES = int(
    os.getenv(
        "LLM_JSON_RETRIES",
        "1"
    )
)


SYSTEM = """You are EvidenceQDA, an evidence-grounded qualitative data analysis assistant designed for humanitarian and development organizations.

Your highest priority is empirical accuracy and evidence traceability.

You MUST follow these rules:

1. Use ONLY information contained in the supplied transcript segments.
2. Never invent participant statements, facts, events, numbers, demographics, locations, or findings.
3. Never create evidence that is not present in the transcript.
4. Every segment_id must come directly from the supplied transcript segments.
5. Every quotation must be copied EXACTLY from its source segment.
6. Never paraphrase a quotation.
7. Never modify a quotation.
8. Never combine text from different segments into one quotation.
9. If evidence is weak or ambiguous, omit the code or quotation.
10. Prefer a small number of strong codes over many speculative codes.
11. Return valid JSON only.
12. Do not wrap JSON in Markdown code fences.
13. Do not add explanations before or after the JSON.
"""


def _extract_json_object(content):
    """
    Safely parse a JSON object returned by the local LLM.

    The preferred path is strict JSON parsing.

    A secondary recovery path extracts the outermost JSON object
    if the model accidentally adds surrounding text.

    IMPORTANT:
    This function NEVER invents or repairs missing evidence.
    It only parses already-returned content.
    """

    if not content:
        raise ValueError(
            "The LLM returned an empty response."
        )

    content = content.strip()

    # ---------------------------------------------------------
    # First attempt: strict JSON.
    # ---------------------------------------------------------

    try:
        return json.loads(content)

    except json.JSONDecodeError as first_error:

        # -----------------------------------------------------
        # Second attempt: remove Markdown code fences.
        # -----------------------------------------------------

        cleaned = content

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)

        except json.JSONDecodeError:
            # -------------------------------------------------
            # Third attempt: locate the outermost JSON object.
            # -------------------------------------------------

            start = cleaned.find("{")
            end = cleaned.rfind("}")

            if start >= 0 and end > start:

                candidate = cleaned[
                    start:end + 1
                ]

                try:
                    return json.loads(
                        candidate
                    )

                except json.JSONDecodeError:
                    pass

            raise ValueError(
                "The LLM returned malformed or incomplete JSON."
            ) from first_error


def _call(messages):
    """
    Call the local Ollama model.

    The model is explicitly forced to CPU because the current
    workstation GPU memory is insufficient for stable Gemma 3:4B
    inference.

    The function also limits generation length so that responses
    are less likely to be truncated while generating JSON.
    """

    body = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_gpu": 0,

            # Prevent incomplete JSON caused by generation
            # being cut off too early.
            "num_predict": 2048
        }
    }

    last_error = None

    for attempt in range(
        1,
        MAX_JSON_RETRIES + 1
    ):

        try:

            response = requests.post(
                OLLAMA_URL,
                json=body,
                timeout=LLM_TIMEOUT
            )

            response.raise_for_status()

            data = response.json()

            content = (
                data
                .get("message", {})
                .get("content", "")
            )

            return _extract_json_object(
                content
            )

        except (
            requests.RequestException,
            ValueError,
            json.JSONDecodeError
        ) as error:

            last_error = error

            if attempt < MAX_JSON_RETRIES:
                continue

            raise RuntimeError(
                "EvidenceQDA LLM request failed after "
                f"{MAX_JSON_RETRIES} attempts: "
                f"{error}"
            ) from error

    raise RuntimeError(
        f"EvidenceQDA LLM request failed: {last_error}"
    )


def _build_analysis_prompt(payload):
    """
    Build the conservative open-coding prompt.
    """

    return f"""
You are performing conservative open coding of qualitative research data.

Read the transcript segments below carefully.

For each segment, identify only clear and meaningful ideas that are
explicitly expressed by the participant.

An open code should be:

- short
- descriptive
- grounded directly in the participant's words
- useful for qualitative analysis
- non-speculative

DO NOT:

- invent information
- infer information that is not stated
- create demographic assumptions
- create causes that participants did not mention
- create findings from general knowledge
- create quotations that do not exist

For quotations:

- copy the text EXACTLY from the source segment
- do not change spelling
- do not summarize
- do not paraphrase
- do not combine different parts of different segments
- the quotation must be a direct substring of the cited segment

Return ONLY valid JSON using exactly this structure:

{{
  "open_codes": [
    {{
      "code": "short descriptive code",
      "description": "brief explanation grounded in the segment",
      "segment_ids": ["SEGMENT_ID"]
    }}
  ],
  "candidate_quotes": [
    {{
      "segment_id": "SEGMENT_ID",
      "quote": "exact quotation copied from the segment",
      "code": "matching open code"
    }}
  ]
}}

IMPORTANT:

- Never return an empty code when meaningful evidence exists.
- Never return an empty description when a code is provided.
- Never create a quote simply to fill the output.
- It is acceptable to return an empty list when there is insufficient evidence.
- Every segment_id must exactly match one of the supplied segment IDs.
- Every quote must exactly match text contained in its cited segment.
- Return JSON only.
- Do not use Markdown.
- Do not add commentary.

TRANSCRIPT SEGMENTS:

{json.dumps(
    payload,
    ensure_ascii=False,
    indent=2
)}
"""


def _analyze_batch_once(segments):
    """
    Perform one LLM analysis request for a batch.

    This function does NOT perform recursive fallback.
    """

    payload = [
        {
            "segment_id": segment["segment_id"],
            "text": segment["text"]
        }
        for segment in segments
    ]

    prompt = _build_analysis_prompt(
        payload
    )

    result = _call(
        [
            {
                "role": "system",
                "content": SYSTEM
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    if not isinstance(result, dict):
        raise ValueError(
            "LLM analysis response is not a JSON object."
        )

    return {
        "open_codes": (
            result.get(
                "open_codes",
                []
            )
            if isinstance(
                result.get(
                    "open_codes",
                    []
                ),
                list
            )
            else []
        ),
        "candidate_quotes": (
            result.get(
                "candidate_quotes",
                []
            )
            if isinstance(
                result.get(
                    "candidate_quotes",
                    []
                ),
                list
            )
            else []
        )
    }


def analyze_batch(segments):
    """Analyze a batch and preserve explicit failure diagnostics."""
    if not segments:
        return {"open_codes": [], "candidate_quotes": [], "warnings": []}
    try:
        result = _analyze_batch_once(segments)
        result["warnings"] = []
        return result
    except Exception as error:
        if len(segments) == 1:
            sid = segments[0].get("segment_id", "unknown")
            message = f"LLM analysis failed for {sid}: {error}"
            print("[EvidenceQDA] WARNING:", message)
            return {"open_codes": [], "candidate_quotes": [], "warnings": [message]}
        midpoint = max(1, len(segments) // 2)
        left_result = analyze_batch(segments[:midpoint])
        right_result = analyze_batch(segments[midpoint:])
        return {
            "open_codes": left_result.get("open_codes", []) + right_result.get("open_codes", []),
            "candidate_quotes": left_result.get("candidate_quotes", []) + right_result.get("candidate_quotes", []),
            "warnings": left_result.get("warnings", []) + right_result.get("warnings", [])
        }


def synthesize_themes(open_codes):
    """
    Group supplied open codes into broader axial themes.

    Themes are generated ONLY from supplied open codes.

    If the local LLM cannot reliably return valid JSON,
    the function returns an empty theme list rather than
    inventing or fabricating thematic evidence.
    """

    if not open_codes:
        return []

    prompt = f"""
You are performing axial coding for qualitative research.

Group the supplied open codes into a small number of meaningful
axial themes.

IMPORTANT:

- Use ONLY the supplied open codes.
- Do not invent evidence.
- Do not invent participant statements.
- Do not invent segment IDs.
- Do not add codes that are not present.
- Every theme must be supported by the supplied codes.
- Prefer fewer meaningful themes over many speculative themes.
- Themes should represent relationships or broader categories
  connecting related open codes.

Return ONLY valid JSON:

{{
  "axial_themes": [
    {{
      "theme": "theme name",
      "description": "brief explanation of the theme",
      "codes": [
        "open code 1",
        "open code 2"
      ]
    }}
  ]
}}

OPEN CODES:

{json.dumps(
    open_codes,
    ensure_ascii=False,
    indent=2
)}
"""

    try:

        result = _call(
            [
                {
                    "role": "system",
                    "content": SYSTEM
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        themes = result.get(
            "axial_themes",
            []
        )

        if not isinstance(
            themes,
            list
        ):
            return []

        return themes

    except Exception as error:

        print(
            "[EvidenceQDA] WARNING: "
            "Axial theme synthesis failed: "
            f"{error}"
        )

        return []


def analyze_segments(segments):
    """
    Run the complete qualitative analysis pipeline.

    Pipeline:

    1. Split evidence into manageable batches.
    2. Generate candidate open codes.
    3. Generate candidate quotations.
    4. Automatically reduce failed batches.
    5. Merge duplicate codes.
    6. Generate axial themes.
    7. Map themes back to candidate quotations.

    IMPORTANT:

    Candidate quotations remain unverified at this stage.
    They MUST pass the programmatic validator before being
    treated as verified evidence.
    """

    all_codes = []
    all_quotes = []
    analysis_warnings = []

    for i in range(
        0,
        len(segments),
        MAX_SEGMENTS
    ):

        batch = segments[
            i:i + MAX_SEGMENTS
        ]

        result = analyze_batch(
            batch
        )

        all_codes.extend(
            result.get(
                "open_codes",
                []
            )
        )

        all_quotes.extend(
            result.get(
                "candidate_quotes",
                []
            )
        )
        analysis_warnings.extend(result.get("warnings", []))

    # ---------------------------------------------------------
    # Deduplicate open codes while preserving evidence links.
    # ---------------------------------------------------------

    merged = {}

    for item in all_codes:

        code = (
            item.get("code") or ""
        ).strip()

        if not code:
            continue

        key = code.lower()

        if key not in merged:

            merged[key] = {
                "code": code,
                "description": (
                    item.get(
                        "description",
                        ""
                    )
                ),
                "segment_ids": []
            }

        existing_ids = (
            merged[key]["segment_ids"]
        )

        new_ids = (
            item.get(
                "segment_ids",
                []
            )
        )

        if not isinstance(
            new_ids,
            list
        ):
            new_ids = []

        merged[key]["segment_ids"] = sorted(
            set(existing_ids)
            | set(new_ids)
        )

    codes = list(
        merged.values()
    )

    # Theme synthesis is optional enrichment: a failure must not erase codes/quotes.
    try:
        themes = synthesize_themes(codes)
    except Exception as error:
        message = f"Axial theme synthesis failed: {error}"
        print("[EvidenceQDA] WARNING:", message)
        analysis_warnings.append(message)
        themes = []
    if not isinstance(themes, list):
        themes = []
    if codes and not themes:
        analysis_warnings.append("No axial themes were returned; findings remain at open-code level.")

    # ---------------------------------------------------------
    # Map each open code to its axial theme.
    # ---------------------------------------------------------

    theme_by_code = {}

    for theme in themes:

        if not isinstance(
            theme,
            dict
        ):
            continue

        theme_name = (
            theme.get(
                "theme"
            )
            or "Unclassified"
        )

        theme_codes = (
            theme.get(
                "codes",
                []
            )
        )

        if not isinstance(
            theme_codes,
            list
        ):
            continue

        for code in theme_codes:

            normalized_code = (
                str(code)
                .strip()
                .lower()
            )

            if normalized_code:
                theme_by_code[
                    normalized_code
                ] = theme_name

    # ---------------------------------------------------------
    # Attach theme information to candidate quotations.
    # ---------------------------------------------------------

    for quote in all_quotes:

        if not isinstance(
            quote,
            dict
        ):
            continue

        normalized_code = (
            quote.get("code") or ""
        ).strip().lower()

        quote["theme"] = (
            theme_by_code.get(
                normalized_code,
                "Unclassified"
            )
        )

    return {
        "open_codes": codes,
        "axial_themes": themes,
        "candidate_quotes": all_quotes,
        "analysis_warnings": analysis_warnings,
        "analysis_status": ("complete" if not analysis_warnings else ("partial" if codes or all_quotes else "failed"))
    }


def answer_question(
    question,
    evidence_segments,
    history=None
):
    """
    Evidence-grounded question answering.

    The model may answer ONLY from supplied evidence segments.

    Quotes returned here are still candidate quotes and should
    be validated by the programmatic validator before being
    presented as verified evidence.
    """

    payload = [
        {
            "segment_id": segment["segment_id"],
            "document_id": segment["document_id"],
            "text": segment["text"]
        }
        for segment in evidence_segments
    ]

    prompt = f"""
Answer the user's question using ONLY the supplied evidence segments.

STRICT EVIDENCE RULES:

1. Do not use outside knowledge.
2. Do not infer unsupported facts.
3. Do not invent information.
4. If the evidence does not support an answer, say:

"Insufficient evidence in the uploaded sources."

5. Every factual claim must cite one or more supplied segment IDs.
6. Every citation must correspond to an actual supplied segment.
7. If you use a quotation, copy it EXACTLY from its source segment.
8. Never paraphrase a quotation.
9. Keep quotations short.
10. Never invent a segment ID.

Return ONLY valid JSON:

{{
  "answer": "evidence-grounded answer",
  "citations": [
    "SEGMENT-ID"
  ],
  "quotes": [
    {{
      "segment_id": "SEGMENT-ID",
      "quote": "exact quotation from the segment"
    }}
  ]
}}

QUESTION:

{question}

EVIDENCE:

{json.dumps(
    payload,
    ensure_ascii=False,
    indent=2
)}
"""

    return _call(
        [
            {
                "role": "system",
                "content": SYSTEM
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

