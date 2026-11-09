import io
import json
import sqlite3
import zipfile
from pathlib import Path
import pytest

from PIL import Image
from test_core import client, create_question
from backend import ai, backups, store


def attempt(client,qid):
    return client.post('/api/attempts',json={'question_id':qid,'answer':'B'}).json()['id']


def confirm(client,aid,grade='correct',version=0):
    return client.post(f'/api/attempts/{aid}/confirm',json={'grade':grade,'version':version})


def validate(client,raw):
    return client.post('/api/backups/validate',files={'file':('backup.zip',raw)})


def repack(raw,change):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files={n:z.read(n) for n in z.namelist()}
    change(files)
    manifest=json.loads(files['manifest.json'])
    if manifest['version']==2:
        manifest['files']={n:backups.sha(v) for n,v in files.items() if n!='manifest.json'}
        files['manifest.json']=json.dumps(manifest).encode()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for n,v in files.items():z.writestr(n,v)
    return output.getvalue()


def mutate_db(files,tmp_path,sql):
    path=tmp_path/'source.db'
    path.write_bytes(files['study.db'])
    db=sqlite3.connect(path)
    db.executescript(sql)
    db.close()
    files['study.db']=path.read_bytes()


def test_question_revision_preserves_historical_evidence_and_answer(client):
    qid=create_question(client)
    aid=attempt(client,qid)
    assert confirm(client,aid).status_code==200
    pending=attempt(client,qid)
    original=client.get('/api/questions/'+qid).json()
    modified={**original,'title':'新题目','answer':'A','knowledge_id':'cache'}
    assert client.patch('/api/questions/'+qid,json=modified).json()['revision']==2
    assert client.patch('/api/questions/'+qid,json=original).status_code==409
    assert client.post('/api/attempts',json={'question_id':qid,'revision':1,'answer':'B'}).status_code==409
    old=client.get('/api/attempts/'+aid).json()
    assert old['question']['answer']=='B'
    assert old['question']['knowledge_id']=='page'
    assert old['current_revision']==2
    assert client.get('/api/attempts/'+pending).json()['status']=='outdated'
    assert confirm(client,pending).status_code==409
    result=confirm(client,aid,'incorrect',1).json()
    assert result['knowledge']['id']=='page'
    assert result['knowledge']['mastery']==33
    assert result['review'] is None
    new=client.post('/api/attempts',json={'question_id':qid,'answer':'A'}).json()
    assert new['result']['grade']=='correct'
    assert client.get('/api/attempts/'+new['id']).json()['question']['revision']==2


def test_revoke_restore_replays_state_and_plan_and_conflicts(client):
    qid=create_question(client)
    client.post('/api/plans/generate',json={'budget':60})
    aid=attempt(client,qid)
    initial=client.get('/api/attempts/'+aid).json()['created_at']
    assert confirm(client,aid).status_code==200
    assert client.get('/api/bootstrap').json()['plan']['tasks'][0]['status']=='done'
    assert client.post(f'/api/attempts/{aid}/status',json={'action':'void','version':1}).status_code==200
    data=client.get('/api/bootstrap').json()
    assert data['stats']['done_today']==0
    assert data['plan']['tasks'][0]['status']=='todo'
    assert next(k for k in data['knowledge'] if k['id']=='page')['evidence']==0
    assert client.post(f'/api/attempts/{aid}/status',json={'action':'restore','version':1}).status_code==409
    assert client.post(f'/api/attempts/{aid}/status',json={'action':'restore','version':2}).status_code==200
    restored=client.get('/api/attempts/'+aid).json()
    assert restored['created_at']==initial
    assert [r['action'] for r in restored['revisions']]==['restore','void','confirm']
    assert client.get('/api/bootstrap').json()['stats']['done_today']==1
    assert client.get('/api/attempts?status=confirmed&query=不存在').json()['total']==0
    assert client.get('/api/attempts?status=confirmed&limit=1').json()['total']==1


