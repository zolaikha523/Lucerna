# User Guide

## Signing in
Use the account your administrator created. On first sign-in with a temporary password you must choose your own.
Turn on two-step verification under **My Account**. Refreshing the browser tab signs you out; just sign in again.

## The sidebar
- **Project** — everything you see belongs to the selected project.
- **Your name** — dark mode and sign out.
- Navigation (only what your role can use is shown): **Home**, **Data Library**, **Data Intelligence**
  (Understanding & Mapping, Quality & Cleaning, Statistical Analysis, Indicators, Comparisons), **Dashboard Studio**,
  **Qualitative Intelligence** (Documents, Coding & Codebook, Themes & Findings, Quotations & Evidence, Evidence Q&A),
  **Mixed Methods**, **Reports**, **Settings** (My Account, Projects; and, for administrators, AI & Models, Privacy &
  System, Organisations, Users & Permissions, Audit Log).

## Fastest route: a dashboard in one click
**Dashboard Studio › Generate**: upload or pick a dataset, choose a theme, click **Generate Professional Dashboard**.
For multi-sheet workbooks Lucerna picks the main data sheet itself and explains why (open **How Lucerna read this
workbook**). See `docs/DASHBOARD_BUILDER.md`.

## Typical quantitative workflow
1. **Data Library** — upload a file. Each sheet/table becomes a dataset. The original is never changed.
2. **Data Intelligence › Understanding & Mapping** — check every column's type and role, the unit of analysis (what one row is) and sector. Click **Confirm mapping**.
3. **Data Intelligence › Quality & Cleaning** — review findings, preview and approve fixes. Every change is listed in the history and can be reverted.
4. **Data Intelligence › Indicators** — define indicators (numerator, denominator, disaggregation). Targets and baselines are only those you enter.
5. **Dashboard Studio** — generate a dashboard (rule-based, no AI needed) or build your own under **Custom editor**. Open it in the full-screen viewer; click a bar to cross-filter, export PDF/Excel/Word, or present.
6. **Data Intelligence › Statistical Analysis** and **Comparisons** for tests and round comparisons.
7. **Reports** — create the report, fill in methodology fields, generate, review, approve, download.

## Typical qualitative workflow
1. **Documents** — upload transcripts. Speakers, pages and paragraphs are detected; check the metadata.
2. **Coding & Codebook** — start AI coding (runs in the background) or code manually. Approve, rename, merge, split or reject codes. Save snapshots.
3. **Themes & Findings** — organise codes into themes and subthemes; review AI summaries (drafts) and add your interpretations, conclusions and recommendations.
4. **Quotations & Evidence** — approve verified quotations for reports, resolve manual-review items, add translations.
5. **Evidence Q&A** — ask questions answered only from cited segments.
6. **Reports** — qualitative report with the full donor structure.

## Roles
| Role | Can |
|---|---|
| Project Manager | everything in the project, incl. members, deleting data, approving reports |
| MEAL Manager | analysis, indicators (and verify), dashboards, coding, reports and approval |
| MEAL Officer | analysis, indicators, dashboards, coding, reports (no approval) |
| Researcher / Analyst | analysis, dashboards, coding, quotes, reports (no indicator management, no approval) |
| Data Collector | view and upload data |
| Viewer | view and export |
Organisation administrators manage their organisation's projects and members. System administrators manage the installation.
