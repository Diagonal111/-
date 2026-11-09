"""Practice-bank integration checks use an isolated database."""
import json
from collections import Counter

from test_core import client
from backend import main, store
from backend.practice_bank import install, questions


def test_practice_bank_install_preserves_records_and_future_imports(client):
    data = client.get('/api/bootstrap').json()
    old_questions = {q['id']: q for q in data['questions']}
    old_attempts = client.get('/api/attempts?limit=200').json()
    with store.connect() as db:
        assert install(db) == 100
        points = {r['id']: r['subject'] for r in db.execute('SELECT * FROM knowledge')}
        for q in questions():
            main.validate_question(db, main.QuestionInput(**q))
            assert points[q['knowledge_id']] == q['subject']
            assert q['explanation'].strip()
        assert len({q['title'] for q in questions()}) == 100
        assert Counter(q['subject'] for q in questions()) == dict.fromkeys(points.values(), 25)
    data = client.get('/api/bootstrap').json()
    assert len(data['questions']) == len(old_questions) + 100
    assert {q['id']: q for q in data['questions'] if q['id'] in old_questions} == old_questions
    assert client.get('/api/attempts?limit=200').json() == old_attempts

    qid = 'practice408_ds_01'
    q = client.get('/api/questions/' + qid).json()
    q['title'] = '我自行修订的题目'
    assert client.patch('/api/questions/' + qid, json=q).status_code == 200
    a = client.post('/api/attempts', json={'question_id': qid, 'answer': '8 个；6 个'}).json()
    assert client.post('/api/attempts/' + a['id'] + '/confirm', json={'grade': 'correct'}).status_code == 200
    with store.connect() as db:
        assert install(db) == 0
        edited = db.execute('SELECT * FROM questions WHERE id=?', (qid,)).fetchone()
        assert edited['title'] == q['title'] and edited['revision'] == 2
        assert json.loads(db.execute('SELECT question_snapshot FROM attempts WHERE id=?', (a['id'],)).fetchone()[0])['revision'] == 2

    # First later import clears old simulated data, while all 100 practice questions survive.
    draft = client.post('/api/imports', files={'file': ('questions.xlsx', client.get('/api/template').content)}).json()
    draft['items'][0]['verified'] = True
    response = client.post('/api/imports/' + draft['id'] + '/confirm', json={'items': draft['items']})
    assert response.status_code == 200, response.text
    data = client.get('/api/bootstrap').json()
    assert not data['demo_mode'] and len(data['questions']) == 101
    detail = client.get('/api/attempts/' + a['id']).json()
    assert detail['status'] == 'confirmed' and detail['question']['revision'] == 2


def test_objective_practice_answers_work_with_grading(client):
    with store.connect() as db:
        install(db)
    for q in questions():
        if q['type'] == 'calculation':
            continue
        right = client.post('/api/attempts', json={'question_id': q['id'], 'answer': q['answer']}).json()
        wrong_answer = ('错误' if q['answer'] == '正确' else '正确') if q['type'] == 'boolean' else ('B' if q['answer'] == 'A' else 'A')
        wrong = client.post('/api/attempts', json={'question_id': q['id'], 'answer': wrong_answer}).json()
        assert right['result']['grade'] == 'correct'
        assert wrong['result']['grade'] == 'incorrect'
