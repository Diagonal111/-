import io
import json
import mimetypes
import os
import secrets
import zipfile
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import ai, backups, rag, store, sharing
from .imports import MAX_FILE, extract_material, normalize_type, save_image
from .learning import RESULTS, SUBJECTS, candidates, derive_state, local_day, make_plan
from .store import DB_PATH, FILES, ROOT, clear_demo, connect, dump, init_db, now, question_dict, set_setting, setting, today, uid

SESSION_TOKEN=secrets.token_urlsafe(32)
# Windows registry MIME mappings can classify .js as text/plain, which blocks modules.
mimetypes.add_type('application/javascript','.js')
mimetypes.add_type('application/javascript','.mjs')
mimetypes.add_type('text/css','.css')


@asynccontextmanager
async def lifespan(app):
    init_db()
    if sharing.ENABLED:
        from .practice_bank import install
        with connect() as db:
            install(db)
    yield


app=FastAPI(title='拾知 · Personal Study',lifespan=lifespan,docs_url=None if sharing.ENABLED else '/docs',redoc_url=None if sharing.ENABLED else '/redoc',openapi_url=None if sharing.ENABLED else '/openapi.json')


@app.middleware('http')
async def local_writes(request:Request,call_next):
    if request.url.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('x-study-token')!=SESSION_TOKEN:
            return JSONResponse({'detail':'页面会话已过期，请刷新后再试。'},status_code=403)
        origin=request.headers.get('origin')
        allowed=sharing.origin_allowed(request,origin) if sharing.ENABLED else origin in ('http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173')
        if origin and not allowed:
            return JSONResponse({'detail':'只接受本机学习页面的请求。'},status_code=403)
    response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response


sharing.install(app)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver']+(['*.trycloudflare.com'] if sharing.ENABLED else []))


class PlanInput(BaseModel):
    budget:int=Field(default=60,ge=5,le=240)


