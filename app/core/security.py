import base64, hashlib, hmac, json, os, secrets, sqlite3, time
from pathlib import Path


def db_path():
    return Path(os.getenv("EVIDENCEQDA_DB", "data/evidenceqda.sqlite3"))


def connect():
    p=db_path(); p.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    c=connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, mfa_secret TEXT, recovery_codes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, username TEXT, device_label TEXT, user_agent TEXT, ip TEXT, created_at REAL, last_seen REAL, revoked INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, username TEXT, action TEXT, detail TEXT, severity TEXT DEFAULT 'INFO');
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_at REAL, updated_at REAL);
    CREATE TABLE IF NOT EXISTS privacy_settings(id INTEGER PRIMARY KEY CHECK(id=1), classification TEXT DEFAULT 'Restricted', retention_days INTEGER DEFAULT 365, local_only INTEGER DEFAULT 1, external_ai_approved INTEGER DEFAULT 0, organization_name TEXT DEFAULT 'Humanitarian Organization');
    CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, title TEXT, severity TEXT, status TEXT, source TEXT, notes TEXT, created_by TEXT);
    CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_by TEXT, created_at REAL, updated_at REAL);
    CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT, citations TEXT, ts REAL);
    """)
    c.execute("INSERT OR IGNORE INTO privacy_settings(id) VALUES(1)")
    c.commit(); c.close()


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 240000)
    return base64.b64encode(salt).decode()+":"+base64.b64encode(dk).decode()


def verify_password(password, stored):
    try:
        a,b=stored.split(':',1); salt=base64.b64decode(a); expected=base64.b64decode(b)
        actual=hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 240000)
        return hmac.compare_digest(actual, expected)
    except Exception: return False


def user_count():
    c=connect(); n=c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']; c.close(); return n


def create_user(username,password):
    c=connect(); c.execute('INSERT INTO users(username,password_hash) VALUES(?,?)',(username,hash_password(password))); c.commit(); c.close()


def get_user(username):
    c=connect(); r=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone(); c.close(); return dict(r) if r else None


def set_password(username,password):
    c=connect(); c.execute('UPDATE users SET password_hash=? WHERE username=?',(hash_password(password),username)); c.commit(); c.close()


def set_mfa(username,secret,recovery_codes):
    c=connect(); c.execute('UPDATE users SET mfa_secret=?, recovery_codes=? WHERE username=?',(secret,json.dumps(recovery_codes),username)); c.commit(); c.close()


def clear_mfa(username):
    c=connect(); c.execute('UPDATE users SET mfa_secret=NULL,recovery_codes=NULL WHERE username=?',(username,)); c.commit(); c.close()


def audit(username,action,detail='',severity='INFO'):
    c=connect(); c.execute('INSERT INTO audit(ts,username,action,detail,severity) VALUES(?,?,?,?,?)',(time.time(),username,action,detail,severity)); c.commit(); c.close()

# RFC 6238 compatible TOTP without external dependencies.
def totp(secret, for_time=None, digits=6, period=30):
    t=int(time.time() if for_time is None else for_time)//period
    key=base64.b32decode(secret.upper()+('='*((8-len(secret)%8)%8)),casefold=True)
    msg=t.to_bytes(8,'big'); digest=hmac.new(key,msg,hashlib.sha1).digest(); off=digest[-1]&15
    code=(int.from_bytes(digest[off:off+4],'big')&0x7fffffff)%(10**digits)
    return str(code).zfill(digits)


def verify_totp(secret,code):
    if not secret: return False
    return any(hmac.compare_digest(totp(secret,time.time()+i*30),str(code).strip()) for i in (-1,0,1))


def new_mfa_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def new_recovery_codes(n=8):
    return [secrets.token_hex(4).upper() for _ in range(n)]


def create_session(username,device_label,user_agent,ip):
    sid=secrets.token_urlsafe(32); now=time.time(); c=connect(); c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,0)',(sid,username,device_label,user_agent,ip,now,now)); c.commit(); c.close(); return sid


def sessions(username):
    c=connect(); rows=[dict(r) for r in c.execute('SELECT * FROM sessions WHERE username=? ORDER BY last_seen DESC',(username,))]; c.close(); return rows


def revoke_session(sid,username):
    c=connect(); c.execute('UPDATE sessions SET revoked=1 WHERE id=? AND username=?',(sid,username)); c.commit(); c.close()


def privacy():
    c=connect(); r=dict(c.execute('SELECT * FROM privacy_settings WHERE id=1').fetchone()); c.close(); return r


def update_privacy(**kw):
    allowed={'classification','retention_days','local_only','external_ai_approved','organization_name'}; vals={k:v for k,v in kw.items() if k in allowed}
    if not vals:return
    c=connect(); sets=','.join(f'{k}=?' for k in vals); c.execute(f'UPDATE privacy_settings SET {sets} WHERE id=1',tuple(vals.values())); c.commit(); c.close()


def incidents():
    c=connect(); rows=[dict(r) for r in c.execute('SELECT * FROM incidents ORDER BY ts DESC')]; c.close(); return rows


def add_incident(title,severity,status,source,notes,created_by):
    c=connect(); c.execute('INSERT INTO incidents(ts,title,severity,status,source,notes,created_by) VALUES(?,?,?,?,?,?,?)',(time.time(),title,severity,status,source,notes,created_by)); c.commit(); c.close()


def create_chat(title,user):
    c=connect(); now=time.time(); cur=c.execute('INSERT INTO chats(title,created_by,created_at,updated_at) VALUES(?,?,?,?)',(title,user,now,now)); c.commit(); cid=cur.lastrowid; c.close(); return cid


def list_chats(user):
    c=connect(); rows=[dict(r) for r in c.execute('SELECT * FROM chats WHERE created_by=? ORDER BY updated_at DESC',(user,))]; c.close(); return rows


def add_message(chat_id,role,content,citations):
    c=connect(); now=time.time(); c.execute('INSERT INTO chat_messages(chat_id,role,content,citations,ts) VALUES(?,?,?,?,?)',(chat_id,role,content,json.dumps(citations),now)); c.execute('UPDATE chats SET updated_at=? WHERE id=?',(now,chat_id)); c.commit(); c.close()


def messages(chat_id):
    c=connect(); rows=[dict(r) for r in c.execute('SELECT * FROM chat_messages WHERE chat_id=? ORDER BY id',(chat_id,))]; c.close(); return rows
