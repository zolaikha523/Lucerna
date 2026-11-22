# Architecture

```
Browser ──► Streamlit (app/main.py → lucerna/ui)          one Python process, 127.0.0.1:8501
               │ pages call service functions only
               ▼
        lucerna/services, quant, qual, reports, ai       business logic; every function that touches
               │                                         project data calls rbac.require(user, perm, project)
               ├── SQLite (LUCERNA_DB)                    metadata, users, audit, jobs, codes, quotes, reports
               ├── Parquet files (LUCERNA_ANALYTIC_DIR)   original + analytical copies of each dataset
               ├── Uploads (LUCERNA_UPLOAD_DIR)           original files under server-generated names
               ├── Reports (LUCERNA_REPORT_DIR)           DOCX / PDF / XLSX per version
               └── Ollama (OLLAMA_URL, local)             only through lucerna/ai/providers.py
```

## Packages
| Package | Responsibility |
|---|---|
| `lucerna/config.py` | Settings from environment / `.env`; storage paths; legacy DB fallback |
| `lucerna/db.py` | Connections (WAL, foreign keys), helpers, migration runner |
| `lucerna/security` | Password hashing (PBKDF2, 240k iterations), TOTP MFA, sessions, lockout, RBAC, audit |
| `lucerna/services` | Organisations/projects, uploads, background jobs, mixed-methods links, settings, backups |
| `lucerna/quant` | Ingestion, workbook sheet classification (`workbook.py`), profiling, typing/transformations, quality, statistics, indicators, counting, charts, universal dashboard engine (`engine.py`, `domain.py`), rule-based explanations (`explain.py`), one-click generator service (`generator.py`), comparisons, dashboard persistence |
| `lucerna/qual` | Text extraction (+ optional OCR), segmentation, verification, PII detection, store, AI pipeline |
| `lucerna/ai` | Provider registry, privacy gate, JSON calling with validation/retries, versioned prompts |
| `lucerna/reports` | Content model, quant/qual/mixed builders, DOCX/PDF renderers, static charts, exports, Power BI package, report service (versions, review, approval) |
| `lucerna/ui` | Theme (design tokens, CSS, icons), dashboard themes (`dash_theme.py`), shared widgets, visual renderer, pages (hubs, Studio, full-screen viewer) |

## Key design decisions
- **Two copies of every dataset.** The original upload is parsed once and stored read-only; the analytical copy is
  rebuilt deterministically from (original + confirmed mapping + approved transformations in sequence). Reverting a
  transformation simply rebuilds without it.
- **Rule-based planning, not AI, for dashboards.** `quant/engine.py` classifies variables, recognises the domain from
  the data's own words, and decides pages from feasibility checks. It holds no dataset-specific names (a test enforces
  this). Every number is computed by `quant/charts.py` from the analytical copy. `generator.compute_visual` is the one
  path that the viewer, the exports and the tests all use. Explanations come from `quant/explain.py` rules, and the
  optional AI rewording discards any number not in the facts. The legacy `quant/planner.py` remains for the older
  "AI Auto" spec format.
- **Builder and viewer are separate pages.** `ui/pages/studio.py` builds and manages dashboards. `ui/pages/viewer.py`
  (hidden from navigation, opened at `/dashboard?id=…`) only displays them, and caches computed visuals per
  dashboard version, filter set and drill path.
- **Evidence gate.** Quotations are stored with status `verified | manual_review | rejected`, source offsets, and the
  method used. Reports re-verify the register at build time.
- **Background jobs.** `services/jobs.py` runs long AI work in a thread pool, records stage/progress in the `jobs` table,
  checks a cancel flag and writes checkpoints so a failed run can resume. Jobs running when the app stopped are
  marked failed at the next start.
- **Privacy gate in one place.** All model calls go through `ai/providers.chat_json`, which resolves the provider and
  refuses external providers unless every condition is met. The AI log stores sizes and timings, never content.
- **Compatibility.** `app/core` and `app/exporters` are the original EvidenceQDA modules, kept for the original tests.
