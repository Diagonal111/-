"""Small local retrieval layer for grounded explanations.

The first version deliberately keeps retrieval local and inspectable. SQLite FTS5
is used when available, with a metadata fallback for older SQLite builds.
"""
import re
import sqlite3


INDEX_COLUMNS = ('question_id', 'title', 'body', 'explanation', 'answer', 'knowledge', 'subject')


def _table_exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def _fts_enabled(db):
    row = db.execute("SELECT sql FROM sqlite_master WHERE name='question_search'").fetchone()
    return bool(row and row['sql'] and 'fts5' in row['sql'].lower())


def ensure_index(db):
    try:
        db.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS question_search USING fts5(
            question_id UNINDEXED, title, body, explanation, answer, knowledge, subject,
            tokenize='unicode61 remove_diacritics 1')''')
    except sqlite3.OperationalError as exc:
        if 'no such module: fts5' not in str(exc).lower():
            raise
        db.execute('''CREATE TABLE IF NOT EXISTS question_search_plain(
            question_id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
            explanation TEXT NOT NULL, answer TEXT NOT NULL, knowledge TEXT NOT NULL,
            subject TEXT NOT NULL)''')


def _values(db, question_id):
    row = db.execute('''SELECT q.id AS question_id, q.title, q.body, q.explanation, q.answer,
                               k.name AS knowledge, k.subject
                        FROM questions q JOIN knowledge k ON k.id=q.knowledge_id
                        WHERE q.id=?''', (question_id,)).fetchone()
    return tuple(row[column] or '' for column in INDEX_COLUMNS) if row else None


def refresh_question(db, question_id):
    ensure_index(db)
    if _table_exists(db, 'question_search'):
        db.execute('DELETE FROM question_search WHERE question_id=?', (question_id,))
    if _table_exists(db, 'question_search_plain'):
        db.execute('DELETE FROM question_search_plain WHERE question_id=?', (question_id,))
    values = _values(db, question_id)
    if not values:
        return
    if _fts_enabled(db):
        # unicode61 treats a run of Chinese text as one token. Apply the same
        # character tokenization to the index and query, retaining source text
        # in questions for citations and model context.
        indexed=(values[0],)+tuple(' '.join(re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]', text)) for text in values[1:])
        db.execute('INSERT INTO question_search VALUES (?,?,?,?,?,?,?)', indexed)
    else:
        db.execute('INSERT INTO question_search_plain VALUES (?,?,?,?,?,?,?)', values)


def rebuild(db):
    ensure_index(db)
    if _table_exists(db, 'question_search'):
        db.execute('DELETE FROM question_search')
    if _table_exists(db, 'question_search_plain'):
        db.execute('DELETE FROM question_search_plain')
    for row in db.execute('SELECT id FROM questions').fetchall():
        refresh_question(db, row['id'])


def _terms(text):
    # Keep ASCII words intact and split CJK into characters because unicode61
    # does not perform Chinese word segmentation.
    result = []
    for piece in re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]', text or ''):
        if piece not in result:
            result.append(piece)
    return result[:24]


def _fts_rows(db, query, current_id, subject, limit):
    terms = _terms(query)
    if not terms or not _fts_enabled(db):
        return []
    expression = ' OR '.join('"' + term.replace('"', '""') + '"' for term in terms)
    try:
        rows = db.execute('''SELECT q.id AS question_id, q.title, q.body, q.explanation,
                                    q.answer, k.name AS knowledge, k.subject,
                                    q.type, q.knowledge_id, bm25(question_search) AS score
                             FROM question_search
                             JOIN questions q ON q.id=question_search.question_id
                             JOIN knowledge k ON k.id=q.knowledge_id
                             WHERE question_search MATCH ? AND q.id<>?
                               AND q.verified=1 AND k.subject=?
                             ORDER BY score, q.id LIMIT ?''', (expression, current_id, subject, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(row) for row in rows]


def retrieve(db, current_id, knowledge_id, subject, query, limit=5):
    """Return verified related questions with stable source metadata."""
    selected = {}
    for row in _fts_rows(db, query, current_id, subject, limit * 3):
        selected[row['question_id']] = row

    # Same-knowledge questions are useful even when Chinese tokenization has no
    # lexical match. Fill remaining slots with deterministic local candidates.
    rows = db.execute('''SELECT q.id AS question_id, q.title, q.body, q.explanation,
                                q.answer, k.name AS knowledge, k.subject,
                                q.type, q.knowledge_id
                         FROM questions q JOIN knowledge k ON k.id=q.knowledge_id
                         WHERE q.id<>? AND q.verified=1
                           AND q.knowledge_id=? AND k.subject=?
                         ORDER BY q.knowledge_id<>?, q.created_at DESC, q.id
                         LIMIT ?''', (current_id, knowledge_id, subject, knowledge_id, limit * 3)).fetchall()
    for row in rows:
        if row['question_id'] not in selected:
            selected[row['question_id']] = dict(row, score=0.0)

    # Prefer the same knowledge point, then BM25 lexical relevance. Do not fill
    # the context with arbitrary questions merely because they share a subject.
    result = sorted(selected.values(),key=lambda row:(row['knowledge_id']!=knowledge_id,row['score'],row['question_id']))[:limit]
    for item in result:
        item['content'] = '\n'.join(part for part in (
            item.get('title'), item.get('body'), item.get('explanation'),
            f"参考答案：{item.get('answer')}" if item.get('answer') else '') if part)
    return result
