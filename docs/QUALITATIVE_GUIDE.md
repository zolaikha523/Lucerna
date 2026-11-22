# Qualitative Guide

## Transcripts
Upload TXT, DOCX, PDF or Markdown. A header such as `Type: FGD`, `Location: …`, `Date: …`, `Group: …` is read into
the document metadata. Lines like `Moderator:` or `P3 (female, 28):` start a new speaker turn; the label is stored as the
speaker and is **not** part of the segment text. Each segment keeps its page, paragraph and exact character offsets.
Moderator turns are kept as context and can never be quoted.

## AI-assisted coding
Runs in the background with the local model: open coding per segment batch, axial grouping into themes, and theme
analysis (summary, contradictions, negative cases, community recommendations, evidence gaps). Codes and themes from AI
are **suggested** until an analyst approves them; AI summaries are **drafts**. References to segments that do not exist
are discarded and counted. If the model fails, the job fails with the reason. Interrupted runs can resume from the last
checkpoint.

## Quotation verification rules
A quotation is **verified** only if it appears in the referenced respondent segment exactly, or after controlled
normalisation (Unicode form, whitespace, typographic quotes and dashes) that maps back to the exact source text.
It is **rejected** if it is not in the segment, is shorter than 4 words, contains an ellipsis, or belongs to the
moderator. It goes to **manual review** if it is found in another segment than the one cited, or if the document came
from OCR. Only verified quotations can be approved for reports, and reports re-verify them when built.

## Separating evidence from interpretation
Each note has a type: AI-generated summary, analytical interpretation, researcher conclusion, contradictory evidence,
negative case, evidence gap, recommendation, recommendation voiced by respondents, limitation, cross-cutting finding,
mixed-methods finding. Reports show these separately and include only approved items.

## Counting
Evidence profiles count documents and distinct speaker labels; these are not prevalence estimates.
