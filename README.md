<p align="center"><img src="assets/brand/lucerna-logo-horizontal-light.png" alt="Lucerna — From Data to Decisions" width="320"></p>

# Lucerna — From Data to Decisions

Lucerna is a local-first data intelligence platform for humanitarian and development teams. It brings two kinds of
evidence together in one place:

- **Quantitative** — surveys, monitoring and registration data: ingestion, data understanding, quality and cleaning
  with an audit trail, deterministic statistics, indicators, one-click adaptive multi-page dashboards (four themes, full-screen viewer, PDF/Excel/Word export, presentation mode), comparisons, and a Power BI package.
- **Qualitative** — FGD and KII transcripts: speaker-aware segmentation, AI-assisted and manual coding, themes, and
  quotations that are verified character-by-character against the source.

Both feed **mixed-methods findings** and **donor-ready reports** (Word, PDF, Excel) with review and approval.
AI runs on your computer through Ollama by default; nothing is sent elsewhere unless an administrator deliberately allows it.

Lucerna is the successor of EvidenceQDA Enterprise v2 and keeps its evidence gate and data.

## Quick start (Windows)
1. Install Python 3.12/3.13 (add to PATH) and Ollama; run `ollama pull gemma3:4b`.
2. Double-click `setup_windows.bat`, then `run_windows.bat`.
3. Open http://localhost:8501 and create the administrator account.

Linux/macOS: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && streamlit run app/main.py`.

## Principles
- Numbers are calculated, never generated. Every chart shows its base (n).
- Quotations are exact source text or they are not used.
- AI output is a draft until a person approves it. Lucerna does not invent targets, baselines, methods or recommendations.
- Originals are never modified; every cleaning step is recorded and reversible.

## Documentation
Start with [`docs/HANDOVER.md`](docs/HANDOVER.md) (status, how to run, remaining work),
[`docs/IMPLEMENTATION_CHECKLIST.md`](docs/IMPLEMENTATION_CHECKLIST.md) and [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
Guides: installation, user guide, quantitative, qualitative, dashboards, reports, AI configuration, security & privacy,
database, troubleshooting, backup & recovery, testing, brand — all in [`docs/`](docs/).

## Tests
`python -m pytest tests -v` — 44 tests on synthetic data (all passing on 2026-11-21).

## Licences
Application code: as provided by the owner. Bundled: Inter and Vazirmatn fonts (SIL OFL), DejaVu fonts (free licence), Lucide icons (ISC).
