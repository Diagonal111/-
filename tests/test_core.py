import io
import json
import zipfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend import ai, imports, main, store
from backend.learning import derive_state, make_plan


@pytest.fixture
def client(tmp_path,monkeypatch):
    photos=tmp_path/'attachments'
    photos.mkdir()
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'study.db')
    for module in (store,main,ai,imports):
        monkeypatch.setattr(module,'FILES',photos)
    monkeypatch.setattr(ai,'SESSION_KEY','')
    monkeypatch.delenv('STUDY_API_KEY',raising=False)
    with TestClient(main.app) as c:
        c.headers['X-Study-Token']=c.get('/api/bootstrap').json()['token']
        yield c


def create_question(client,**overrides):
    payload={'title':'测试题','body':'页面大小为4KB，页内偏移是多少位？','knowledge_id':'page',
             'type':'single','options':['10','12','14','16'],'answer':'B','verified':True,'minutes':3}
    payload.update(overrides)
    response=client.post('/api/questions',json=payload)
    assert response.status_code==200,response.text
    return response.json()['id']


def insert_attempt(db,id_,qid,offset,grade,hinted=False):
    stamp=(store.today()+timedelta(days=offset)).isoformat()+'T10:00:00+08:00'
    db.execute('''INSERT INTO attempts(id,question_id,answer,grade,hinted,status,created_at,confirmed_at,version)
        VALUES (?,?,?,?,?,'confirmed',?,?,1)''',(id_,qid,'测试',grade,int(hinted),stamp,stamp))


def test_plan_never_exceeds_budget_and_has_no_duplicate_questions(client):
    with store.connect() as db:
        for budget in range(5,241):
            plan=make_plan(db,budget)
            ids=[t['question_id'] for t in plan['tasks']]
            assert len(ids)==len(set(ids))
            assert plan['total_minutes']<=budget
            assert plan['study_minutes']==sum(t['minutes'] for t in plan['tasks'])


def test_confirmation_is_idempotent_and_revision_replaces_evidence(client):
    qid=create_question(client)
    attempt=client.post('/api/attempts',json={'question_id':qid,'answer':'B'}).json()
    assert attempt['result']['grade']=='correct'
    request={'grade':'correct','version':0}
    first=client.post(f"/api/attempts/{attempt['id']}/confirm",json=request)
    assert first.status_code==200
    assert first.json()['knowledge']['evidence']==1
    assert client.post(f"/api/attempts/{attempt['id']}/confirm",json=request).json()['idempotent']
    revised=client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'incorrect','version':1})
    assert revised.status_code==200
    assert revised.json()['knowledge']['mastery']==33
    assert revised.json()['knowledge']['evidence']==1
    assert client.post(f"/api/attempts/{attempt['id']}/confirm",json=request).status_code==409
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM grading_history').fetchone()[0]==2


def test_unconfirmed_attempt_never_changes_mastery(client):
    qid=create_question(client)
    client.post('/api/attempts',json={'question_id':qid,'answer':'B'})
    with store.connect() as db:
        knowledge,_,reviews,_=derive_state(db)
        assert knowledge['page']['evidence']==0
        assert qid not in reviews


def test_unverified_reference_blocked_and_can_be_completed(client):
    qid=create_question(client,verified=False,answer='')
    attempt=client.post('/api/attempts',json={'question_id':qid,'answer':'B'}).json()
    assert attempt['result']['grade']=='unknown'
    assert client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'correct'}).status_code==409
    q=client.get('/api/questions/'+qid).json()
    q.update(answer='B',verified=True)
    assert client.patch('/api/questions/'+qid,json=q).status_code==200
    assert client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'correct'}).status_code==409


def test_same_day_repetition_has_reduced_weight_and_keeps_due_date(client):
    qid=create_question(client)
    with store.connect() as db:
        for i in range(3):
            insert_attempt(db,f'a{i}',qid,0,'correct')
        knowledge,_,reviews,_=derive_state(db)
        assert knowledge['page']['evidence']==1.2
        assert reviews[qid]['stage']==0
        assert reviews[qid]['due_date']==(store.today()+timedelta(days=1)).isoformat()


def test_cross_day_success_advances_but_early_practice_does_not(client):
    qid=create_question(client)
    with store.connect() as db:
        insert_attempt(db,'a0',qid,-4,'correct')
        insert_attempt(db,'a1',qid,-3,'correct')
        insert_attempt(db,'a2',qid,-2,'correct')
        _,_,reviews,_=derive_state(db)
        assert reviews[qid]['stage']==1
        assert reviews[qid]['due_date']==store.today().isoformat()
        insert_attempt(db,'a3',qid,0,'correct')
        _,_,reviews,_=derive_state(db)
        assert reviews[qid]['stage']==2
        assert reviews[qid]['due_date']==(store.today()+timedelta(days=7)).isoformat()


