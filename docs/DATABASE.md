# Database

SQLite file at `LUCERNA_DB` (WAL mode, foreign keys on). Large tables of data are stored as Parquet files; the database
keeps metadata and paths. Migrations live in `lucerna/migrations/NNNN_name.sql` and are applied once, in order, recorded in
`schema_migrations`. Never edit an applied migration; add a new one.

| Migration | Tables |
|---|---|
| 0001 legacy | users, sessions, audit, privacy settings, incidents, chats (EvidenceQDA schema, created if missing) |
| 0002 core | organizations, org_members, projects (rebuilt with org_id, classification…), project_members, login_attempts, app_settings, jobs, ai_providers, ai_runs; new columns on users, sessions, audit |
| 0003 quantitative | data_files, datasets, dataset_columns, transformations, indicators, indicator_results, dashboards, dashboard_versions, dashboard_bookmarks |
| 0004 qualitative | qual_documents, qual_segments, codebooks, codes, code_applications, themes, theme_codes, quotations, analytic_notes |
| 0005 reports | reports, report_versions, report_reviews |
| 0006 mixed methods | evidence_links |

Inspect with any SQLite browser (read-only while Lucerna runs). Back up with **Privacy & System › Backups** or `backup_windows.bat`
(uses SQLite's online backup API, safe while running).
