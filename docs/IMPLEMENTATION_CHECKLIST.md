# Lucerna — Implementation Checklist

Status as of 2026-11-21. **Done** = implemented and exercised by an automated test or a live browser run.
**Partial** = works but with stated gaps. **Not done** = not implemented. Evidence column names the test
(`tests/test_lucerna.py`) or check that backs the status. Full test output: `docs/test_evidence/pytest_2026-11-21.txt`.

## 1. Foundation (from the EvidenceQDA audit, `docs/00_AUDIT_EvidenceQDA.md`)

| # | Item | Status | Evidence / notes |
|---|---|---|---|
| A2 | Persistent storage of all analysis (no session-only state) | Done | SQLite + parquet; every module reads from the DB |
| A3 | Organisations and project isolation | Done | `test_organisation_and_project_isolation` |
| A4 | RBAC with 6 project roles + org admin + system admin, enforced in the service layer | Done | `test_role_permissions_enforced_in_service_layer`, `test_permission_denials_are_audited` |
| A5 | MFA enabled only after a confirmed code; disabling needs the password | Done | `test_mfa_only_enabled_after_confirmation_and_disable_needs_password` |
| A6 | Sessions checked on every page load; expiry and revocation | Done | `test_sessions_revocation_and_expiry` |
| A7 | Login throttling / lockout | Done | `test_login_lockout_after_repeated_failures` |
| A8 | Upload validation (type, size, content signature), server-generated stored names | Done | `test_upload_restrictions` |
| A9 | Non-overlapping speaker-turn segmentation with exact offsets, page/paragraph, speaker; labels excluded | Done | `test_segments_are_speaker_turns_with_exact_offsets_and_no_labels` |
| A10 | Verification method + source span recorded; OCR → manual review | Done | `test_ocr_documents_never_auto_verify` |
| A11 | Codebook editing: approve, reject, rename, merge, split, versions | Done (UI) | Coding & Codebook page; merge/split service functions |
| A13 | Retries configurable, `num_gpu` configurable, prompt versions, AI run log (metadata only) | Done | `lucerna/ai/providers.py`, `ai_runs` table |
| A14 | Background jobs with progress, cancellation, checkpoints, resume | Done | `test_ai_coding_job_...`; interrupted jobs marked failed at start-up |
| A16 | Privacy flags enforced (external AI) | Done | `test_external_ai_blocked_by_default`, `test_external_ai_restricted_project_always_blocked` |
| — | Versioned SQL migrations, legacy EvidenceQDA DB migrated in place | Done | `lucerna/migrations/0001–0006`; legacy DB used automatically if present |
| — | Original 7 EvidenceQDA tests still pass | Done | `tests/test_quality_gate.py` |

## 2. Quantitative Data Intelligence

| Item | Status | Evidence / notes |
|---|---|---|
| Ingestion: XLSX, XLS, CSV, TSV, TXT, JSON, JSONL, DOCX tables, PDF tables; multi-sheet; multi-table sheets | Done | All 7 synthetic datasets import; DOCX/PDF tables via python-docx/pdfplumber |
| Encoding & delimiter detection | Done | `;`-delimited returnee file imports |
| Schema detection: type, role, confidence, reasons, PII risk, multi-select, unit of analysis, sector | Done | Data Understanding page |
| Mapping UI with user confirmation (audited) | Done | Live browser check |
| Quality checks + proposals; preview; approve; apply to analytical copy only; revert; history | Done | `test_cleaning_never_touches_the_original_and_can_be_reverted`, `test_quality_detects_planted_issues_in_pdm` |
| Deterministic statistics (descriptive, weighted, frequencies incl. multiple response, crosstab with chi-square/Fisher, group tests, correlation, time series, ETS forecast, anomalies, OLS, longitudinal, pyramid, Wilson CI) | Done | `lucerna/quant/stats.py`; `test_forecast_refused_with_short_history` |
| Humanitarian counting logic (units never mixed, rules shown) | Done | Statistical Analysis › Counting |
| Indicators: definitions, numerator/denominator, disaggregation, baseline/target only when entered, provisional → configured → verified | Done | `test_percentage_indicator_...`, `test_suggested_indicators_are_provisional_without_targets` |
| Sector templates (FCS, rCSI weights with sources) | Partial | Weights in `quant/templates.py`; no one-click "apply FCS template" button yet |
| AI Auto Dashboard: rule-based analytical plan, adaptive pages, feasibility, limitations | Done | `test_every_dataset_gets_an_adaptive_dashboard_that_computes` (7 datasets, ≥4 distinct page structures) |
| 23 visual types, validated colour-blind-safe palette, stable colours, max 7 categories + Other | Done | `lucerna/quant/charts.py`, `palette.py` |
| Cross-filtering (click bar/slice), drill-down hierarchies, filter bar, bookmarks | Done | Dashboards page; plotly selection events |
| Custom Dashboard Studio: pages, visuals, widths, reorder, filters, versions, restore, duplicate, templates | Done | Live browser check |
| Free drag-and-drop canvas | Not done | Streamlit has no drag-and-drop canvas; layout uses a 12-column grid with move/width controls |
| Comparative analysis (rounds, baseline/endline) with compatibility checks and significance tests | Done | `test_baseline_endline_comparison_checks_compatibility` |
| Point maps from verified coordinates only | Done | `test_maps_only_from_valid_coordinates` |
| Choropleth maps | Partial | Renderer implemented and refuses to draw without a boundary file; **no UI to upload GeoJSON boundaries yet** |
| Exports: CSV/XLSX datasets (PII dropped, optional pseudonymisation), chart CSV/PNG/SVG | Done | Data Library › Export; visual export menu |
| Power BI package (star schema, M, DAX, relationships, theme), explicitly not a PBIX | Done | `test_power_bi_package_is_honest` |