def test_hinted_success_restarts_interval(client):
    qid=create_question(client)
    with store.connect() as db:
        insert_attempt(db,'a0',qid,-5,'correct')
        insert_attempt(db,'a1',qid,-4,'correct')
        insert_attempt(db,'a2',qid,0,'correct',hinted=True)
        knowledge,_,reviews,_=derive_state(db)
        assert knowledge['page']['evidence']==2.25
        assert reviews[qid]['stage']==0
        assert reviews[qid]['due_date']==(store.today()+timedelta(days=1)).isoformat()


def test_late_confirmation_uses_original_attempt_day(client):
    qid=create_question(client)
    attempt=client.post('/api/attempts',json={'question_id':qid,'answer':'B'}).json()
    with store.connect() as db:
        old=(store.today()-timedelta(days=4)).isoformat()+'T23:00:00+08:00'
        db.execute('UPDATE attempts SET created_at=? WHERE id=?',(old,attempt['id']))
    result=client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'correct'}).json()
    assert result['review']['due_date']==(store.today()-timedelta(days=3)).isoformat()
    assert client.get('/api/bootstrap').json()['stats']['done_today']==0


def test_excel_import_preview_confirm_and_demo_isolation(client):
    raw=client.get('/api/template').content
    imported=client.post('/api/imports',files={'file':('questions.xlsx',raw)}).json()
    assert imported['mode']=='structured'
    assert len(imported['items'])==1
    assert imported['items'][0]['knowledge_id']=='page'
    assert not imported['items'][0]['verified']
    assert client.get('/api/bootstrap').json()['demo_mode']
    imported['items'][0]['verified']=True
    response=client.post(f"/api/imports/{imported['id']}/confirm",json={'items':imported['items']})
    assert response.status_code==200,response.text
    data=client.get('/api/bootstrap').json()
    assert not data['demo_mode']
    assert data['stats']['question_count']==1
    assert data['stats']['practiced']==0
    assert client.post(f"/api/imports/{imported['id']}/confirm",json={'items':imported['items']}).status_code==409


def test_ai_grading_and_corrected_transcription_protocol(client,monkeypatch):
    qid=create_question(client,type='calculation',options=[],answer='12位')
    attempt=client.post('/api/attempts',json={'question_id':qid,'answer':'12位'}).json()
    calls=[]
    async def fake_model(instruction,payload,images=None):
        calls.append(payload)
        return {'transcription':payload['student_answer'],'grade':'correct','summary':'步骤正确',
                'steps':[{'quote':'12位','verdict':'正确','reason':'4KB=2^12 B'}],'uncertainties':[]}
    monkeypatch.setattr(ai,'call_json',fake_model)
    assert client.post(f"/api/attempts/{attempt['id']}/grade",json={}).json()['grade']=='correct'
    corrected=client.patch(f"/api/attempts/{attempt['id']}/transcription",json={'text':'4KB=2^12B，因此12位','version':0})
    assert corrected.json()['version']==1
    assert client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'correct','version':0}).status_code==409
    assert client.post(f"/api/attempts/{attempt['id']}/grade",json={}).status_code==200
    assert calls[-1]['transcription_corrected_by_user']
    assert client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'correct','version':1}).status_code==200


def test_photo_grading_runs_transcription_then_answer_check(client,monkeypatch):
    from PIL import Image
    qid=create_question(client,type='calculation',options=[],answer='12位')
    image=io.BytesIO()
    Image.new('RGB',(30,30),'white').save(image,'PNG')
    uploaded=client.post('/api/uploads',files={'file':('answer.png',image.getvalue(),'image/png')})
    assert uploaded.status_code==200
    attempt=client.post('/api/attempts',json={'question_id':qid,'photos':[uploaded.json()['name']]})
    assert attempt.status_code==200
    calls=[]
    async def fake_model(instruction,payload,images=None):
        calls.append((instruction,payload,images))
        if instruction==ai.TRANSCRIBE_INSTRUCTION:
            return {'transcription':'4KB=2^12B，因此偏移为12位','uncertainties':['手写单位略模糊']}
        return {'transcription':payload['student_answer'],'grade':'correct','summary':'结论正确',
                'steps':[{'quote':'12位','verdict':'正确','reason':'由 2^12 个字节可知偏移为 12 位'}],
                'uncertainties':[]}
    monkeypatch.setattr(ai,'call_json',fake_model)
    result=client.post(f"/api/attempts/{attempt.json()['id']}/grade",json={})
    assert result.status_code==200,result.text
    assert len(calls)==2
    assert calls[0][0]==ai.TRANSCRIBE_INSTRUCTION and calls[0][2]
    assert calls[1][0]==ai.GRADE_INSTRUCTION and calls[1][2] is None
    assert calls[1][1]['student_answer']=='4KB=2^12B，因此偏移为12位'
    assert result.json()['workflow']==[
        {'step':'照片转写','status':'完成'},
        {'step':'依据题目与参考答案批改','status':'完成'},
    ]
    assert result.json()['uncertainties']==['手写单位略模糊']
    assert client.get('/api/bootstrap').json()['stats']['done_today']==0
    assert client.post(f"/api/attempts/{attempt.json()['id']}/confirm",json={'grade':'correct','version':0}).status_code==200


