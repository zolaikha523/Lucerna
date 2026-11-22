CREATE TABLE evidence_links(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  indicator_id INTEGER REFERENCES indicators(id) ON DELETE CASCADE,
  quant_statement TEXT,                -- a computed quantitative result (snapshot text with n)
  dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
  theme_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL,          -- supports | explains | contradicts | complements | unclear
  analyst_note TEXT,
  integrated_finding TEXT,
  status TEXT DEFAULT 'draft',         -- draft | approved
  created_by INTEGER, created_at REAL, reviewed_by INTEGER, reviewed_at REAL
);
