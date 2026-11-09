from test_core import client, create_question
from backend import rag, store


def test_chinese_fts_recall_uses_verified_same_subject_sources(client):
    current=create_question(client,title='操作系统综合题',knowledge_id='schedule')
    wanted=create_question(client,title='中文分页地址计算',body='分页系统中计算页内偏移。')
    unverified=create_question(client,title='中文分页地址计算',body='分页系统中计算页内偏移。',verified=False)
    other_subject=create_question(client,title='中文分页地址计算',body='分页系统中计算页内偏移。',knowledge_id='cache')
    with store.connect() as db:
        assert rag._fts_enabled(db), 'The supported Python runtime must include FTS5'
        rows=rag.retrieve(db,current,'schedule','操作系统','分页地址',limit=5)
    ids={row['question_id'] for row in rows}
    assert wanted in ids
    assert unverified not in ids
    assert other_subject not in ids
    assert current not in ids
    assert next(row for row in rows if row['question_id']==wanted)['title']=='中文分页地址计算'


def test_question_edit_replaces_fts_terms(client):
    question_id=create_question(client,title='unique_old_term',body='原始内容。')
    question=client.get('/api/questions/'+question_id).json()
    question.update(title='unique_new_term')
    assert client.patch('/api/questions/'+question_id,json=question).status_code==200
    with store.connect() as db:
        assert not rag._fts_rows(db,'unique_old_term','none','操作系统',5)
        assert rag._fts_rows(db,'unique_new_term','none','操作系统',5)[0]['question_id']==question_id


def test_retrieval_without_fts_has_same_knowledge_fallback(client,monkeypatch):
    current=create_question(client)
    related=create_question(client,title='同知识点题目')
    monkeypatch.setattr(rag,'_fts_enabled',lambda db:False)
    with store.connect() as db:
        rows=rag.retrieve(db,current,'page','操作系统','无词法匹配',limit=5)
    assert related in {row['question_id'] for row in rows}
