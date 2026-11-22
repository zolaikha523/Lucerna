# Testing

```
python -m pytest tests -v          # or run_tests_windows.bat
```
Result on 2026-11-21 (3.1.0-alpha): **70 passed** (log: `docs/test_evidence/pytest_phase2_2026-11-21.txt`).

## What is covered
- `tests/test_quality_gate.py` — the 7 original EvidenceQDA tests.
- `tests/test_dashboard_engine.py` — 26 tests for the one-click dashboard generator (the 23 required scenarios, adaptivity across datasets, and no dataset-specific rules), run on `tests/adaptive_datasets.py` and `tests/dtm_workbook.py`.
- `tests/test_lucerna.py`
  - Quantitative: adaptive dashboards for 7 synthetic datasets (every visual computes; page structures differ), chart values vs
    independent pandas calculation, indicator value vs manual calculation, no invented targets, provisional suggestions,
    cleaning never alters the original and reverts, planted quality issues found, forecast refused with short history,
    compatibility checks, Power BI package honesty, maps from valid coordinates only.
  - Qualitative: exact offsets and no speaker labels in segments, exact quote verified, fabricated quotes rejected,
    paraphrase/ellipsis/moderator rejected, wrong segment → manual review → confirmation, OCR never auto-verifies,
    only verified quotes approvable, register re-verification after source tampering, AI job with fake model (invalid
    references dropped, fabrications rejected, outputs stay drafts), AI failure surfaced.
  - Security: role enforcement, org/project isolation, lockout, session revocation/expiry, MFA lifecycle, weak passwords,
    upload restrictions, external AI blocked by default and for Restricted projects, denials audited.
  - Reports: DOCX/PDF/XLSX generation with DRAFT label and "Not provided", approval requires review steps and manager role,
    qualitative report contains only approved verified quotes, mixed report, version diff, backup contents.

## Synthetic data
`tests/synthetic_data.py` writes `tests/fixtures/`: PDM cash (with deliberate issues), WASH household survey with coordinates,
returnee flow monitoring (18 months, `;`-delimited), food security (FCS/rCSI), baseline/endline, feedback records (JSONL),
two FGD and one KII transcript, and a list of fabricated quotations. All are fictional and labelled SYNTHETIC.
`tests/fake_llm.py` is a deterministic keyword stand-in for the model; it is not AI.

## Demo workspace
`python -m tests.seed_demo` builds a full demo project (point `LUCERNA_DATA_DIR`/`LUCERNA_DB` at an empty folder first).

## Not covered automatically
Live Ollama output quality, Windows installation, OCR on real scans, and browser interactions (checked manually with Playwright screenshots).