def test_rag_explanation_retrieves_verified_related_questions_and_filters_citations(client,monkeypatch):
    current=create_question(client,title='页内偏移位数计算',body='页面大小为4KB，求页内偏移地址位数。',knowledge_id='page',type='calculation',options=[],answer='12位',explanation='4KB=2^12B。')
    related=create_question(client,title='页表地址结构',body='页大小为4KB时，页内偏移占多少位？',knowledge_id='page',type='calculation',options=[],answer='12位',explanation='由 2^12=4KB。')
    calls=[]
    async def fake_model(instruction,payload,images=None):
        calls.append(payload)
        return {'answer':'两题都考查页内偏移位数，先把容量换成 2 的幂。',
                'citations':[{'question_id':current,'reason':'当前题目'},{'question_id':related,'reason':'同知识点例题'},{'question_id':'not-allowed','reason':'不应出现'}],
                'recommended_question_ids':[related,'not-allowed'],'uncertainties':[]}
    monkeypatch.setattr(ai,'call_json',fake_model)
    response=client.post(f'/api/questions/{current}/explain',json={})
    assert response.status_code==200,response.text
    result=response.json()
    assert len(calls)==1
    assert any(item['question_id']==related for item in calls[0]['related_questions'])
    assert {item['question_id'] for item in result['citations']}=={current,related}
    assert result['recommendations']==[{'question_id':related,'title':'页表地址结构','knowledge':'分页与地址转换'}]
    assert result['retrieved_count']>=1


def test_malformed_ai_output_does_not_change_learning_state(client,monkeypatch):
    qid=create_question(client,type='calculation',options=[],answer='12位')
    attempt=client.post('/api/attempts',json={'question_id':qid,'answer':'12位'}).json()
    async def invalid_model(*args,**kwargs):
        return {'grade':'definitely','steps':[{'quote':{'unexpected':'object'}}]}
    monkeypatch.setattr(ai,'call_json',invalid_model)
    assert client.post(f"/api/attempts/{attempt['id']}/grade",json={}).status_code==502
    assert client.get('/api/bootstrap').json()['stats']['done_today']==0


def test_backup_is_complete_snapshot_and_key_not_exposed(client):
    client.post('/api/settings/ai',json={'base_url':'https://example.com/v1','model':'test-model','api_key':'test-secret-not-real'})
    response=client.get('/api/export')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert 'study.db' in archive.namelist()
        assert json.loads(archive.read('manifest.json'))['version']==2
        assert b'test-secret-not-real' not in archive.read('study.db')
    assert 'test-secret-not-real' not in client.get('/api/bootstrap').text


def test_local_mutation_requires_session_and_rejects_foreign_origin(client):
    assert client.post('/api/plans/generate',json={'budget':60},headers={'X-Study-Token':'wrong'}).status_code==403
    assert client.post('/api/plans/generate',json={'budget':60},headers={'Origin':'https://example.org'}).status_code==403


def test_invalid_objective_answer_is_not_importable_as_verified(client):
    qid=create_question(client,verified=False)
    q=client.get('/api/questions/'+qid).json()
    q.update(answer='Z',verified=True)
    assert client.patch('/api/questions/'+qid,json=q).status_code==400


