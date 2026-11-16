import os, json, sqlite3, secrets, time

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'checker.db')


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = conn(); q = c.cursor()
    q.execute('''CREATE TABLE IF NOT EXISTS reports (
        token TEXT PRIMARY KEY, user_id TEXT, username TEXT,
        raw TEXT, report TEXT, created_at INTEGER)''')
    c.commit(); c.close()


def save(user_id, username, raw, report):
    tok = secrets.token_urlsafe(12)
    c = conn(); q = c.cursor()
    q.execute('INSERT INTO reports (token,user_id,username,raw,report,created_at) VALUES (?,?,?,?,?,?)',
              (tok, str(user_id), str(username), raw, json.dumps(report, ensure_ascii=False), int(time.time())))
    c.commit(); c.close()
    return tok


def get(token):
    c = conn(); q = c.cursor()
    q.execute('SELECT * FROM reports WHERE token=?', (token,))
    r = q.fetchone(); c.close()
    if not r:
        return None
    d = dict(r)
    d['report'] = json.loads(d['report'])
    return d


def recent(user_id, limit=10):
    c = conn(); q = c.cursor()
    q.execute('SELECT token,username,created_at FROM reports WHERE user_id=? ORDER BY created_at DESC LIMIT ?',
              (str(user_id), limit))
    rows = [dict(r) for r in q.fetchall()]; c.close()
    return rows