class QuestionInput(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    body:str=Field(min_length=1,max_length=18000)
    knowledge_id:str
    type:Literal['single','multiple','boolean','calculation']='calculation'
    options:list[str]=Field(default_factory=list,max_length=8)
    answer:str=Field(default='',max_length=12000)
    explanation:str=Field(default='',max_length=20000)
    minutes:int=Field(default=12,ge=1,le=90)
    verified:bool=False
    attachments:list[str]=Field(default_factory=list,max_length=12)
    source:str=Field(default='手动录入',max_length=300)
    revision:int=Field(default=1,ge=1)


class AttemptInput(BaseModel):
    question_id:str
    revision:int|None=Field(default=None,ge=1)
    answer:str=Field(default='',max_length=20000)
    photos:list[str]=Field(default_factory=list,max_length=8)
    hinted:bool=False
    elapsed:int=Field(default=0,ge=0,le=1440)


class ConfirmInput(BaseModel):
    grade:Literal['correct','partial','incorrect']
    version:int=0


class TranscriptionInput(BaseModel):
    text:str=Field(min_length=1,max_length=20000)
    version:int=0


class AIGradeOutput(BaseModel):
    transcription:str=''
    grade:Literal['correct','partial','incorrect','unknown']
    summary:str=''
    steps:list[dict[str,str]]=Field(default_factory=list,max_length=80)
    uncertainties:list[str]=Field(default_factory=list,max_length=30)
    error_types:list[str]=Field(default_factory=list,max_length=20)


class AITranscriptionOutput(BaseModel):
    transcription:str=Field(min_length=1,max_length=20000)
    uncertainties:list[str]=Field(default_factory=list,max_length=30)


class RAGCitation(BaseModel):
    question_id:str
    reason:str=Field(default='',max_length=300)


class RAGExplainOutput(BaseModel):
    answer:str=Field(min_length=1,max_length=5000)
    citations:list[RAGCitation]=Field(default_factory=list,max_length=10)
    recommended_question_ids:list[str]=Field(default_factory=list,max_length=5)
    uncertainties:list[str]=Field(default_factory=list,max_length=20)


class AIConfigInput(BaseModel):
    base_url:str=Field(max_length=500)
    model:str=Field(default='',max_length=200)
    api_key:str=Field(default='',max_length=4000)
    json_mode:bool=True
    clear_key:bool=False


class ImportConfirmInput(BaseModel):
    items:list[QuestionInput]=Field(min_length=1,max_length=30)
    version:int=Field(default=0,ge=0)


class DraftQuestionInput(QuestionInput):
    title:str=Field(default='',max_length=200)
    body:str=Field(default='',max_length=18000)
    warnings:list[str]=Field(default_factory=list,max_length=30)


class ImportDraftInput(BaseModel):
    items:list[DraftQuestionInput]=Field(min_length=1,max_length=30)
    version:int=Field(default=0,ge=0)


class AttemptStatusInput(BaseModel):
    action:Literal['void','restore']
    version:int=Field(ge=0)


class RestoreInput(BaseModel):
    token:str=Field(min_length=32,max_length=32)


def get_question(db,id_):
    q=db.execute('SELECT q.*,k.name AS knowledge,k.subject,k.chapter FROM questions q JOIN knowledge k ON k.id=q.knowledge_id WHERE q.id=?',(id_,)).fetchone()
    if not q:
        raise HTTPException(404,'题目不存在')
    return question_dict(q)


def validate_question(db,q):
    if not q.title.strip() or not q.body.strip():
        raise HTTPException(400,'请填写题目标题和完整题干')
    if not db.execute('SELECT 1 FROM knowledge WHERE id=?',(q.knowledge_id,)).fetchone():
        raise HTTPException(400,'请选择有效的知识点')
    if q.type in ('single','multiple'):
        if len(q.options)<2 or any(not o.strip() for o in q.options):
            raise HTTPException(400,'选择题至少需要两个非空选项')
        expected=[s.strip().upper() for s in q.answer.replace('，',',').split(',') if s.strip()]
        if q.verified and (not expected or any(s not in list('ABCDEFGH')[:len(q.options)] for s in expected) or (q.type=='single' and len(expected)!=1)):
            raise HTTPException(400,'选择题参考答案请使用 A 或 A,B 格式，并对应有效选项')
    elif q.type=='boolean' and q.verified and q.answer not in ('正确','错误'):
        raise HTTPException(400,'判断题答案请选择“正确”或“错误”')
    if q.verified and not q.answer.strip():
        raise HTTPException(400,'请先补充并核实参考答案')
    for name in q.attachments:
        if '/' in name or '\\' in name or not (FILES/name).is_file():
            raise HTTPException(400,'题目附件不存在')


def insert_question(db,q):
    id_=uid('q')
    db.execute('''INSERT INTO questions(id,knowledge_id,type,title,body,options,answer,explanation,minutes,verified,attachments,source,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',(id_,q.knowledge_id,q.type,q.title,q.body,dump(q.options),q.answer,q.explanation,q.minutes,int(q.verified),dump(q.attachments),q.source,now()))
    snapshot=question_dict(db.execute('SELECT * FROM questions WHERE id=?',(id_,)).fetchone())
    db.execute('INSERT INTO question_revisions VALUES (?,?,?,?)',(id_,1,dump(snapshot),now()))
    rag.refresh_question(db,id_)
    return id_


@app.get('/api/bootstrap')
def bootstrap():
    with connect() as db:
        kp,questions,reviews,attempts=derive_state(db)
        plan_row=db.execute('SELECT * FROM plans WHERE day=? ORDER BY created_at DESC,id DESC LIMIT 1',(today().isoformat(),)).fetchone()
        plan=None
        if plan_row:
            plan=dict(plan_row)
            stored=json.loads(plan['tasks'])
            plan.update(stored)
            plan['summary']=json.loads(plan['summary']) if plan['summary'] else None
        qlist=[]
        for q in questions.values():
            qlist.append({**q,'knowledge':kp[q['knowledge_id']]['name'],'subject':kp[q['knowledge_id']]['subject'],'review':reviews.get(q['id'])})
        days=[]
        for offset in range(-6,1):
            day=today()+timedelta(days=offset)
            matches=[a for a in attempts if local_day(a['created_at'])==day]
            days.append({'date':day.isoformat(),'count':len(matches),'correct':sum(a['grade']=='correct' for a in matches)})
        today_attempts=[a for a in attempts if local_day(a['created_at'])==today()]
        due=sum(r['due_date']<=today().isoformat() for r in reviews.values())
        cfg=ai.config()
        return {
            'app':'shizhi','token':SESSION_TOKEN,'date':today().isoformat(),'demo_mode':setting(db,'demo_mode',False),'share_mode':sharing.ENABLED,
            'budget':setting(db,'budget',60),'knowledge':list(kp.values()),'questions':qlist,'plan':plan,
            'stats':{'due':due,'mistakes':sum(r['had_error'] and r['mistake_status']!='已稳定' for r in reviews.values()),
                     'done_today':len(today_attempts),'question_count':len(qlist),'week':days,
                     'practiced':sum(k['evidence']>0 for k in kp.values()),'knowledge_count':len(kp)},
            'ai':{**cfg,'configured':bool(ai.api_key() and cfg.get('model')),'has_key':bool(ai.api_key())},
        }


@app.post('/api/workspace/start')
def start_workspace():
    with connect() as db:
        clear_demo(db)
    return {'ok':True}


@app.get('/api/questions/{id_}')
def question(id_:str):
    with connect() as db:
        q=get_question(db,id_)
        _,_,reviews,_=derive_state(db)
        history=[dict(r) for r in db.execute('SELECT id,grade,status,created_at,hinted,version FROM attempts WHERE question_id=? ORDER BY created_at DESC,id DESC LIMIT 12',(id_,))]
    return {**q,'review':reviews.get(id_),'history':history}


@app.post('/api/questions/{id_}/explain')
async def explain_question(id_:str):
    with connect() as db:
        epoch=store.WORKSPACE_EPOCH
        q=get_question(db,id_)
        related=rag.retrieve(db, id_, q['knowledge_id'], q['subject'],
                             f"{q['title']} {q['body']} {q['knowledge']}", limit=5)
        history=[]
        for row in db.execute('''SELECT grade, created_at, ai_result FROM attempts
                                 WHERE question_id=? AND status='confirmed'
                                 ORDER BY created_at DESC LIMIT 8''', (id_,)).fetchall():
            item={'grade':row['grade'], 'created_at':row['created_at']}
            if row['ai_result']:
                value=json.loads(row['ai_result'])
                if value.get('error_types'):
                    item['error_types']=value['error_types'][:5]
            history.append(item)
    result=await ai.call_json(ai.RAG_EXPLAIN_INSTRUCTION, {
        'current_question': {key:q[key] for key in (
            'id','title','body','options','answer','explanation','knowledge','subject','verified')},
        'related_questions': [{key:item.get(key,'') for key in (
            'question_id','title','body','explanation','answer','knowledge','subject','type','content')}
            for item in related],
        'learner_history': history,
    })
    try:
        validated=RAGExplainOutput.model_validate(result)
    except ValueError:
        raise HTTPException(502,'错题讲解结果格式无效，请重试。')
    allowed={id_}|{item['question_id'] for item in related}
    citations=[]
    related_by_id={item['question_id']:item for item in related}
    for citation in validated.citations:
        if citation.question_id not in allowed:
            continue
        source=q if citation.question_id==id_ else related_by_id[citation.question_id]
        citations.append({'question_id':citation.question_id,'title':source['title'],
                          'knowledge':source.get('knowledge',q['knowledge']),
                          'reason':citation.reason})
    recommendations=[]
    for question_id in validated.recommended_question_ids:
        source=related_by_id.get(question_id)
        if source and question_id!=id_ and question_id not in {item['question_id'] for item in recommendations}:
            recommendations.append({'question_id':question_id,'title':source['title'],
                                     'knowledge':source['knowledge']})
    with connect() as db:
        if epoch!=store.WORKSPACE_EPOCH:
            raise HTTPException(409,'学习数据已改变，请基于最新题目重新讲解。')
    return {'answer':validated.answer,'citations':citations,
            'recommendations':recommendations,'uncertainties':validated.uncertainties,
            'retrieved_count':len(related)}


@app.post('/api/questions')
def create_question(value:QuestionInput):
    with connect() as db:
        validate_question(db,value)
        clear_demo(db)
        id_=insert_question(db,value)
    return {'id':id_}


@app.patch('/api/questions/{id_}')
def update_question(id_:str,value:QuestionInput):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=get_question(db,id_)
        validate_question(db,value)
        if existing['revision']!=value.revision:
            raise HTTPException(409,'题目已在其他页面修改，请重新打开后编辑。')
        db.execute('''UPDATE questions SET knowledge_id=?,type=?,title=?,body=?,options=?,answer=?,explanation=?,minutes=?,verified=?,attachments=?,source=? WHERE id=?''',
                   (value.knowledge_id,value.type,value.title,value.body,dump(value.options),value.answer,value.explanation,value.minutes,int(value.verified),dump(value.attachments),value.source,id_))
        db.execute('UPDATE questions SET revision=revision+1 WHERE id=?',(id_,))
        updated=get_question(db,id_)
        db.execute('INSERT INTO question_revisions VALUES (?,?,?,?)',(id_,updated['revision'],dump(updated),now()))
        rag.refresh_question(db,id_)
        db.execute("UPDATE attempts SET status='outdated' WHERE question_id=? AND status='pending'",(id_,))
        # Preserve plan snapshots and make stale content visible until explicit replanning.
        for plan_row in db.execute('SELECT id,tasks FROM plans WHERE day=?',(today().isoformat(),)).fetchall():
            plan=json.loads(plan_row['tasks'])
            plan['stale']=True
            db.execute('UPDATE plans SET tasks=?,summary=NULL WHERE id=?',(dump(plan),plan_row['id']))
    return {'ok':True,'revision':updated['revision']}


@app.post('/api/uploads')
async def upload(file:UploadFile=File(...)):
    content=await file.read(MAX_FILE+1)
    name=await run_in_threadpool(save_image,content)
    return {'name':name,'url':'/attachments/'+name}


@app.post('/api/attempts')
def create_attempt(value:AttemptInput):
    with connect() as db:
        q=get_question(db,value.question_id)
        if value.revision is not None and value.revision!=q['revision']:
            raise HTTPException(409,'题目已在其他页面更新，请关闭后重新打开作答。')
        if not value.answer.strip() and not value.photos:
            raise HTTPException(400,'请填写答案或上传作答照片')
        # Validate file references before saving the attempt or calling any model.
        for name in value.photos:
            if '/' in name or '\\' in name or not (FILES/name).is_file():
                raise HTTPException(400,'作答照片不存在，请重新上传')
        id_=uid('attempt')
        result=None
        if q['type'] in ('single','multiple','boolean') and value.answer.strip():
            expected={s.strip().upper() for s in q['answer'].replace('，',',').split(',')}
            actual={s.strip().upper() for s in value.answer.replace('，',',').split(',')}
            correct=actual==expected
            result={'mode':'objective','grade':('correct' if correct else 'incorrect') if q['verified'] else 'unknown',
                    'summary':('答案与参考答案一致。' if correct else '答案与参考答案不一致。') if q['verified'] else '参考答案尚未核实，请先核实后再确认。',
                    'transcription':value.answer,'steps':[],'uncertainties':[]}
        db.execute('INSERT INTO attempts(id,question_id,answer,photos,hinted,elapsed,ai_result,created_at) VALUES (?,?,?,?,?,?,?,?)',
                   (id_,q['id'],value.answer,dump(value.photos),int(value.hinted),value.elapsed,dump(result) if result else None,now()))
        db.execute('UPDATE attempts SET question_snapshot=? WHERE id=?',(dump(q),id_))
    return {'id':id_,'result':result,'version':0}


@app.post('/api/attempts/{id_}/grade')
async def grade_attempt(id_:str):
    with connect() as db:
        epoch=store.WORKSPACE_EPOCH
        a=db.execute('SELECT * FROM attempts WHERE id=?',(id_,)).fetchone()
        if not a:
            raise HTTPException(404,'作答记录不存在')
        if a['status']!='pending':
            raise HTTPException(409,'该作答已确认或题目已更改，请重新打开题目')
        q=json.loads(a['question_snapshot']) or get_question(db,a['question_id'])
        a=dict(a)
    photos=[] if a['transcription_override'] else json.loads(a['photos'])
    workflow=[]
    transcription_uncertainties=[]
    student_answer=a['transcription_override'] or a['answer']
    question_payload={key:q[key] for key in ('body','options','answer','explanation','verified')}
    if photos:
        try:
            transcript=await ai.call_json(ai.TRANSCRIBE_INSTRUCTION,{
                'question_title':q['title'],
                'existing_text':student_answer,
                'task':'仅转写照片中的作答，不回答题目',
            },photos)
            transcript=AITranscriptionOutput.model_validate(transcript)
        except ValueError:
            raise HTTPException(502,'照片转写结果无效，请重试，或改用文字输入')
        student_answer=transcript.transcription
        transcription_uncertainties=transcript.uncertainties
        workflow.append({'step':'照片转写','status':'完成'})
    result=await ai.call_json(ai.GRADE_INSTRUCTION,{
        'question':question_payload,
        'student_answer':student_answer,
        'transcription_corrected_by_user':bool(a['transcription_override']),
        'transcription_uncertainties':transcription_uncertainties,
    })
    try:
        result=AIGradeOutput.model_validate(result).model_dump()
        if any(not all(key in step for key in ('quote','verdict','reason')) for step in result['steps']):
            raise ValueError('steps')
    except ValueError:
        raise HTTPException(502,'模型批改结构无效，请重试，或转为自评')
    result['mode']='ai'
    if workflow:
        result['transcription']=student_answer
        result['workflow']=workflow+[{'step':'依据题目与参考答案批改','status':'完成'}]
        result['uncertainties']=list(dict.fromkeys(transcription_uncertainties+result['uncertainties']))
    if not q['verified']:
        result['grade']='unknown'
        result['summary']='参考答案未核实，本次仅供参考，不更新掌握度。'
    with connect() as db:
        if epoch!=store.WORKSPACE_EPOCH:
            raise HTTPException(409,'学习数据已恢复，请重新打开作答记录。')
        changed=db.execute("UPDATE attempts SET ai_result=? WHERE id=? AND status='pending' AND version=?",(dump(result),id_,a['version'])).rowcount
        if not changed:
            raise HTTPException(409,'作答状态已改变，请刷新')
    return result


@app.patch('/api/attempts/{id_}/transcription')
def correct_transcription(id_:str,value:TranscriptionInput):
    with connect() as db:
        changed=db.execute("UPDATE attempts SET transcription_override=?,ai_result=NULL,version=version+1 WHERE id=? AND version=? AND status='pending'",
                           (value.text,id_,value.version)).rowcount
        if not changed:
            raise HTTPException(409,'作答状态已改变，请刷新后重试')
    return {'version':value.version+1}


def commit_grade(db,id_,value):
    a=db.execute('SELECT * FROM attempts WHERE id=?',(id_,)).fetchone()
    if not a:
        raise HTTPException(404,'作答记录不存在')
    if a['status'] in ('outdated','voided'):
        raise HTTPException(409,'题目已更改，这次作答已过期，请重新作答')
    if a['status']=='confirmed' and a['grade']==value.grade and a['version']==value.version+1:
        return {'ok':True,'idempotent':True}
    if a['version']!=value.version:
        raise HTTPException(409,'作答已被修改，请刷新后再确认')
    q=json.loads(a['question_snapshot']) or get_question(db,a['question_id'])
    if not q['verified']:
        raise HTTPException(409,'参考答案尚未核实，本次结果已保留，但不能更新学习状态')
    stamp=now()
    changed=db.execute('UPDATE attempts SET grade=?,status=?,confirmed_at=?,version=version+1 WHERE id=? AND version=?',
                       (value.grade,'confirmed',stamp,id_,value.version)).rowcount
    if not changed:
        raise HTTPException(409,'状态冲突，请刷新')
    db.execute('INSERT INTO grading_history(attempt_id,version,grade,confirmed_at) VALUES (?,?,?,?)',(id_,value.version+1,value.grade,stamp))
    # Current day's completion is kept in the persisted plan; state itself is replayed from attempts.
    sync_today_plan(db)
    return {'ok':True,'version':value.version+1}


def sync_today_plan(db):
    row=db.execute('SELECT * FROM plans WHERE day=? ORDER BY created_at DESC,id DESC LIMIT 1',(today().isoformat(),)).fetchone()
    if not row:
        return
    confirmed={(a['question_id'],json.loads(a['question_snapshot']).get('revision',1)) for a in db.execute("SELECT * FROM attempts WHERE status='confirmed'") if local_day(a['created_at'])==today()}
    value=json.loads(row['tasks'])
    for task in value['tasks']:
        task['status']='done' if (task['question_id'],task.get('revision',1)) in confirmed else 'todo'
    value['stale']=True
    db.execute('UPDATE plans SET tasks=?,summary=NULL WHERE id=?',(dump(value),row['id']))


@app.get('/api/attempts')
def list_attempts(status:str='all',query:str='',offset:int=0,limit:int=30):
    if status not in ('all','confirmed','pending','voided','outdated') or offset<0 or not 1<=limit<=100:
        raise HTTPException(400,'筛选参数无效')
    with connect() as db:
        rows=db.execute('SELECT a.*,q.title,q.knowledge_id,k.name AS knowledge,k.subject FROM attempts a JOIN questions q ON q.id=a.question_id JOIN knowledge k ON k.id=q.knowledge_id ORDER BY a.created_at DESC,a.id DESC').fetchall()
        points={r['id']:dict(r) for r in db.execute('SELECT * FROM knowledge')}
        result=[]
        for row in rows:
            item=dict(row)
            snapshot=json.loads(item['question_snapshot'])
            item['title']=snapshot.get('title',item['title'])
            point=points.get(snapshot.get('knowledge_id',item['knowledge_id']),{})
            item['knowledge']=snapshot.get('knowledge',point.get('name',item['knowledge']))
            item['subject']=snapshot.get('subject',point.get('subject',item['subject']))
            if status!='all' and item['status']!=status:
                continue
            if query.lower() not in f"{item['title']} {item['knowledge']} {item['answer']}".lower():
                continue
            result.append({key:item[key] for key in ('id','question_id','title','knowledge','subject','grade','status','created_at','confirmed_at','hinted','version','is_demo')})
    return {'items':result[offset:offset+limit],'total':len(result)}


@app.get('/api/attempts/{id_}')
def attempt_detail(id_:str):
    with connect() as db:
        row=db.execute('SELECT * FROM attempts WHERE id=?',(id_,)).fetchone()
        if not row:
            raise HTTPException(404,'作答记录不存在')
        value=dict(row)
        current=get_question(db,value['question_id'])
        snapshot=json.loads(value['question_snapshot']) or current
        point=db.execute('SELECT * FROM knowledge WHERE id=?',(snapshot['knowledge_id'],)).fetchone()
        snapshot.update(knowledge=point['name'],subject=point['subject'])
        value.update(question=snapshot,photos=json.loads(value['photos']),
                     ai_result=json.loads(value['ai_result']) if value['ai_result'] else None,
                     current_revision=current['revision'],
                     revisions=[dict(r) for r in db.execute('SELECT version,grade,confirmed_at,action FROM grading_history WHERE attempt_id=? ORDER BY version DESC',(id_,))])
    return value


@app.post('/api/attempts/{id_}/status')
def change_attempt_status(id_:str,value:AttemptStatusInput):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        a=db.execute('SELECT * FROM attempts WHERE id=?',(id_,)).fetchone()
        if not a or a['version']!=value.version:
            raise HTTPException(409,'记录已改变，请刷新后再试')
        if value.action=='void' and a['status'] not in ('confirmed','pending'):
            raise HTTPException(409,'只能撤销已确认或待确认记录')
        if value.action=='restore' and a['status']!='voided':
            raise HTTPException(409,'只有已撤销记录可以恢复')
        status='voided' if value.action=='void' else 'confirmed' if a['grade'] else 'pending'
        q=get_question(db,a['question_id'])
        snapshot=json.loads(a['question_snapshot']) or q
        if status=='pending' and snapshot.get('revision',1)!=q['revision']:
            status='outdated'
        db.execute('UPDATE attempts SET status=?,version=version+1 WHERE id=?',(status,id_))
        db.execute('INSERT INTO grading_history(attempt_id,version,grade,confirmed_at,action) VALUES (?,?,?,?,?)',
                   (id_,value.version+1,a['grade'] or 'unknown',now(),value.action))
        sync_today_plan(db)
    return {'ok':True,'status':status,'version':value.version+1}


@app.post('/api/attempts/{id_}/confirm')
def confirm_attempt(id_:str,value:ConfirmInput):
    with connect() as db:
        # A short immediate transaction makes duplicate concurrent confirmations deterministic.
        db.execute('BEGIN IMMEDIATE')
        result=commit_grade(db,id_,value)
        kp,_,reviews,_=derive_state(db)
        a=db.execute('SELECT * FROM attempts WHERE id=?',(id_,)).fetchone()
        q=json.loads(a['question_snapshot']) or get_question(db,a['question_id'])
        result.update(knowledge=kp[q['knowledge_id']],review=reviews.get(q['id']))
    return result


@app.post('/api/plans/generate')
def generate_plan(value:PlanInput):
    with connect() as db:
        previous=db.execute('SELECT tasks FROM plans WHERE day=? ORDER BY created_at DESC,id DESC LIMIT 1',(today().isoformat(),)).fetchone()
        versions={q['id']:q['revision'] for q in db.execute('SELECT id,revision FROM questions')}
        completed=[t for t in json.loads(previous['tasks'])['tasks'] if t['status']=='done' and t.get('revision',1)==versions.get(t['question_id'])] if previous else []
        completed_minutes=sum(t['minutes'] for t in completed)
        if completed_minutes>value.budget:
            raise HTTPException(409,f'已完成任务预计占用 {completed_minutes} 分钟，请把今日预算设为至少这个时长。')
        plan=make_plan(db,value.budget-completed_minutes,exclude={t['question_id'] for t in completed})
        plan['budget']=value.budget
        plan['tasks']=completed+plan['tasks']
        plan['study_minutes']+=completed_minutes
        plan['total_minutes']+=completed_minutes
        id_=uid('plan')
        db.execute('INSERT INTO plans(id,day,budget,tasks,created_at) VALUES (?,?,?,?,?)',
                   (id_,today().isoformat(),value.budget,dump(plan),now()))
        set_setting(db,'budget',value.budget)
    return {'id':id_,**plan}


@app.post('/api/plans/{id_}/explain')
async def explain_plan(id_:str):
    with connect() as db:
        epoch=store.WORKSPACE_EPOCH
        row=db.execute('SELECT * FROM plans WHERE id=?',(id_,)).fetchone()
        if not row:
            raise HTTPException(404,'计划不存在')
        plan=json.loads(row['tasks'])
    result=await ai.call_json('你是学习计划解释助手。仅依据给定任务与理由写简短中文建议，不增删任务、不推断未提供的历史、不修改时间。返回 {"summary":"最多100字","tasks":[{"id":"原任务ID","explanation":"最多80字"}]}。',{'budget':row['budget'],'tasks':plan['tasks']})
    if not isinstance(result.get('summary'),str) or not isinstance(result.get('tasks',[]),list):
        raise HTTPException(502,'计划解释格式无效，已保留规则计划')
    allowed={t['id'] for t in plan['tasks']}
    validated={'summary':result['summary'][:500],'tasks':[
        {'id':t['id'],'explanation':str(t.get('explanation',''))[:400]}
        for t in result.get('tasks',[]) if isinstance(t,dict) and t.get('id') in allowed
    ]}
    with connect() as db:
        if epoch!=store.WORKSPACE_EPOCH or not db.execute('UPDATE plans SET summary=? WHERE id=? AND tasks=?',(dump(validated),id_,row['tasks'])).rowcount:
            raise HTTPException(409,'计划或学习数据已改变，请基于最新计划重新解读。')
    return validated


@app.post('/api/imports')
async def import_file(file:UploadFile=File(...)):
    content=await file.read(MAX_FILE+1)
    if len(content)>MAX_FILE:
        raise HTTPException(413,'首版单个文件最多 12 MB，请分批导入')
    filename=Path(file.filename or '未命名文件').name
    try:
        material=await run_in_threadpool(extract_material,filename,content)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400,'材料解析失败，请检查格式，或改为题目照片上传。')
    items=material['items']
    warnings=material['warnings']
    mode='structured' if items else 'manual'
    with connect() as db:
        kp=[dict(r) for r in db.execute('SELECT * FROM knowledge')]
    if not items and ai.api_key() and ai.config().get('model'):
        result=await ai.call_json(ai.IMPORT_INSTRUCTION,{'text':material['text'],'image_files':material['images'],'knowledge_points':kp},material['images'])
        items=result.get('items',[])
        if not isinstance(items,list) or any(not isinstance(i,dict) for i in items):
            raise HTTPException(502,'AI 题目列表格式错误，请重试')
        warnings.extend(str(w) for w in result.get('warnings',[]) if isinstance(w,str))
        mode='ai'
    elif not items:
        warnings.append('未配置 AI：已提取原文和图片，可先手动整理为题目；配置模型后可重新识别。')
        items=[{'title':filename.rsplit('.',1)[0],'body':material['text'] or '请根据题目图片补充题干。','type':'calculation',
                'options':[],'answer':'','explanation':'','knowledge_id':'cache','minutes':12,'warnings':['此条仅为材料草稿，尚未自动拆题。']}]
    normalized=[]
    kp_ids={k['id'] for k in kp}
    for item in items[:30]:
        kid=item.get('knowledge_id')
        if kid not in kp_ids:
            matched=next((k['id'] for k in kp if k['name']==kid),None)
            kid=matched or 'cache'
            item.setdefault('warnings',[])
            if not isinstance(item['warnings'],list):
                item['warnings']=[]
            if not matched:
                item['warnings'].append('知识点为默认值，请重新选择。')
        options=item.get('options',[])
        if not isinstance(options,list):
            options=[]
        typ=normalize_type(item.get('type'),options)
        if typ=='boolean':
            options=['正确','错误']
        normalized.append({
            'title':str(item.get('title','未命名题目'))[:200],
            'body':str(item.get('body',''))[:18000], 'type':typ,'options':[str(o) for o in options[:8]],
            'answer':str(item.get('answer',''))[:12000],'explanation':str(item.get('explanation',''))[:20000],
            'knowledge_id':kid,'minutes':12 if typ=='calculation' else 3,'verified':False,
            'source':str(item.get('source',filename))[:300],
            'attachments':material['images'],
            'warnings':item.get('warnings',[]),
        })
    id_=uid('import')
    with connect() as db:
        db.execute('INSERT INTO imports(id,name,items,warnings,status,created_at) VALUES (?,?,?,?,?,?)',(id_,filename,dump(normalized),dump(warnings),'review',now()))
    return {'id':id_,'name':filename,'items':normalized,'warnings':warnings,'mode':mode,'version':0}


@app.post('/api/imports/{id_}/confirm')
def confirm_import(id_:str,value:ImportConfirmInput):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM imports WHERE id=?',(id_,)).fetchone()
        if not row:
            raise HTTPException(404,'导入任务不存在')
        if row['status']=='confirmed':
            raise HTTPException(409,'本批题目已入库，请勿重复提交')
        if row['version']!=value.version:
            raise HTTPException(409,'草稿已在其他页面更新，请重新打开再校对')
        for q in value.items:
            validate_question(db,q)
        clear_demo(db)
        ids=[insert_question(db,q) for q in value.items]
        db.execute('UPDATE imports SET status=?,items=?,version=version+1 WHERE id=?',('confirmed',dump([q.model_dump() for q in value.items]),id_))
    return {'ids':ids,'count':len(ids)}


@app.patch('/api/imports/{id_}')
def save_import_draft(id_:str,value:ImportDraftInput):
    with connect() as db:
        changed=db.execute("UPDATE imports SET items=?,version=version+1 WHERE id=? AND status='review' AND version=?",(dump([q.model_dump() for q in value.items]),id_,value.version)).rowcount
        if not changed:
            raise HTTPException(409,'草稿已在其他页面更新或已入库，请关闭后重新打开；当前编辑尚未覆盖服务器内容。')
    return {'ok':True,'version':value.version+1}


@app.get('/api/imports')
def pending_imports():
    with connect() as db:
        rows=db.execute("SELECT * FROM imports WHERE status='review' ORDER BY created_at DESC LIMIT 10").fetchall()
    return [{**dict(r),'items':json.loads(r['items']),'warnings':json.loads(r['warnings'])} for r in rows]


@app.post('/api/settings/ai')
def save_ai(value:AIConfigInput):
    url=ai.validate_url(value.base_url)
    from urllib.parse import urlsplit
    model=value.model.strip()
    if urlsplit(url).hostname=='api.deepseek.com' and (model.lower()=='ds' or any(c.isspace() for c in model)):
        raise HTTPException(400,'请填写 DeepSeek 的 API 模型 ID，例如 deepseek-flash；ds 或 deepseek v4.1 flash 不是有效的模型 ID。')
    if value.api_key.strip():
        ai.SESSION_KEY=value.api_key.strip()
    if value.clear_key:
        ai.SESSION_KEY=''
    with connect() as db:
        set_setting(db,'ai_config',{'base_url':url,'model':value.model.strip(),'json_mode':value.json_mode})
    return {'ok':True,'configured':bool(ai.api_key() and value.model.strip())}


@app.get('/api/export')
def export_data():
    return Response(backups.export_bytes(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="shizhi-backup-{today().isoformat()}.zip"'})


@app.post('/api/backups/validate')
async def validate_backup(file:UploadFile=File(...)):
    raw=await file.read(backups.MAX_ARCHIVE+1)
    return await run_in_threadpool(backups.stage,raw)


@app.post('/api/backups/restore')
def restore_backup(value:RestoreInput):
    return backups.restore(value.token)


@app.get('/api/backups/safety')
def safety_backups():
    folder=backups.store.DB_PATH.parent/'backups'
    return [{'name':p.name,'bytes':p.stat().st_size} for p in sorted(folder.glob('before-restore-*.zip'),reverse=True)][:10]


@app.get('/api/backups/safety/{name}')
def download_safety_backup(name:str):
    import re
    if not re.fullmatch(r'before-restore-\d{4}-\d{2}-\d{2}-[a-f0-9]{8}\.zip',name):
        raise HTTPException(404,'备份不存在')
    path=backups.store.DB_PATH.parent/'backups'/name
    if not path.is_file():
        raise HTTPException(404,'备份不存在')
    return FileResponse(path,filename=name,media_type='application/zip')


@app.get('/api/template')
def excel_template():
    from openpyxl import Workbook
    wb=Workbook()
    ws=wb.active
    ws.title='题库模板'
    ws.append(['标题','题干','题型','A','B','C','D','答案','解析','知识点'])
    ws.append(['分页基础','页面大小为4KB时，页内偏移占多少位？','单选题','10位','12位','14位','16位','B','4KB=2^12 B，按字节编址时页内偏移为12位。','分页与地址转换'])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width=24
    out=io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="shizhi-question-template.xlsx"'})


app.mount('/attachments',StaticFiles(directory=str(FILES)),name='attachments')
DIST=Path(__file__).resolve().parent.parent/'dist'
if DIST.is_dir():
    app.mount('/',StaticFiles(directory=str(DIST),html=True),name='web')
else:
    @app.get('/')
    def development_hint():
        return {'message':'前端尚未构建。运行 npm run build 后重启，或使用 npm run dev。'}
