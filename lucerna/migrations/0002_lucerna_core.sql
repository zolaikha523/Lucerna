-- Lucerna core: organisations, projects, RBAC, sessions, audit context, jobs, AI config.

CREATE TABLE organizations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  short_name TEXT,
  brand_primary TEXT DEFAULT '#173B68',
  brand_accent TEXT DEFAULT '#18B6A4',
  logo_path TEXT,
  created_at REAL, updated_at REAL,
  active INTEGER DEFAULT 1
);

ALTER TABLE users ADD COLUMN full_name TEXT;
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN system_role TEXT DEFAULT 'user';      -- 'system_admin' or 'user'
ALTER TABLE users ADD COLUMN failed_logins INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN locked_until REAL DEFAULT 0;
ALTER TABLE users ADD COLUMN password_changed_at REAL;
ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0;
-- Legacy EvidenceQDA installs had exactly one administrator: promote existing users.
UPDATE users SET system_role='system_admin' WHERE id=(SELECT MIN(id) FROM users);

CREATE TABLE org_members(
  org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                       -- org_admin | member
  PRIMARY KEY(org_id, user_id)
);

-- Rebuild the (unused) legacy projects table with organisation scoping.
CREATE TABLE projects_v2(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  code TEXT,
  description TEXT,
  sector TEXT,
  geography TEXT,
  period_start TEXT,
  period_end TEXT,
  donor TEXT,
  classification TEXT DEFAULT 'Restricted',
  status TEXT DEFAULT 'active',
  metadata_json TEXT,
  created_by INTEGER,
  created_at REAL, updated_at REAL,
  UNIQUE(org_id, name)
);
INSERT INTO projects_v2(id, name, created_at, updated_at) SELECT id, name, created_at, updated_at FROM projects;
DROP TABLE projects;
ALTER TABLE projects_v2 RENAME TO projects;

CREATE TABLE project_members(
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL,     -- project_manager | meal_manager | meal_officer | analyst | data_collector | viewer
  added_at REAL,
  PRIMARY KEY(project_id, user_id)
);

ALTER TABLE sessions ADD COLUMN expires_at REAL;
ALTER TABLE sessions ADD COLUMN user_id INTEGER;

CREATE TABLE login_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ts REAL, success INTEGER);
CREATE INDEX ix_login_attempts_user ON login_attempts(username, ts);

ALTER TABLE audit ADD COLUMN org_id INTEGER;
ALTER TABLE audit ADD COLUMN project_id INTEGER;
ALTER TABLE audit ADD COLUMN object_type TEXT;
ALTER TABLE audit ADD COLUMN object_id TEXT;
CREATE INDEX ix_audit_project ON audit(project_id, ts);

ALTER TABLE chats ADD COLUMN project_id INTEGER;

CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT, updated_at REAL, updated_by TEXT);

CREATE TABLE jobs(
  id TEXT PRIMARY KEY,
  project_id INTEGER,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued|running|completed|failed|cancelled
  stage TEXT,
  progress REAL DEFAULT 0,
  message TEXT,
  params_json TEXT,
  result_json TEXT,
  error TEXT,
  cancel_requested INTEGER DEFAULT 0,
  checkpoint_json TEXT,
  created_by INTEGER,
  created_at REAL, started_at REAL, finished_at REAL
);
CREATE INDEX ix_jobs_project ON jobs(project_id, created_at);

CREATE TABLE ai_providers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,                       -- ollama | openai_compatible
  base_url TEXT NOT NULL,
  model TEXT NOT NULL,
  is_external INTEGER NOT NULL DEFAULT 0,   -- 1 = data leaves the organisation's machine/network
  enabled INTEGER NOT NULL DEFAULT 1,
  approved_by TEXT, approved_at REAL,
  terms_review_note TEXT,                   -- who verified retention/training terms, and when
  api_key_env TEXT,                         -- NAME of env var holding the key; the key itself is never stored
  options_json TEXT,
  is_default INTEGER DEFAULT 0,
  created_at REAL
);

CREATE TABLE ai_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER, job_id TEXT,
  provider TEXT, model TEXT, prompt_name TEXT, prompt_version TEXT,
  input_chars INTEGER, output_chars INTEGER,
  status TEXT, attempts INTEGER, duration_ms INTEGER, error TEXT,
  created_at REAL
);