## 3. Qualitative Data Intelligence

| Item | Status | Evidence / notes |
|---|---|---|
| Ingestion TXT/DOCX/PDF/MD; metadata from transcript headers; editable metadata | Done | Documents page |
| OCR for scanned PDFs flagged for manual verification | Partial | Works only when Tesseract + `pytesseract`/`pypdfium2` are installed (optional); not tested here with a real scan |
| Open coding, axial coding, theme analysis via local LLM in background jobs | Done (mocked) | Tested with a deterministic fake model. **Not tested against a live Ollama model in this environment** |
| Analyst review: approve/reject/rename/merge/split codes; codebook snapshots | Done | Coding & Codebook page |
| Themes and subthemes, evidence profile (documents/speakers, not prevalence) | Done | Themes & Findings page |
| Strict quotation verification (exact / controlled normalisation, min 4 words, no ellipsis, moderator excluded, wrong segment → manual review, offset self-check, read-time re-verification) | Done | 8 tests in `TestQualitative` incl. fabricated quotes |
| Separation of verified quotes / AI summaries / interpretations / conclusions / recommendations | Done | `analytic_notes.kind` + origin; AI notes are drafts |
| Translations stored alongside, original text remains the evidence | Done | Quotations page |
| Evidence Q&A with cited segments, invalid citations discarded | Done (mocked) | Evidence Q&A page |

## 4. Reports

| Item | Status | Evidence / notes |
|---|---|---|
| Quantitative, qualitative (sections A–I + annexes) and mixed-methods reports | Done | `test_quantitative_report_...`, `test_qualitative_report_uses_only_approved_verified_quotes`, `test_mixed_report_builds` |
| DOCX (cover, TOC field, headers/footers, page numbers), PDF (cover, TOC, page numbers), XLSX tables | Done | Visual check of PDFs |
| "Not provided" instead of invented methodology | Done | asserted in tests |
| Review steps, approval by managers only, edits return to draft, version history and text diff | Done | `test_approval_requires_review_steps`, `test_version_compare`, `test_viewer_cannot_approve` |
| Guarded AI narrative (paragraphs with numbers not in the facts discarded) | Done (unit) | `reports/narrative.py`; not run against a live model |
| Organisation branding (colours) on reports | Done | Organisations › Report branding |
| Logo upload for report covers | Not done | Colour branding only |
| Arabic/Dari/Pashto shaping in PDF | Not done | DOCX handles it (Word shapes text); PDF does not shape RTL scripts — see Known Limitations |

## 5. Mixed methods

| Item | Status | Evidence |
|---|---|---|
| Evidence links (indicator/result ↔ theme, relationship), integrated findings approved by managers | Done | Mixed Methods page; `test_mixed_report_builds` |

## 6. Platform, AI, security, deployment

