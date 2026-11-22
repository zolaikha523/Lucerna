# Known Limitations

Lucerna is honest about what it does not do. These are the current limits (2026-11-21, version 3.1.0-alpha).

## Not tested in the build environment
- **Live local model.** AI coding, theme analysis, Evidence Q&A and AI narrative were tested with a
  deterministic stand-in (`tests/fake_llm.py`), not with Ollama/gemma3:4b. Output quality of the real model,
  its speed on your hardware, and how often it returns malformed JSON are unknown until you run it.
  Malformed output is retried (`LLM_JSON_RETRIES`) and then reported as a failure, never silently accepted.
- **Windows.** The `.bat` scripts were written for Windows but the build ran on Linux. Run `setup_windows.bat`
  and report any error message.
- **OCR.** Scanned-PDF OCR depends on the optional Tesseract install and was not tested with a real scan.
- **Real workbooks.** The dashboard engine was tested on 10 synthetic datasets with different structures: a
  DTM-style 8-sheet workbook, WASH camps, food security, MPCA PDM, a student survey, market prices, a factory
  maintenance log, plus tiny, invalid and phase-1 sets. It has **not** been tested on the real IOM DTM workbook or any
  other real dataset. Passing these tests shows it adapts across these structures. It does not prove it adapts to
  every dataset.
- **Map tiles need internet.** Point maps use online map tiles; offline, the points draw without a background map.

## Functional gaps
- **No drag-and-drop dashboard canvas.** Streamlit does not provide one. Dashboard Studio uses a 12-column grid:
  reorder visuals with arrows and choose widths (quarter, third, half, two-thirds, full).
- **No .pbix file.** The Power BI package contains data, Power Query scripts, DAX, relationships and a theme. You
  assemble the report in Power BI Desktop (README inside the ZIP).
- **Choropleth maps need boundary files, and there is no upload screen for them yet.** Point maps work from
  validated latitude/longitude columns. Lucerna will not draw invented boundaries.
- **PDF reports do not shape Arabic-script text** (Dari, Pashto, Arabic): letters may appear unjoined in the PDF.
  Use the Word (DOCX) output for these languages, or export Word to PDF.
- **Logos.** Dashboards accept a PNG or JPEG logo (under 1 MB, checked by signature and image decoding). Word and
  PDF *reports* from the Report Centre still use organisation colours only. Lucerna does not supply any
  organisation's official logo. Upload only logos you are entitled to use.
- **Domain recognition is vocabulary-based.** It scores keywords in column names, labels and values. Datasets with
  cryptic codes (e.g. `q1`, `v203`) and no codebook will usually show "General dataset". Confirming labels or
  attaching a codebook improves this.
- **Dashboards are generated, not hand-designed.** Layout follows fixed rules (KPI rows, a 12-column grid, at most 8
  charts per page). Very wide surveys can produce 12–14 pages, and the page tabs then wrap onto two rows.
- **No PBIX.** Dashboard exports are PDF, Excel and Word. The separate Power BI package is unchanged.
- **Refreshing the browser tab signs you out.** Streamlit keeps the session token in the tab's memory. Sessions still
  expire (`LUCERNA_SESSION_HOURS`) and can be revoked.
- **Password reset is administrator-issued** (temporary password with forced change). There is no e-mail system.
- **Sector templates** (FCS, rCSI) provide documented weights; applying them is done by creating a weighted-sum
  transformation, not a one-click template.
- **Single-machine deployment.** SQLite and a local job pool suit one office computer or a small server. Many
  simultaneous users or very large datasets (millions of rows) would need PostgreSQL and a job queue.
- **Encryption at rest** is delegated to the operating system (BitLocker). The database itself is not encrypted.

## Analytical boundaries (by design)
- Counts of documents/speakers in qualitative evidence are **not** prevalence estimates.
- Statistical tests assume independent samples unless stated; survey design effects (clustering, stratification)
  are not modelled. Weighted descriptives are available; weighted significance tests are not.
- Forecasts are only offered with at least 12 monthly observations and are labelled as projections.
- Lucerna does not write recommendations or conclusions on its own; they come from analysts.
- No formal certification or compliance (e.g. ISO 27001, GDPR certification) is claimed.
