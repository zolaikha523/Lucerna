# Stage 1 Audit — EvidenceQDA Enterprise v2 (as received)

Audit date: 2026-11-21. Source: `EvidenceQDA_Enterprise_v2_Final.zip` (19 files, 176 KB).
A git checkpoint of the untouched source is the first commit in this repository
(`Checkpoint: original EvidenceQDA Enterprise v2 source as received`).

## 1. Structure found

| Path | Purpose |
|---|---|
| `app/main.py` (440 lines) | Single Streamlit script: login, upload, analysis, 9 pages, all UI |
| `app/core/ingest.py` | TXT/DOCX/PDF text extraction, SHA-256 fingerprint, deterministic chunking |
| `app/core/llm.py` | Ollama `/api/chat` client, open coding, axial themes, evidence Q&A |
| `app/core/validator.py` | Quote verification (exact / whitespace-normalised), code & theme reference filtering |
| `app/core/security.py` | SQLite schema, PBKDF2 hashing, TOTP MFA, sessions, audit, privacy, incidents, chats |
| `app/exporters/reports.py` | DOCX / Markdown / XLSX / CSV qualitative report package |
| `tests/test_quality_gate.py` | 7 unit tests (mocked LLM) |
| `run_windows.bat`, `setup_windows.bat` | Windows launch & install |
| README, SECURITY, DEPLOYMENT_CHECKLIST, `.env.example` | Docs/config |

Entry point: `python -m streamlit run app\main.py`. Architecture: one Streamlit process,
session-state storage of analysis, one SQLite database for users/audit/chats.

## 2. What was run

* `python -m unittest discover -s tests -v` → **7/7 passed** (Python 3.13, pandas 3.0).
* `streamlit run app/main.py` → **starts, HTTP 200**.
* Live Ollama was not available in the audit environment, so real model runs were not tested.

## 3. Working functionality worth preserving

* Quote gate: a quote is accepted only if its `segment_id` exists and the quote is an exact
  (or whitespace-normalised) substring of that segment. Rejected candidates are held apart.
* Code/theme reference filtering (codes linked to non-existent segments are dropped).
* Deterministic segment IDs and SHA-256 source fingerprints.
* Report exporter that writes "Not provided" instead of inventing methodology.
* PBKDF2 password hashing, TOTP implementation, audit table.
* Honest status handling (failed / partial analysis surfaced to the user).

## 4. Broken, incomplete or weak areas

| # | Area | Finding | Severity |
|---|---|---|---|
| A1 | Scope | No quantitative pillar at all (no dataset ingestion, statistics, dashboards, indicators). | Critical (missing) |
| A2 | Persistence | Analysis, segments, codes, themes, quotes and report metadata live only in Streamlit session state; lost on refresh/restart. | High |
| A3 | Projects | `projects` table exists but is never used; no organisations, no project isolation. | High |
| A4 | RBAC | Single role. First user is admin; no roles/permissions; no backend authorisation checks. | High |
| A5 | MFA | "Enable MFA" stores the secret **before** the user confirms a code, so a user who never confirms is locked into MFA. Disabling MFA requires no re-authentication. | High |
| A6 | Sessions | Session rows are created but never checked; revoking a "device" has no effect; no expiry. | High |
| A7 | Login | No throttling / lockout on failed logins. | Medium |
| A8 | Uploads | No size or type validation beyond extension; filenames used as document IDs (two files with the same stem collide); uploads overwrite each other. | Medium |
| A9 | Segmentation | Paragraph chunking with 350-char overlap: overlapping text appears in two segments, so one quote can be "verified" in two places; segment offsets fall back to `0` when not located; no page numbers, paragraph numbers or speaker attribution. | Medium |
| A10 | Verification | Normalised matching is not recorded with the source span; no OCR-uncertainty state; no manual-review state. | Medium |
| A11 | Coding | No codebook editing (merge/split/rename/approve/reject), no versioning; analyst decisions cannot be recorded. | High |
| A12 | Theme→quote mapping | Quotes are mapped to themes by lower-cased code name only; quotes whose code string differs slightly become "Unclassified". | Low |
| A13 | LLM | `LLM_JSON_RETRIES=1` means no retry; `num_gpu: 0` hard-coded (forces CPU for every user); single provider; no prompt versioning; no execution log. | Medium |
| A14 | Processing | Analysis runs synchronously inside the Streamlit request; no progress, cancellation, or checkpoint — long runs block the UI. | High |
| A15 | Reports | Single Word layout, no TOC, no page numbers, no PDF, no cover page branding, no review/approval workflow. | Medium |
| A16 | Privacy flags | `local_only` / `external_ai_approved` settings are stored but never enforced anywhere. | Medium |
| A17 | Dependencies | `pandas<3` pin but code works on pandas 3; no plotting/statistics libraries. | Low |
| A18 | Path hygiene | `sys.path.insert(ROOT)` but imports rely on Streamlit adding `app/` — works only when launched via Streamlit. | Low |

## 5. Decision: architecture for Lucerna

* **Keep Python + Streamlit + SQLite.** The user runs on Windows with a one-click `.bat`
  workflow; a Python-only stack keeps that working without Node.js tooling. Streamlit is
  extended with a custom design system (CSS), Plotly for interactive visuals and
  matplotlib for static exports.
* **Move business logic into a `lucerna/` package** separated into `security`, `quant`,
  `qual`, `ai`, `reports`, `services`, `ui`. The original `app/core` and `app/exporters`
  modules are kept as thin compatibility shims so the existing tests and any scripts keep working.
* **Versioned SQL migrations** (`lucerna/migrations/*.sql`, `schema_migrations` table) instead of
  ad-hoc `CREATE TABLE IF NOT EXISTS`. The original tables are kept and migrated in place.
* **Background job runner** (thread pool with job table, progress stages, cancellation flags)
  so long AI runs do not block the UI.

The implementation checklist that follows from this audit is `docs/IMPLEMENTATION_CHECKLIST.md`.