def test_ai_http_adapter_sends_multimodal_request_without_real_network(client,monkeypatch):
    import asyncio
    import httpx
    from PIL import Image
    client.post('/api/settings/ai',json={'base_url':'https://example.com/v1','model':'test-vision','api_key':'not-a-real-key'})
    image=io.BytesIO()
    Image.new('RGB',(30,30),'white').save(image,'PNG')
    name=imports.save_image(image.getvalue())
    seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        assert str(request.url)=='https://example.com/v1/chat/completions'
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok": true}'}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    assert asyncio.run(ai.call_json('返回JSON',{'question':'测试'},[name]))=={'ok':True}
    content=seen[0]['messages'][1]['content']
    assert content[0]['type']=='text'
    assert content[1]['type']=='image_url'
    assert content[1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert seen[0]['response_format']=={'type':'json_object'}


def test_javascript_assets_have_executable_mime_type(client):
    assets=list(main.DIST.glob('assets/index-*.js'))
    if not assets:
        pytest.skip('Run npm run build to exercise built asset MIME types')
    response=client.get('/assets/'+assets[0].name)
    assert response.status_code==200
    assert response.headers['content-type'].startswith('application/javascript')


def test_deepseek_rejects_display_name_without_replacing_key(client,monkeypatch):
    monkeypatch.setattr(ai,'SESSION_KEY','existing-test-key')
    for model in ('ds','deepseek v4.1 flash'):
        response=client.post('/api/settings/ai',json={
            'base_url':'https://api.deepseek.com','model':model,'api_key':'replacement-key'})
        assert response.status_code==400
        assert ai.SESSION_KEY=='existing-test-key'
    assert client.post('/api/settings/ai',json={
        'base_url':'https://api.deepseek.com','model':'deepseek-flash'}).status_code==200


def test_text_model_request_and_redacted_provider_errors(client,monkeypatch):
    import asyncio
    import httpx
    from fastapi import HTTPException
    client.post('/api/settings/ai',json={
        'base_url':'https://example.com/v1','model':'text-model','api_key':'fake-secret'})
    original=httpx.AsyncClient
    def handler(request):
        body=json.loads(request.content)
        assert isinstance(body['messages'][1]['content'],str)
        return httpx.Response(400,json={'error':{'message':'Invalid model fake-secret private-answer'}})
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ai.call_json('返回 JSON',{'answer':'private-answer'}))
    assert '模型名称无效' in exc.value.detail
    assert 'fake-secret' not in exc.value.detail
    assert 'private-answer' not in exc.value.detail


def test_import_draft_edits_survive_reopen(client):
    raw=client.get('/api/template').content
    imported=client.post('/api/imports',files={'file':('questions.xlsx',raw)}).json()
    imported['items'][0]['title']='校对后的标题'
    response=client.patch('/api/imports/'+imported['id'],json={'items':imported['items']})
    assert response.status_code==200
    reopened=client.get('/api/imports').json()
    assert reopened[0]['items'][0]['title']=='校对后的标题'


def test_replanning_preserves_completed_tasks_and_remaining_budget(client):
    plan=client.post('/api/plans/generate',json={'budget':60}).json()
    task=plan['tasks'][0]
    attempt=client.post('/api/attempts',json={'question_id':task['question_id'],'answer':'示例自评'}).json()
    client.post(f"/api/attempts/{attempt['id']}/confirm",json={'grade':'correct'})
    replanned=client.post('/api/plans/generate',json={'budget':60}).json()
    done=[t for t in replanned['tasks'] if t['status']=='done']
    assert len(done)==1
    assert done[0]['question_id']==task['question_id']
    assert len({t['question_id'] for t in replanned['tasks']})==len(replanned['tasks'])
    assert replanned['total_minutes']<=60
    assert replanned['study_minutes']==sum(t['minutes'] for t in replanned['tasks'])


def test_word_and_photo_import_without_key_are_explicit_manual_drafts(client):
    from docx import Document
    from PIL import Image
    document=Document()
    document.add_paragraph('计算题：某存储器按字节编址，请计算地址位数。')
    word=io.BytesIO()
    document.save(word)
    response=client.post('/api/imports',files={'file':('题目.docx',word.getvalue())})
    assert response.status_code==200
    assert response.json()['mode']=='manual'
    assert '存储器' in response.json()['items'][0]['body']
    photo=io.BytesIO()
    Image.new('RGB',(100,80),'white').save(photo,'PNG')
    response=client.post('/api/imports',files={'file':('题目.png',photo.getvalue())})
    assert response.status_code==200
    assert response.json()['mode']=='manual'
    assert len(response.json()['items'][0]['attachments'])==1
    assert not response.json()['items'][0]['verified']


def test_excel_numeric_zero_is_preserved():
    from openpyxl import Workbook
    workbook=Workbook()
    workbook.active.append(['题干','答案'])
    workbook.active.append(['计算某表达式',0])
    raw=io.BytesIO()
    workbook.save(raw)
    material=imports.extract_material('zero.xlsx',raw.getvalue())
    assert material['items'][0]['answer']=='0'
