# Phase 2 (3.1.0-alpha): changed and created files

Baseline: git tag `v3.0.0-alpha-pre-phase2` (backup zip `Lucerna_backup_before_phase2_2026-11-21.zip`).
Run `git diff --stat v3.0.0-alpha-pre-phase2` for the full list with line counts.

## Created
| File | Purpose |
|---|---|
| `lucerna/quant/workbook.py` | Sheet classification (main data, codebook, documentation, lookup, sampling frame, monitoring, indicator map), primary-sheet choice, relationship detection by value overlap, codebook labels |
| `lucerna/quant/domain.py` | Domain recognition from the data's own words; topic grouping; plain-language names |
| `lucerna/quant/engine.py` | Universal dashboard engine: variable roles, feasibility checks, page and visual selection |
| `lucerna/quant/explain.py` | Eight-part rule-based explanation for every visual type; optional guarded AI rewording |
| `lucerna/quant/generator.py` | One-click generation service: themes, branding, logos, refresh, versions, `compute_visual` |
| `lucerna/migrations/0007_dashboard_engine.sql` | Adds columns only: workbook analysis, sheet roles, dashboard theme/branding/links/source version |
| `lucerna/reports/dashboard_export.py` | Dashboard export to PDF, Excel and Word (permission-checked, audited) |
| `lucerna/ui/dash_theme.py` | The four dashboard themes (design tokens and CSS) |
| `lucerna/ui/pages/studio.py` | Dashboard Studio: Generate, My dashboards, Custom editor |
| `lucerna/ui/pages/viewer.py` | Full-screen dashboard viewer and presentation mode |
| `lucerna/ui/pages/hubs.py` | Data Intelligence, Qualitative Intelligence and Settings hubs |
| `lucerna/ui/static/icons/*.svg` (15) | Additional Lucide icons (ISC licence, see `LICENSE-lucide.txt`) |
| `tests/dtm_workbook.py`, `tests/fixtures/SYNTHETIC_DTM_practice_workbook.xlsx` | Synthetic 8-sheet DTM-style workbook with planted data problems |
| `tests/adaptive_datasets.py`, `tests/fixtures/adaptive/*` | 8 structurally different synthetic datasets (WASH camps, food security, MPCA PDM, student survey, market prices, factory maintenance log, tiny, invalid values) |
| `tests/test_dashboard_engine.py` | 26 tests covering the 23 required scenarios, plus adaptivity and no-dataset-specific-rules checks |
| `lucerna/demo.py`, `docs/DEMO_STREAMLIT_CLOUD.md` | Optional public demo mode (synthetic data, `LUCERNA_DEMO_MODE=1`) |
| `docs/PHASE2_CHANGES.md`, `docs/test_evidence/pytest_phase2_2026-11-21.txt` | This list; test log |

## Changed
| File | Change |
|---|---|
| `lucerna/quant/charts.py` | New visual types (multi-line, comparison table, methodology); excludes "not applicable" answers from denominators; duplicate-ID KPI; theme palettes; readable p-values; stacked legend order |
| `lucerna/quant/palette.py` | Palettes for the four themes (validated for colour-vision deficiency) |
| `lucerna/quant/profile.py` | Origin/destination detection before admin levels; camp, block, ward and market recognised as locations; respondent-level unit guess |
| `lucerna/quant/stats.py` | Weeks run Monday to Sunday and are labelled by their Monday |
| `lucerna/quant/store.py` | Workbook analysis at import; sheet roles; codebook labels; main sheet listed first |
| `lucerna/quant/dashboards.py` | Auto-generation delegates to the generator; duplicate keeps theme, branding and links |
| `lucerna/reports/static_charts.py` | Box, multi-line and treemap static charts; wrapped heat-map labels |
| `app/main.py` | Seeds the synthetic demo only when demo mode is switched on |
| `lucerna/ui/app.py`, `lucerna/ui/common.py`, `lucerna/ui/theme.py` | New role-aware navigation; page links; embedded hub sections; demo notice on the login page in demo mode |
| `lucerna/ui/pages/home.py`, `lucerna/ui/pages/quant.py` | Dashboards card on Home; sheet type and workbook explanation in the Data Library |
| `lucerna/qual/store.py`, `lucerna/qual/verify.py`, `lucerna/quant/quality.py`, `lucerna/reports/exports.py`, `lucerna/reports/render_docx.py` | One unused import removed from each; no behaviour change |
| `lucerna/__init__.py` | Version 3.1.0-alpha |
| `tests/seed_demo.py`, `tests/test_lucerna.py` | Demo seeds the DTM-style workbook and an Executive Dark dashboard; one page-title assertion updated |
| `docs/*` | Dashboard guide rewritten; user guide, architecture, handover, checklist and known limitations updated; "Workspace ›" menu references now read "Settings ›" |

## Unchanged on purpose
`app/core`, `app/exporters`, the original EvidenceQDA tests, the Windows `.bat` scripts, the `.env` settings, the
security and AI provider code, and the data folders. No user data is deleted or moved by this version. Migration 0007
only adds columns.
