-- Tables from EvidenceQDA Enterprise v2, preserved so existing databases migrate in place.
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, mfa_secret TEXT, recovery_codes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, username TEXT, device_label TEXT, user_agent TEXT, ip TEXT, created_at REAL, last_seen REAL, revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, username TEXT, action TEXT, detail TEXT, severity TEXT DEFAULT 'INFO');
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS privacy_settings(id INTEGER PRIMARY KEY CHECK(id=1), classification TEXT DEFAULT 'Restricted', retention_days INTEGER DEFAULT 365, local_only INTEGER DEFAULT 1, external_ai_approved INTEGER DEFAULT 0, organization_name TEXT DEFAULT 'Humanitarian Organization');
CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, title TEXT, severity TEXT, status TEXT, source TEXT, notes TEXT, created_by TEXT);
CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_by TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT, citations TEXT, ts REAL);
INSERT OR IGNORE INTO privacy_settings(id) VALUES(1);