| Item | Status | Evidence |
|---|---|---|
| Local-first AI (Ollama, gemma3:4b default, configurable), health check with actionable errors | Done | AI & Models page |
| External providers: HTTPS only, env switch + app setting + terms approval; Restricted always blocked; no silent fallback | Done | security tests |
| No training / fine-tuning on user data | Done | No such code exists |
| Audit log (security + data events, no content), CSV export | Done | Audit Log page |
| Backups (consistent SQLite snapshot + files) and scheduled backup script | Done | `test_backup_contains_database`, `backup_windows.bat` |
| Windows one-click setup and run (`setup_windows.bat`, `run_windows.bat`), storage on D: via `.env` | Done (not run on Windows here) | Scripts written and reviewed; the build environment is Linux |
| Light/dark mode, reduced motion, focus outlines, Lucide icons, Inter/Vazirmatn fonts, brand assets | Done | Browser screenshots |
| Persistent login across browser refresh | Not done | Refreshing the browser tab signs you out (Streamlit session state); sessions still expire/revoke correctly |
| Password reset by e-mail | Not done | Administrator-issued temporary password with forced change |
| Encryption at rest inside the application | Not done | Use BitLocker on the data drive (documented) |
| Formal certification / compliance | Not claimed | — |

## 7. Phase 2 — one-click adaptive dashboards (3.1.0-alpha)

Tests named below are in `tests/test_dashboard_engine.py`. Full log: `docs/test_evidence/pytest_phase2_2026-11-21.txt` (70 passed).
Datasets: `tests/adaptive_datasets.py` (8 structurally different synthetic sets) and `tests/dtm_workbook.py` (8-sheet DTM-style workbook).

| # | Item | Status | Evidence / notes |
|---|---|---|---|
| 1 | One-click flow: data → theme → Generate Professional Dashboard | Done | Browser run: upload → generate → all pages → PDF → present for WASH (Corporate Light), market prices (Modern Vibrant), student survey (Research & Minimal), DTM (Executive Dark) |
| 2 | Backup before changes; existing data, users and Ollama settings preserved | Done | Git tag `v3.0.0-alpha-pre-phase2`, backup zip; migration 0007 only adds columns |
| 3 | Separate builder (Studio) and full-screen viewer | Done | `ui/pages/studio.py`, `ui/pages/viewer.py` (hidden page `/dashboard`) |
| 4 | Four themes, branding (title, subtitle, organisation, logo upload) | Done | `test_14_all_four_themes_and_branding`; palettes validated for colour-vision deficiency |
| 5 | Sheet detection: main data vs codebook / documentation / lookup / sampling frame / monitoring | Done | `test_02`, `test_03`, `test_04` (10,000-row survey chosen over 55-row codebook) |
| 5 | Domain recognised from content; "General dataset" when evidence is weak | Done | `test_08_domain_recognised_from_content_not_file_names` |
| 5 | Deterministic statistics with tests | Done | `test_07_statistics_match_independent_calculation` (scipy cross-check) |
| 6 | Multi-page dashboards, no empty pages | Done | `test_10_multi_page_dashboards_without_empty_pages` |
| 7 | Varied visuals chosen from the data | Done | `test_09_visuals_chosen_from_the_data` (Likert, pyramid, median-by-group trends, maps only with coordinates) |
| 8 | Eight-part insights per visual | Done | `test_11_every_explanation_has_all_sections_and_only_real_numbers` |
| 9 | No hallucinated numbers; AI rewording optional and number-checked | Done | `test_11`; `reports/narrative.guarded_paragraph` |
| 10 | Filters, cross-filter, drill-down, PDF/Excel/Word export, presentation mode | Done | `test_12`, `test_18`, `test_19`, `test_20`; browser run |
| 11 | Save, reopen, rename, duplicate, theme change, refresh (new version), restore | Done | `test_15`, `test_16`, `test_17` |
| 12 | Navigation: Home, Data Library, Data Intelligence, Dashboard Studio, Qualitative Intelligence, Mixed Methods, Reports, Settings; role-aware; Audit and Organisations under Settings | Done | `ui/app.py`, `ui/pages/hubs.py`; browser run of every page and section |
| 13 | Local Ollama only for optional rewording; caching; Windows scripts | Done (Ollama not run live) | Viewer cache per dashboard version/filters/drill; `.bat` files unchanged |
| 14 | Tests for the 23 scenarios | Done | 26 tests in `test_dashboard_engine.py` |
| — | Adapts across different datasets; no dataset-specific rules | Done for the tested sets | `test_dashboards_differ_across_datasets`, `test_engine_has_no_dataset_specific_rules` |
| — | Missing, invalid and insufficient data handled honestly | Done | `test_21`, `test_22`, `test_23` |
| — | Tested on the real IOM DTM workbook | Not done | Not available; synthetic DTM-style workbook used instead |
| — | Windows verification of phase 2 | Not done | Build environment is Linux |
