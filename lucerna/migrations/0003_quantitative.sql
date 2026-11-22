-- Pillar 1: quantitative data intelligence.

CREATE TABLE data_files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  original_name TEXT NOT NULL,
  stored_path TEXT NOT NULL,          -- immutable original upload; never modified
  sha256 TEXT NOT NULL,
  size_bytes INTEGER,
  extension TEXT,
  purpose TEXT,                       -- quantitative | qualitative
  uploaded_by INTEGER, uploaded_at REAL
);
CREATE INDEX ix_data_files_project ON data_files(project_id);

CREATE TABLE datasets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  data_file_id INTEGER REFERENCES data_files(id),
  name TEXT NOT NULL,
  source_table TEXT,                  -- worksheet / table name within the file
  original_path TEXT,                 -- parquet snapshot of the parsed original (read-only)
  analytic_path TEXT,                 -- parquet analytical copy (transformations applied)
  row_count INTEGER, column_count INTEGER,
  unit_of_analysis TEXT,              -- household | individual | assistance_event | respondent | movement | visit | case | other | unknown
  unit_confirmed INTEGER DEFAULT 0,
  sector_guess TEXT, sector_confirmed TEXT,
  round_label TEXT, period_label TEXT,
  profile_json TEXT,                  -- deterministic profile (types, missingness, roles...)
  quality_json TEXT,
  version INTEGER DEFAULT 1,
  status TEXT DEFAULT 'uploaded',     -- uploaded | mapped | cleaned | analysed
  created_by INTEGER, created_at REAL, updated_at REAL
);
CREATE INDEX ix_datasets_project ON datasets(project_id);

CREATE TABLE dataset_columns(
  dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  position INTEGER,
  inferred_type TEXT,                 -- numeric | integer | categorical | text | date | boolean | identifier | multiselect | coordinate
  inferred_role TEXT,                 -- identifier | date | geo_admin1 | geo_admin2 | geo_admin3 | latitude | longitude | sex | age | age_group | household_size | measure | category | multiselect | free_text | weight
  confidence REAL,
  final_type TEXT, final_role TEXT,
  label TEXT,
  confirmed INTEGER DEFAULT 0,
  confirmed_by INTEGER, confirmed_at REAL,
  notes TEXT,
  PRIMARY KEY(dataset_id, name)
);

CREATE TABLE transformations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  operation TEXT NOT NULL,
  params_json TEXT,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'proposed',   -- proposed | approved | applied | rejected | reverted
  rows_affected INTEGER,
  cells_affected INTEGER,
  created_by INTEGER, created_at REAL,
  approved_by INTEGER, approved_at REAL,
  applied_at REAL
);
CREATE INDEX ix_transformations_dataset ON transformations(dataset_id, seq);

CREATE TABLE indicators(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
  code TEXT,
  name TEXT NOT NULL,
  definition TEXT,
  indicator_type TEXT NOT NULL,   -- percentage | count | count_unique | mean | median | sum | ratio
  unit TEXT,
  numerator_json TEXT,            -- {"column":..., "op": "in|==|>=|<=|>|<|notnull", "value": ...}
  denominator_json TEXT,          -- {"column":..., "op": ...} or null = all valid rows
  value_column TEXT,              -- for mean/median/sum/count_unique
  disaggregations TEXT,           -- JSON list of columns
  baseline REAL, baseline_source TEXT,
  target REAL, target_source TEXT,
  reporting_period TEXT,
  data_source TEXT,
  responsible TEXT,
  calculation_notes TEXT,
  status TEXT DEFAULT 'provisional',   -- provisional | configured | verified
  origin TEXT DEFAULT 'manual',        -- manual | suggested
  verified_by INTEGER, verified_at REAL,
  created_by INTEGER, created_at REAL, updated_at REAL
);
CREATE INDEX ix_indicators_project ON indicators(project_id);

CREATE TABLE indicator_results(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  indicator_id INTEGER NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
  dataset_id INTEGER, dataset_version INTEGER,
  computed_at REAL,
  value REAL, numerator REAL, denominator REAL, n_valid INTEGER, n_missing INTEGER,
  disaggregation_json TEXT,
  config_hash TEXT
);

CREATE TABLE dashboards(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
  compare_dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  mode TEXT NOT NULL,           -- auto | custom | comparative
  spec_json TEXT NOT NULL,
  plan_json TEXT,
  version INTEGER DEFAULT 1,
  is_template INTEGER DEFAULT 0,
  created_by INTEGER, created_at REAL, updated_at REAL
);
CREATE TABLE dashboard_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dashboard_id INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
  version INTEGER, spec_json TEXT, note TEXT, created_by INTEGER, created_at REAL
);
CREATE TABLE dashboard_bookmarks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dashboard_id INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
  name TEXT, page_index INTEGER, filters_json TEXT, created_by INTEGER, created_at REAL
);
