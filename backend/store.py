"""Local persistence. Learning state is derived from confirmed, versioned attempts."""
import json
import os
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
PERSONAL_ROOT = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ShizhiStudy'
ROOT = Path(os.environ.get('STUDY_DATA_DIR', PERSONAL_ROOT))
if os.environ.get('STUDY_SHARE_MODE') == '1' and (not os.environ.get('STUDY_DATA_DIR') or ROOT.resolve() == PERSONAL_ROOT.resolve()):
    raise RuntimeError('分享模式必须使用独立的数据目录，请使用 share.py 启动。')
ROOT.mkdir(parents=True, exist_ok=True)
FILES = ROOT / 'attachments'
FILES.mkdir(exist_ok=True)
DB_PATH = ROOT / 'study.db'
DATA_LOCK = threading.RLock()
WORKSPACE_EPOCH = 0


def now():
    return datetime.now(TZ).isoformat()


def today():
    return datetime.now(TZ).date()


def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex[:14]


def dump(value):
    return json.dumps(value, ensure_ascii=False)


@contextmanager
def connect():
    # Serialize local mutations, including restore, across FastAPI worker threads.
    with DATA_LOCK:
        with _connection() as db:
            yield db


@contextmanager
def _connection():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def setting(db, key, default=None):
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(db, key, value):
    db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, dump(value)))


def init_db():
    with connect() as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS knowledge(
            id TEXT PRIMARY KEY, subject TEXT NOT NULL, chapter TEXT NOT NULL, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS questions(
            id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL REFERENCES knowledge(id),
            type TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            options TEXT NOT NULL DEFAULT '[]', answer TEXT NOT NULL DEFAULT '',
            explanation TEXT NOT NULL DEFAULT '', difficulty TEXT NOT NULL DEFAULT '中等',
            minutes INTEGER NOT NULL DEFAULT 12, verified INTEGER NOT NULL DEFAULT 0,
            attachments TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL DEFAULT '',
            is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(
            id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id),
            answer TEXT NOT NULL, photos TEXT NOT NULL DEFAULT '[]', hinted INTEGER NOT NULL DEFAULT 0,
            elapsed INTEGER NOT NULL DEFAULT 0, grade TEXT,
            ai_result TEXT, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, confirmed_at TEXT, is_demo INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS grading_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id TEXT NOT NULL REFERENCES attempts(id),
            version INTEGER NOT NULL, grade TEXT NOT NULL, confirmed_at TEXT NOT NULL,
            UNIQUE(attempt_id,version));
        CREATE TABLE IF NOT EXISTS plans(
            id TEXT PRIMARY KEY, day TEXT NOT NULL, budget INTEGER NOT NULL,
            tasks TEXT NOT NULL, summary TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS imports(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, items TEXT NOT NULL,
            warnings TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id,created_at);
        ''')
        columns={r['name'] for r in db.execute('PRAGMA table_info(attempts)')}
        if 'transcription_override' not in columns:
            db.execute("ALTER TABLE attempts ADD COLUMN transcription_override TEXT NOT NULL DEFAULT ''")
        for table, name, definition in [
            ('questions','revision','INTEGER NOT NULL DEFAULT 1'),
            ('attempts','question_snapshot',"TEXT NOT NULL DEFAULT '{}'"),
            ('grading_history','action',"TEXT NOT NULL DEFAULT 'confirm'"),
            ('imports','version','INTEGER NOT NULL DEFAULT 0'),
        ]:
            if name not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        db.execute('''CREATE TABLE IF NOT EXISTS question_revisions(
            question_id TEXT NOT NULL REFERENCES questions(id), revision INTEGER NOT NULL,
            snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(question_id,revision))''')
        if not setting(db, 'initialized', False):
            from .seed import seed
            seed(db)
            set_setting(db, 'initialized', True)
            set_setting(db, 'budget', 60)
            set_setting(db, 'demo_mode', True)
        from . import rag
        rag.rebuild(db)
        # Old records can only be associated with the pre-migration current question.
        # Preserve that content now, before allowing the first edit.
        for row in db.execute('SELECT * FROM questions').fetchall():
            snapshot=dump(question_dict(row))
            db.execute('INSERT OR IGNORE INTO question_revisions VALUES (?,?,?,?)',
                       (row['id'],row['revision'],snapshot,row['created_at']))
            db.execute("UPDATE attempts SET question_snapshot=? WHERE question_id=? AND question_snapshot='{}'",
                       (snapshot,row['id']))


def clear_demo(db):
    if not setting(db, 'demo_mode', False):
        return
    db.execute('DELETE FROM grading_history WHERE attempt_id IN (SELECT a.id FROM attempts a JOIN questions q ON q.id=a.question_id WHERE q.is_demo=1)')
    db.execute('DELETE FROM attempts WHERE question_id IN (SELECT id FROM questions WHERE is_demo=1)')
    db.execute('DELETE FROM question_revisions WHERE question_id IN (SELECT id FROM questions WHERE is_demo=1)')
    db.execute('DELETE FROM questions WHERE is_demo=1')
    from . import rag
    rag.rebuild(db)
    db.execute('DELETE FROM plans')
    set_setting(db, 'demo_mode', False)


def question_dict(row):
    value = dict(row)
    value['options'] = json.loads(value['options'])
    value['attachments'] = json.loads(value['attachments'])
    value['verified'] = bool(value['verified'])
    value['is_demo'] = bool(value['is_demo'])
    return value
