# Lucerna — Development Handover

Date: 2026-11-21 · Version 3.1.0-alpha (phase 2) · Source: EvidenceQDA Enterprise v2 (checkpointed as the first git commit).

## 0. Phase 2 summary (3.1.0-alpha)
- **One-click dashboards.** Dashboard Studio › Generate: pick data, pick one of four themes, generate. The finished
  dashboard opens in a separate full-screen viewer with filters, cross-filtering, drill-down, eight-part insights per
  visual, PDF/Excel/Word export and presentation mode. Details: `docs/DASHBOARD_BUILDER.md`.
- **Universal engine, not sector templates.** `quant/workbook.py` classifies every sheet (main data, codebook,
  documentation, lookup, sampling frame, monitoring). `quant/engine.py` builds pages from variable roles and
  feasibility checks, and `quant/domain.py` names the domain from the data's own words. A test fails if dataset-specific
  names appear in this code.
- **Evidence.** 70 automated tests pass (`docs/test_evidence/pytest_phase2_2026-11-21.txt`), including 26 for the
  23 required scenarios on 9 structurally different synthetic datasets. A browser run uploaded and generated
  dashboards in all four themes, opened every page, exported a PDF, and entered presentation mode.
- **Not verified.** The real IOM DTM workbook (not available), Windows, a live Ollama model, and map tiles offline.
- **Navigation** is now Home, Data Library, Data Intelligence, Dashboard Studio, Qualitative Intelligence, Mixed
  Methods, Reports, Settings. Audit Log and Organisations sit under Settings and are shown only to administrators.
- **Changed and created files:** `docs/PHASE2_CHANGES.md`.
- **Backup before phase 2:** git tag `v3.0.0-alpha-pre-phase2` and `Lucerna_backup_before_phase2_2026-11-21.zip`.

## 1. Status in one paragraph
Lucerna turns the EvidenceQDA transcript tool into a two-pillar platform. The quantitative pillar (ingestion,
mapping, quality and cleaning, statistics, indicators, adaptive and custom dashboards, comparisons, exports,
Power BI package) and the qualitative pillar (transcripts, speaker-turn segmentation, AI-assisted and manual
coding, themes, strict quotation verification, evidence Q&A) are implemented, together with mixed-methods
links, a report centre with review and approval, RBAC with organisation/project isolation, MFA, sessions,
audit, privacy controls, backups and a branded light/dark interface. 44 automated tests pass. The AI features
were tested with a deterministic stand-in, **not** a live Ollama model, and the Windows scripts were not run on
Windows. See `docs/IMPLEMENTATION_CHECKLIST.md` for item-by-item status and `docs/KNOWN_LIMITATIONS.md`.

## 2. Technical changes from EvidenceQDA
- New package `lucerna/` (≈ 10,000 lines of Python): `security/`, `services/`, `quant/`, `qual/`, `ai/`, `reports/`, `ui/`.
- `app/main.py` is now a thin entry point. The previous interface is kept as `app/legacy_evidenceqda_main.py`;
  `app/core` and `app/exporters` are unchanged so the original tests still pass.
- Versioned migrations `lucerna/migrations/0001–0006.sql`. An existing `data/evidenceqda.sqlite3` is used and
  migrated in place when no Lucerna database exists (users, audit and chats are preserved).
- Background job runner (`services/jobs.py`) with progress, cancel, checkpoint/resume.
- Fixes for all 18 audit findings except those listed as gaps (see checklist).

## 3. Test evidence
- `python -m pytest tests -v` → **44 passed** (37 new + 7 original). Log: `docs/test_evidence/pytest_2026-11-21.txt`.
- Live browser run (Playwright, Chromium): all 23 pages load without exceptions in light and dark mode with the
  synthetic demo workspace (`python -m tests.seed_demo`).
- Generated quantitative and qualitative PDF/DOCX reports were rendered and visually checked.

## 4. How to run
1. Windows: double-click `setup_windows.bat`, then `run_windows.bat`; open http://localhost:8501.
2. First start: create the system administrator and organisation.
3. Install Ollama and run `ollama pull gemma3:4b` for AI features; check it under Settings › AI & Models.
4. Optional demo data: `python -m tests.seed_demo` (fictional data, user `admin` / `Lucerna-Demo-2026!`)
   — use a separate `LUCERNA_DATA_DIR`, never your production data folder.

## 5. How to use (short)
Fastest: Dashboard Studio › Generate. Full route: Settings › Projects → Data Library (upload) → Data Intelligence
(Understanding & Mapping, Quality & Cleaning, Indicators) → Dashboard Studio → Reports. For qualitative work: Documents → Coding & Codebook
(AI coding + review) → Themes & Findings → Quotations & Evidence (approve verified quotes) → Report Centre.
Full guide: `docs/USER_GUIDE.md`.

## 6. Remaining work (priority order)
1. Run with a live Ollama model on the target laptop; tune `MAX_SEGMENTS_PER_LLM_BATCH`, timeouts and prompts
   (`lucerna/ai/prompts.py`, versioned) against real transcripts; record results.
2. Run `setup_windows.bat` / `run_windows.bat` on Windows 11 and fix any environment issue.
3. Boundary-file (GeoJSON) upload per project for choropleth maps.
4. RTL shaping in PDF (e.g. `arabic-reshaper` + `python-bidi`) or a Word→PDF route.
5. Logo on Report Centre reports (dashboards already support it); one-click FCS/rCSI template application.
8. Test the dashboard engine on real workbooks (starting with the IOM DTM workbook) and record any sheet or variable it misreads.
6. Persistent login across refresh (signed cookie) if users need it.
7. Survey-design-aware tests (clustered/stratified) if programmes require them.

## 7. Where things are
| Topic | File |
|---|---|
| Architecture | `docs/ARCHITECTURE.md` |
| Installation (Windows) | `docs/INSTALLATION_WINDOWS.md` |
| User guide / quant / qual / dashboards / reports | `docs/USER_GUIDE.md`, `docs/QUANTITATIVE_GUIDE.md`, `docs/QUALITATIVE_GUIDE.md`, `docs/DASHBOARD_BUILDER.md`, `docs/REPORTS.md` |
| AI configuration | `docs/AI_CONFIGURATION.md` |
| Security & privacy | `docs/SECURITY_AND_PRIVACY.md` |
| Database | `docs/DATABASE.md` |
| Troubleshooting | `docs/TROUBLESHOOTING.md` |
| Backup & recovery | `docs/BACKUP_AND_RECOVERY.md` |
| Deployment checklist | `DEPLOYMENT_CHECKLIST.md` |
| Testing | `docs/TESTING.md` |
| Brand | `docs/BRAND_GUIDE.md` |
