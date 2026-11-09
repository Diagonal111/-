import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest


@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    root=tmp_path_factory.mktemp('share')
    personal=root/'personal'/'ShizhiStudy'
    personal.mkdir(parents=True)
    marker=personal/'study.db'
    marker.write_bytes(b'personal data must never be opened')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    env=os.environ.copy()
    env.update(LOCALAPPDATA=str(root/'personal'),STUDY_SHARE_MODE='1',STUDY_DATA_DIR=str(root/'demo'),STUDY_SHARE_PASSWORD='test-demo-password-123',STUDY_API_KEY='must-not-be-used')
    with (root/'server.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(port)],cwd=Path(__file__).resolve().parent.parent,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=10,trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get('/share/login').status_code==200:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.poll() is not None:
                        pytest.fail((root/'server.log').read_text())
                    time.sleep(.1)
                else:
                    pytest.fail('demo did not start')
                yield client,marker
        finally:
            process.terminate()
            process.wait(timeout=10)


def login(client):
    client.cookies.clear()
    response=client.post('/share/login',data={'password':'test-demo-password-123'},headers={'Origin':str(client.base_url).rstrip('/')})
    assert response.status_code==303
    assert 'HttpOnly' in response.headers['set-cookie']
    return client.get('/api/bootstrap').json()


def test_demo_requires_password_and_rejects_foreign_origin(demo):
    client,_=demo
    client.cookies.clear()
    assert client.get('/').status_code==303
    assert client.get('/api/bootstrap').status_code==401
    assert client.get('/attachments/anything.jpg').status_code==303
    assert client.get('/share/login',headers={'Host':'untrusted.example'}).status_code==400
    assert client.post('/share/login',data={'password':'test-demo-password-123'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/share/login',data={'password':'wrong'},headers={'Origin':str(client.base_url).rstrip('/')}).status_code==401
    state=login(client)
    assert state['share_mode'] and not state['ai']['configured'] and not state['ai']['has_key']
    assert len(state['questions'])==116
    assert client.get('/').status_code==200


def test_demo_blocks_administration_and_paid_ai_but_allows_practice(demo):
    client,marker=demo
    state=login(client)
    headers={'X-Study-Token':state['token'],'Origin':str(client.base_url).rstrip('/')}
    for method,path in [('GET','/api/export'),('GET','/api/backups/safety'),('GET','/api/imports'),('POST','/api/workspace/start'),('POST','/api/questions'),('PATCH','/api/questions/q_tcp'),('POST','/api/uploads'),('POST','/api/settings/ai'),('POST','/api/backups/restore'),('POST','/api/imports'),('POST','/api/plans/a/explain'),('POST','/api/attempts/a/grade')]:
        assert client.request(method,path,headers=headers).status_code==403,(method,path)
    foreign={**headers,'Origin':'https://evil.example'}
    assert client.post('/api/attempts',json={'question_id':'q_tcp','answer':'B'},headers=foreign).status_code==403
    assert client.post('/api/attempts',json={'question_id':'q_tcp','answer':'B'},headers={'Origin':headers['Origin']}).status_code==403
    response=client.post('/api/attempts',json={'question_id':'q_tcp','answer':'B'},headers=headers)
    assert response.status_code==200,response.text
    aid=response.json()['id']
    assert response.json()['result']['grade']=='correct'
    assert client.post(f'/api/attempts/{aid}/confirm',json={'grade':'correct','version':0},headers=headers).status_code==200
    assert client.get('/api/attempts/'+aid).json()['status']=='confirmed'
    assert client.post('/api/plans/generate',json={'budget':30},headers=headers).status_code==200
    assert marker.read_bytes()==b'personal data must never be opened'


def test_demo_supports_tunnel_origin_and_signed_sessions(demo):
    client,_=demo
    state=login(client)
    host='demo-name.trycloudflare.com'
    headers={'Host':host,'Origin':'https://'+host,'X-Study-Token':state['token'],'Cookie':'shizhi_share='+client.cookies.get('shizhi_share')}
    assert client.get('/api/bootstrap',headers=headers).status_code==200
    assert client.post('/api/plans/generate',json={'budget':20},headers=headers).status_code==200
    assert client.post('/api/plans/generate',json={'budget':20},headers={**headers,'Origin':'https://another.trycloudflare.com'}).status_code==403
    assert client.get('/api/bootstrap',headers={'Cookie':'shizhi_share=forged'}).status_code==401


def test_share_mode_refuses_personal_storage(tmp_path):
    env=os.environ.copy()
    env.update(LOCALAPPDATA=str(tmp_path),STUDY_SHARE_MODE='1')
    env.pop('STUDY_DATA_DIR',None)
    response=subprocess.run([sys.executable,'-c','import backend.store'],env=env,capture_output=True)
    assert response.returncode!=0
    assert not (tmp_path/'ShizhiStudy').exists()
