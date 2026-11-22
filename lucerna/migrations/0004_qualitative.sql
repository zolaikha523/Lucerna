-- Pillar 2: qualitative data intelligence and evidence verification.

CREATE TABLE qual_documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  data_file_id INTEGER REFERENCES data_files(id),
  document_code TEXT NOT NULL,          -- stable, unique within the project (e.g. DOC-003)
  title TEXT,
  original_name TEXT,
  doc_type TEXT,                         -- FGD | KII | Interview | Open-ended survey | Consultation | Field notes | Observation | Report | Other
  location TEXT, collection_date TEXT, respondent_group TEXT, language TEXT,
  metadata_json TEXT,
  extraction_method TEXT,                -- txt | docx | pdf_text | ocr
  requires_verification INTEGER DEFAULT 0,  -- 1 when OCR / weak extraction makes verification uncertain
  full_text TEXT NOT NULL,               -- exact extracted text: the verification source of truth
  text_sha256 TEXT, char_count INTEGER, page_count INTEGER,
  status TEXT DEFAULT 'ingested',        -- ingested | coded
  created_by INTEGER, created_at REAL,
  UNIQUE(project_id, document_code)
);

CREATE TABLE qual_segments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES qual_documents(id) ON DELETE CASCADE,
  segment_code TEXT NOT NULL,           -- DOC-003-S0012
  seq INTEGER NOT NULL,
  page INTEGER, paragraph INTEGER,
  speaker TEXT, speaker_role TEXT,      -- moderator | respondent | unknown
  respondent_id TEXT,
  start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,   -- offsets into qual_documents.full_text
  text TEXT NOT NULL,
  UNIQUE(document_id, segment_code)
);
CREATE INDEX ix_qual_segments_doc ON qual_segments(document_id, seq);

CREATE TABLE codebooks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL, version INTEGER DEFAULT 1, status TEXT DEFAULT 'working',
  snapshot_json TEXT, note TEXT,
  created_by INTEGER, created_at REAL
);

CREATE TABLE codes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  definition TEXT,
  category TEXT,                        -- axial category (optional)
  origin TEXT NOT NULL DEFAULT 'ai',    -- ai | manual
  status TEXT NOT NULL DEFAULT 'suggested',   -- suggested | approved | rejected | merged
  merged_into INTEGER REFERENCES codes(id),
  prompt_version TEXT,
  created_by INTEGER, created_at REAL,
  reviewed_by INTEGER, reviewed_at REAL, updated_at REAL
);
CREATE INDEX ix_codes_project ON codes(project_id, status);

CREATE TABLE code_applications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code_id INTEGER NOT NULL REFERENCES codes(id) ON DELETE CASCADE,
  segment_id INTEGER NOT NULL REFERENCES qual_segments(id) ON DELETE CASCADE,
  origin TEXT DEFAULT 'ai',
  status TEXT DEFAULT 'suggested',      -- suggested | approved | rejected
  created_by INTEGER, created_at REAL,
  UNIQUE(code_id, segment_id)
);

CREATE TABLE themes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,   -- non-null = subtheme
  name TEXT NOT NULL,
  definition TEXT,
  analytic_explanation TEXT,
  limitations TEXT,
  origin TEXT DEFAULT 'ai',
  status TEXT DEFAULT 'suggested',      -- suggested | approved | rejected
  sort_order INTEGER DEFAULT 0,
  created_by INTEGER, created_at REAL, reviewed_by INTEGER, reviewed_at REAL, updated_at REAL
);
CREATE TABLE theme_codes(
  theme_id INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
  code_id INTEGER NOT NULL REFERENCES codes(id) ON DELETE CASCADE,
  PRIMARY KEY(theme_id, code_id)
);

CREATE TABLE quotations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  document_id INTEGER REFERENCES qual_documents(id) ON DELETE CASCADE,
  segment_id INTEGER REFERENCES qual_segments(id) ON DELETE CASCADE,
  claimed_segment_code TEXT,            -- what the AI/analyst claimed, kept for audit
  code_id INTEGER REFERENCES codes(id) ON DELETE SET NULL,
  theme_id INTEGER REFERENCES themes(id) ON DELETE SET NULL,
  candidate_text TEXT NOT NULL,         -- exactly as proposed (never edited)
  verified_text TEXT,                   -- exact substring of the source (only when verified)
  verification_status TEXT NOT NULL,    -- verified | rejected | manual_review
  verification_method TEXT,             -- exact | normalized_whitespace | normalized_quotes | none
  match_start INTEGER, match_end INTEGER,    -- offsets in qual_documents.full_text
  rejection_reason TEXT,
  origin TEXT DEFAULT 'ai',             -- ai | manual
  analyst_decision TEXT DEFAULT 'pending',   -- pending | approved | excluded
  reviewed_by INTEGER, reviewed_at REAL,
  translation_text TEXT, translation_language TEXT, translation_by TEXT,
  created_at REAL
);
CREATE INDEX ix_quotations_project ON quotations(project_id, verification_status);

CREATE TABLE analytic_notes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  theme_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,          -- ai_summary | interpretation | researcher_conclusion | contradiction | negative_case | evidence_gap | recommendation | mixed_methods
  text TEXT NOT NULL,
  origin TEXT DEFAULT 'ai',    -- ai | analyst
  status TEXT DEFAULT 'draft', -- draft | approved | excluded
  segment_ids_json TEXT,       -- supporting segment ids (validated)
  priority TEXT, stakeholder TEXT, follow_up TEXT,
  created_by INTEGER, created_at REAL, reviewed_by INTEGER, reviewed_at REAL
);