def test_partial_import_draft_and_optimistic_lock(client):
    raw=client.get('/api/template').content
    draft=client.post('/api/imports',files={'file':('q.xlsx',raw)}).json()
    items=draft['items'];items[0].update(title='',body='',warnings=['请补齐题干'])
    response=client.patch('/api/imports/'+draft['id'],json={'items':items,'version':0})
    assert response.json()['version']==1
    assert client.patch('/api/imports/'+draft['id'],json={'items':items,'version':0}).status_code==409
    reopened=client.get('/api/imports').json()[0]
    assert reopened['version']==1 and reopened['items'][0]['title']==''
    assert reopened['items'][0]['warnings']==['请补齐题干']
    assert client.post('/api/imports/'+draft['id']+'/confirm',json={'items':items,'version':1}).status_code==422
    items[0].update(title='补齐题目',body='完整的题干')
    assert client.post('/api/imports/'+draft['id']+'/confirm',json={'items':items,'version':0}).status_code==409
    assert client.post('/api/imports/'+draft['id']+'/confirm',json={'items':items,'version':1}).status_code==200


def test_backup_roundtrip_photos_safety_and_current_ai_config(client):
    image=io.BytesIO();Image.new('RGB',(30,20),'white').save(image,'PNG')
    photo=client.post('/api/uploads',files={'file':('answer.png',image.getvalue())}).json()['name']
    qid=create_question(client,attachments=[photo])
    aid=attempt(client,qid);confirm(client,aid)
    raw=client.get('/api/export').content
    original_photo=(store.FILES/photo).read_bytes()
    Image.new('RGB',(30,20),'black').save(store.FILES/photo,'JPEG')
    create_question(client,title='备份之后的新题')
    client.post('/api/settings/ai',json={'base_url':'https://example.com/v1','model':'current'})
    preview=validate(client,raw)
    assert preview.status_code==200,preview.text
    assert preview.json()['questions']==1 and preview.json()['photos']==1
    assert len(client.get('/api/bootstrap').json()['questions'])==2
    response=client.post('/api/backups/restore',json={'token':preview.json()['token']})
    assert response.status_code==200,response.text
    data=client.get('/api/bootstrap').json()
    assert len(data['questions'])==1 and data['ai']['model']=='current'
    assert data['stats']['done_today']==1
    name=response.json()['safety_backup']
    safety=client.get('/api/backups/safety/'+name)
    assert safety.status_code==200
    assert validate(client,safety.content).json()['questions']==2
    assert (store.FILES/photo).read_bytes()==original_photo


def test_backup_preview_expires_on_learning_change(client):
    qid=create_question(client)
    preview=validate(client,client.get('/api/export').content)
    assert preview.status_code==200,preview.text
    attempt(client,qid)
    response=client.post('/api/backups/restore',json={'token':preview.json()['token']})
    assert response.status_code==409
    assert client.get('/api/attempts').json()['total']==1


def test_demo_backup_with_generated_plan_is_valid(client):
    client.post('/api/plans/generate',json={'budget':60})
    response=validate(client,client.get('/api/export').content)
    assert response.status_code==200,response.text
    assert response.json()['questions']==16


def test_backup_rejects_hash_path_trigger_missing_photo_and_bad_json(client,tmp_path):
    qid=create_question(client)
    raw=client.get('/api/export').content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as out:
            for n in z.namelist():out.writestr(n,z.read(n)+(b'bad' if n=='study.db' else b''))
    assert validate(client,output.getvalue()).status_code==400
    assert validate(client,repack(raw,lambda f:f.update({'../escape.jpg':b'bad'}))).status_code==400
    bad=repack(raw,lambda f:mutate_db(f,tmp_path,"CREATE TRIGGER bad AFTER INSERT ON questions BEGIN DELETE FROM attempts; END;"))
    assert validate(client,bad).status_code==400
    bad=repack(raw,lambda f:mutate_db(f,tmp_path,"UPDATE questions SET attachments='[\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg\"]';"))
    assert validate(client,bad).status_code==400
    bad=repack(raw,lambda f:mutate_db(f,tmp_path,"UPDATE questions SET options='[{}]';"))
    assert validate(client,bad).status_code==400
    assert client.get('/api/questions/'+qid).json()['options']==['10','12','14','16']


