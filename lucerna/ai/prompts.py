"""Versioned prompts. Change the version string whenever a prompt's wording changes, so every
AI-generated code/theme/summary can be traced to the exact prompt that produced it."""

SYSTEM_QUAL = """You are Lucerna's qualitative research assistant for humanitarian and development organisations.
Rules you must follow:
1. Use ONLY the transcript segments supplied. Never use outside knowledge.
2. Never invent statements, people, numbers, demographics, locations, dates or events.
3. A quotation must be copied character-for-character from ONE supplied segment. Never paraphrase, correct, translate, shorten with ellipses, or merge text.
4. Only quote respondents; do not quote the moderator/interviewer.
5. Every segment_id you return must be one of the supplied ids.
6. If evidence is weak or ambiguous, omit it. An empty list is acceptable.
7. Return a single JSON object only, with no Markdown and no commentary."""

OPEN_CODING = ("open_coding", "2026.11.1", """Perform open coding on the transcript segments below.
For each segment, identify clear ideas explicitly expressed by the respondent (not the moderator).
A code is short (2–6 words), descriptive, and grounded in the respondent's words.
Return JSON exactly in this structure:
{{"codes": [{{"code": "short code", "definition": "one sentence, grounded in the text", "segment_ids": ["ID"]}}],
  "quotes": [{{"segment_id": "ID", "quote": "exact text copied from that segment", "code": "matching code"}}]}}
Prefer existing codebook codes when they fit: {existing_codes}
SEGMENTS (moderator context is given in 'context' and must not be quoted):
{segments}""")

AXIAL_CODING = ("axial_coding", "2026.11.1", """Group the open codes below into a small number of meaningful themes (axial coding).
Use only the supplied codes; do not invent codes. A theme may have subthemes.
Return JSON exactly in this structure:
{{"themes": [{{"theme": "name", "definition": "what the theme covers", "codes": ["code", "..."],
              "subthemes": [{{"theme": "name", "definition": "...", "codes": ["code"]}}]}}]}}
OPEN CODES (name — definition — number of coded segments):
{codes}""")

THEME_ANALYSIS = ("theme_analysis", "2026.11.1", """You are analysing one theme from a qualitative study.
Theme: {theme}
Definition: {definition}
Evidence segments (id, document, speaker, text):
{segments}
Write an evidence-based analytical explanation, and identify contradictions, negative cases and evidence gaps.
Every point must cite supporting segment ids from the list. Do not invent facts or counts; do not state how many people hold a view.
Return JSON exactly in this structure:
{{"explanation": "2–4 analytical paragraphs", "explanation_segment_ids": ["ID"],
  "contradictions": [{{"text": "...", "segment_ids": ["ID"]}}],
  "negative_cases": [{{"text": "...", "segment_ids": ["ID"]}}],
  "evidence_gaps": ["what the evidence does not tell us"],
  "community_recommendations": [{{"text": "recommendation explicitly voiced by respondents", "segment_ids": ["ID"]}}]}}""")

EVIDENCE_QA = ("evidence_qa", "2026.11.1", """Answer the question using ONLY the evidence segments below.
If the evidence does not answer it, reply "Insufficient evidence in the uploaded sources."
Every claim must cite segment ids. Quotations must be exact copies from one segment.
Return JSON: {{"answer": "...", "segment_ids": ["ID"], "quotes": [{{"segment_id": "ID", "quote": "exact text"}}]}}
QUESTION: {question}
EVIDENCE:
{segments}""")

QUANT_NARRATIVE = ("quant_narrative", "2026.11.1", """Write a short interpretive paragraph for a humanitarian report section titled "{section}".
Use ONLY the verified facts below. Do not introduce any number that is not in the facts. Do not claim causation.
Do not recommend actions. Write in plain professional English, 80–150 words.
FACTS:
{facts}
Return JSON: {{"paragraph": "..."}}""")
