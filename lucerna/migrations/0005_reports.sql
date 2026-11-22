CREATE TABLE reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                 -- quantitative | qualitative | mixed
  title TEXT NOT NULL,
  template TEXT,
  status TEXT NOT NULL DEFAULT 'draft',   -- draft | in_review | approved
  metadata_json TEXT,
  current_version INTEGER DEFAULT 0,
  created_by INTEGER, created_at REAL, updated_at REAL,
  approved_by INTEGER, approved_at REAL
);
CREATE TABLE report_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  content_json TEXT NOT NULL,          -- full structured content (sections) used to render
  docx_path TEXT, pdf_path TEXT, xlsx_path TEXT,
  note TEXT,
  created_by INTEGER, created_at REAL
);
CREATE TABLE report_reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  step TEXT NOT NULL,                  -- evidence | themes | quotations | findings | recommendations | edit | approval
  decision TEXT NOT NULL,              -- completed | changes_requested
  note TEXT,
  reviewer_id INTEGER, ts REAL
);