def test_legacy_backup_restores_and_backfills_versions(client,tmp_path):
    qid=create_question(client);aid=attempt(client,qid);confirm(client,aid)
    def legacy(files):
        manifest=json.loads(files['manifest.json']);manifest['version']=1;manifest.pop('files')
        files['manifest.json']=json.dumps(manifest).encode()
        mutate_db(files,tmp_path,"""DROP TABLE question_revisions;
          ALTER TABLE questions DROP COLUMN revision;
          ALTER TABLE attempts DROP COLUMN question_snapshot;
          ALTER TABLE imports DROP COLUMN version;
          ALTER TABLE grading_history DROP COLUMN action;""")
    raw=repack(client.get('/api/export').content,legacy)
    preview=validate(client,raw)
    assert preview.status_code==200,preview.text
    assert preview.json()['legacy']
    response=client.post('/api/backups/restore',json={'token':preview.json()['token']})
    assert response.status_code==200,response.text
    assert client.get('/api/attempts/'+aid).json()['question']['revision']==1
    store.init_db();store.init_db()
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM question_revisions').fetchone()[0]==1


def test_failed_photo_restore_rolls_back_database_and_files(client,monkeypatch):
    image=io.BytesIO();Image.new('RGB',(20,20),'white').save(image,'PNG')
    photo=client.post('/api/uploads',files={'file':('q.png',image.getvalue())}).json()['name']
    create_question(client,attachments=[photo])
    raw=client.get('/api/export').content
    create_question(client,title='恢复前保留的题')
    Image.new('RGB',(20,20),'black').save(store.FILES/photo,'JPEG')
    old_photo=(store.FILES/photo).read_bytes();baseline=backups.fingerprint()
    preview=validate(client,raw).json()
    original_replace=Path.replace
    def fail_photo(path,target):
        if path.parent==store.FILES:raise OSError('simulated photo write failure')
        return original_replace(path,target)
    monkeypatch.setattr(Path,'replace',fail_photo)
    with pytest.raises(OSError):backups.restore(preview['token'])
    assert backups.fingerprint()==baseline
    assert (store.FILES/photo).read_bytes()==old_photo


def test_inflight_ai_cannot_overwrite_restored_attempt(client,monkeypatch):
    qid=create_question(client,type='calculation',options=[],answer='12位')
    aid=attempt(client,qid)
    preview=validate(client,client.get('/api/export').content).json()
    async def returning_after_restore(*args,**kwargs):
        backups.restore(preview['token'])
        return {'transcription':'12位','grade':'correct','summary':'返回过晚的批改','steps':[]}
    monkeypatch.setattr(ai,'call_json',returning_after_restore)
    response=client.post('/api/attempts/'+aid+'/grade',json={})
    assert response.status_code==409
    assert client.get('/api/attempts/'+aid).json()['ai_result'] is None


def test_inflight_explanation_does_not_overwrite_changed_plan(client,monkeypatch):
    plan=client.post('/api/plans/generate',json={'budget':60}).json()
    async def slow_result(*args,**kwargs):
        with store.connect() as db:
            row=db.execute('SELECT tasks FROM plans WHERE id=?',(plan['id'],)).fetchone()
            value=json.loads(row['tasks']);value['stale']=True
            db.execute('UPDATE plans SET tasks=? WHERE id=?',(store.dump(value),plan['id']))
        return {'summary':'过时解读','tasks':[]}
    monkeypatch.setattr(ai,'call_json',slow_result)
    assert client.post('/api/plans/'+plan['id']+'/explain',json={}).status_code==409
    assert client.get('/api/bootstrap').json()['plan']['summary'] is None
