"""Validate portable backups as data, never execute SQL supplied by an archive."""
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from PIL import Image
from . import store

TABLES=['settings','knowledge','questions','attempts','grading_history','plans','imports','question_revisions']
MAX_ARCHIVE=100*1024*1024
MAX_EXPANDED=250*1024*1024
STAGED={}
SCHEMA=2


def sha(data):
    return hashlib.sha256(data).hexdigest()


def export_bytes():
    memory=sqlite3.connect(':memory:')
    try:
        with store.connect() as db:
            db.backup(memory)
            contents={'study.db':memory.serialize()}
            for path in store.FILES.glob('*.jpg'):
                contents['attachments/'+path.name]=path.read_bytes()
    finally:
        memory.close()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in contents.items():
            archive.writestr(name,data)
        archive.writestr('manifest.json',store.dump({
            'app':'shizhi','version':SCHEMA,'exported_at':store.now(),'timezone':'Asia/Shanghai',
            'files':{name:sha(data) for name,data in contents.items()},
        }))
    return output.getvalue()


def invalid(message='备份结构或内容无效，请选择由拾知导出的完整备份。'):
    raise HTTPException(400,message)


def validate_bytes(raw):
    if len(raw)>MAX_ARCHIVE:
        raise HTTPException(413,'备份文件最多 100 MB。')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos=archive.infolist()
            names=[i.filename for i in infos]
            if len(names)>5000 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>MAX_EXPANDED:
                invalid('备份文件重复、过多或解压体积过大。')
            if not {'study.db','manifest.json'}.issubset(names):
                invalid()
            if any(n not in ('study.db','manifest.json') and not re.fullmatch(r'attachments/[a-f0-9]{32}\.jpg',n) for n in names):
                invalid('备份包含不允许的路径或文件，未恢复任何数据。')
            if archive.getinfo('study.db').file_size>30*1024*1024 or archive.getinfo('manifest.json').file_size>2*1024*1024:
                invalid('数据库或清单体积超过当前版本支持范围。')
            contents={n:archive.read(n) for n in names}
        manifest=json.loads(contents.pop('manifest.json'))
        if manifest.get('app')!='shizhi' or manifest.get('version') not in (1,2):
            invalid('这不是兼容的拾知备份版本。')
        if manifest['version']==2:
            if manifest.get('files')!={n:sha(v) for n,v in contents.items()}:
                invalid('备份校验和不一致，文件可能不完整。')
        for name,data in contents.items():
            if name.startswith('attachments/'):
                with Image.open(io.BytesIO(data)) as image:
                    if image.format!='JPEG' or image.width*image.height>35_000_000:
                        invalid('备份包含无效照片。')
                    image.verify()
        # Read fixed tables from a read-only temporary database; never executes its schema.
        with tempfile.TemporaryDirectory(prefix='shizhi-validate-') as directory:
            path=Path(directory)/'study.db'
            path.write_bytes(contents['study.db'])
            source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            try:
                source.row_factory=sqlite3.Row
                source.execute('PRAGMA trusted_schema=OFF')
                schema={r['name']:r['type'] for r in source.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
                if any(schema.get(n)!='table' for n in TABLES[:-1]) or any(t not in ('table','index') for t in schema.values()):
                    invalid('备份数据库含不支持的结构。')
                if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or source.execute('PRAGMA foreign_key_check').fetchone():
                    invalid('备份数据库完整性检查失败。')
                rows={n:[dict(r) for r in source.execute(f'SELECT * FROM {n}')] if n in schema else [] for n in TABLES}
                columns={n:{r['name'] for r in source.execute(f'PRAGMA table_info({n})')} for n in TABLES}
            finally:
                source.close()
        # Enforce current schema before staging anything for restore.
        with store.connect() as db:
            allowed={table:{r['name'] for r in db.execute(f'PRAGMA table_info({table})')} for table in TABLES}
        legacy_optional={'questions':{'revision'},'attempts':{'question_snapshot','transcription_override'},'imports':{'version'},'grading_history':{'action'},'question_revisions':allowed['question_revisions']}
        if any(columns[table]-allowed[table] or allowed[table]-columns[table]-(legacy_optional.get(table,set()) if manifest['version']==1 else set()) for table in TABLES):
            invalid('备份来自更高版本，请先升级程序再恢复。')
        knowledge={r['id'] for r in rows['knowledge']}
        qids={r['id'] for r in rows['questions']}
        aids={r['id'] for r in rows['attempts']}
        if len(qids)!=len(rows['questions']) or len(aids)!=len(rows['attempts']):
            invalid()
        for q in rows['questions']:
            if q['knowledge_id'] not in knowledge or q['type'] not in ('single','multiple','boolean','calculation') or not 1<=q['minutes']<=90:
                invalid('备份题目字段无效。')
            if not isinstance(json.loads(q['options']),list):
                invalid()
        for a in rows['attempts']:
            if a['question_id'] not in qids or a['status'] not in ('pending','confirmed','voided','outdated'):
                invalid('备份作答字段无效。')
            if a['grade'] is not None and a['grade'] not in ('correct','partial','incorrect'):
                invalid()
            datetime.fromisoformat(a['created_at'])
        if any(r['attempt_id'] not in aids for r in rows['grading_history']):
            invalid()
        for row in rows['settings']:
            json.loads(row['value'])
        settings={r['key']:json.loads(r['value']) for r in rows['settings']}
        if settings.get('initialized') is not True or not isinstance(settings.get('demo_mode',False),bool):
            invalid('备份缺少学习空间标记。')
        for row in rows['plans']:
            value=json.loads(row['tasks'])
            if not isinstance(value,dict) or not isinstance(value.get('tasks'),list):
                invalid()
        for row in rows['imports']:
            if not isinstance(json.loads(row['items']),list) or not isinstance(json.loads(row['warnings']),list):
                invalid()
        for row in rows['question_revisions']:
            if row['question_id'] not in qids or not isinstance(json.loads(row['snapshot']),dict):
                invalid()
        validate_payloads(rows,knowledge,qids)
        references=[]
        for q in rows['questions']:
            references.extend(json.loads(q['attachments']))
        for a in rows['attempts']:
            references.extend(json.loads(a['photos']))
            snapshot=json.loads(a.get('question_snapshot','{}'))
            if snapshot:
                if snapshot.get('knowledge_id') not in knowledge:
                    invalid()
                references.extend(snapshot.get('attachments',[]))
        for row in rows['question_revisions']:
            references.extend(json.loads(row['snapshot']).get('attachments',[]))
        for row in rows['imports']:
            for item in json.loads(row['items']):
                references.extend(item.get('attachments',[]))
        for name in references:
            if not isinstance(name,str) or not re.fullmatch(r'[a-f0-9]{32}\.jpg',name) or 'attachments/'+name not in contents:
                invalid('备份缺少被引用的照片，请重新导出完整备份。')
        # Rehearse the data copy using our schema so invalid constraints are caught
        # in the preview, before the user chooses to replace the workspace.
        rehearsal=sqlite3.connect(':memory:')
        try:
            with store.connect() as db:
                db.backup(rehearsal)
            rehearsal.execute('PRAGMA foreign_keys=ON')
            copy_rows(rehearsal,rows)
            if rehearsal.execute('PRAGMA foreign_key_check').fetchone():invalid()
        finally:
            rehearsal.close()
        return {'rows':rows,'photos':{n.split('/')[1]:v for n,v in contents.items() if n.startswith('attachments/')},
                'summary':{'exported_at':manifest.get('exported_at','未知'),'questions':len(qids),
                           'attempts':len(aids),'photos':len(contents)-1,'legacy':manifest['version']==1}}
    except HTTPException:
        raise
    except Exception:
        invalid()


def stage(raw):
    value=validate_bytes(raw)
    # Keep only a small number of short-lived previews; uploads are never restored implicitly.
    with store.DATA_LOCK:
        for key in list(STAGED):
            if time.monotonic()-STAGED[key]['created']>1800:
                del STAGED[key]
        if len(STAGED)>=3:
            del STAGED[next(iter(STAGED))]
        token=uuid.uuid4().hex
        STAGED[token]={'created':time.monotonic(),'raw':raw,'baseline':fingerprint()}
    return {'token':token,**value['summary']}


def validate_payloads(rows,knowledge,qids):
    # Validate JSON against the same input contracts used by the app. A valid SQLite
    # file alone does not guarantee that its contents can be rendered or replayed.
    from .main import AIGradeOutput, DraftQuestionInput, QuestionInput
    from .learning import SUBJECTS

    def text(value):
        if not isinstance(value,str):
            invalid('备份含无效文字字段。')

    def integer(value,minimum=0,maximum=1_000_000):
        if type(value)!=int or not minimum<=value<=maximum:
            invalid('备份含无效数值字段。')

    def strings(value):
        if not isinstance(value,list) or any(not isinstance(v,str) for v in value):
            invalid('备份含无效列表字段。')

    def question(value,draft=False):
        if not isinstance(value,dict):invalid()
        model=DraftQuestionInput if draft else QuestionInput
        model.model_validate(value,strict=True)
        if value['knowledge_id'] not in knowledge:invalid()
        strings(value.get('options',[]));strings(value.get('attachments',[]))
        if not draft:
            text(value['id'])
            if value['id'] not in qids:invalid()

    for k in rows['knowledge']:
        for key in ('id','subject','chapter','name'):text(k[key])
        if k['subject'] not in SUBJECTS:invalid()
    for q in rows['questions']:
        for key in ('verified','is_demo'):integer(q[key],0,1)
        question({**q,'verified':bool(q['verified']),'options':json.loads(q['options']),'attachments':json.loads(q['attachments'])})
        datetime.fromisoformat(q['created_at'])
    for a in rows['attempts']:
        text(a['id']);text(a['answer']);text(a.get('transcription_override',''))
        integer(a['version']);integer(a['hinted'],0,1);integer(a['elapsed'],0,1440);integer(a['is_demo'],0,1)
        strings(json.loads(a['photos']))
        if a['status']=='confirmed' and a['grade'] is None:invalid()
        if a['confirmed_at']:datetime.fromisoformat(a['confirmed_at'])
        snapshot=json.loads(a.get('question_snapshot','{}'))
        if snapshot:
            question(snapshot)
            if snapshot['id']!=a['question_id']:invalid()
        if a['ai_result']:
            result=json.loads(a['ai_result'])
            AIGradeOutput.model_validate(result,strict=True)
            if result.get('mode') not in ('ai','objective','manual'):invalid()
            if any(not {'quote','verdict','reason'}<=set(s) for s in result.get('steps',[])):invalid()
    for row in rows['grading_history']:
        integer(row['version']);datetime.fromisoformat(row['confirmed_at'])
        if row.get('action','confirm') not in ('confirm','void','restore') or row['grade'] not in ('correct','partial','incorrect','unknown'):invalid()
    for row in rows['imports']:
        text(row['id']);text(row['name']);integer(row.get('version',0))
        if row['status'] not in ('review','confirmed'):invalid()
        strings(json.loads(row['warnings']))
        for item in json.loads(row['items']):
            question(item,draft=True)
    for row in rows['question_revisions']:
        snapshot=json.loads(row['snapshot']);question(snapshot)
        if snapshot['id']!=row['question_id'] or snapshot.get('revision',1)!=row['revision']:invalid()
    for row in rows['plans']:
        text(row['id']);datetime.fromisoformat(row['day']);datetime.fromisoformat(row['created_at'])
        plan=json.loads(row['tasks'])
        for key in ('budget','study_minutes','buffer_minutes','break_minutes','total_minutes','backlog'):integer(plan[key])
        for task in plan['tasks']:
            for key in ('id','title','knowledge','knowledge_id','subject','type','category','status'):text(task[key])
            if task['question_id'] not in qids:invalid()
            strings(task['reasons']);integer(task['minutes'],1,90)
            if type(task['priority']) not in (int,float) or not isinstance(task['factors'],dict) or any(type(v) not in (int,float) for v in task['factors'].values()):invalid()
        if row['summary']:
            summary=json.loads(row['summary']);text(summary['summary'])
            for item in summary['tasks']:text(item['id']);text(item['explanation'])
    settings={r['key']:json.loads(r['value']) for r in rows['settings']}
    integer(settings.get('budget',60),5,240)


def fingerprint():
    with store.connect() as db:
        return sha(store.dump({t:[dict(r) for r in db.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in TABLES}).encode())


def copy_rows(db,rows):
    # Column names were checked against our schema; all values are parameters.
    for table in reversed(TABLES):
        db.execute(f'DELETE FROM {table}')
    for table in TABLES:
        for row in rows[table]:
            if table=='settings' and row['key']=='ai_config':
                continue
            columns=list(row)
            db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",tuple(row[c] for c in columns))


def restore(token):
    with store.DATA_LOCK:
        staged=STAGED.get(token)
        if not staged or time.monotonic()-staged['created']>1800:
            raise HTTPException(409,'恢复预览已过期，请重新选择备份文件。')
        if staged['baseline']!=fingerprint():
            raise HTTPException(409,'预览后学习数据已改变，请重新选择备份并确认，避免覆盖刚完成的学习。')
        # Revalidate staging and create a recoverable snapshot before any changes.
        value=validate_bytes(staged['raw'])
        folder=store.DB_PATH.parent/'backups'
        folder.mkdir(exist_ok=True)
        safety_name=f'before-restore-{store.today().isoformat()}-{uuid.uuid4().hex[:8]}.zip'
        (folder/safety_name).write_bytes(export_bytes())
        old_files={}
        try:
            with store.connect() as db:
                current_ai=store.setting(db,'ai_config')
                # Parameterized data copy into our own schema. No archive SQL is executed.
                copy_rows(db,value['rows'])
                if current_ai:
                    store.set_setting(db,'ai_config',current_ai)
                for row in db.execute('SELECT * FROM questions').fetchall():
                    snapshot=store.dump(store.question_dict(row))
                    db.execute('INSERT OR IGNORE INTO question_revisions VALUES (?,?,?,?)',
                               (row['id'],row['revision'],snapshot,row['created_at']))
                    db.execute("UPDATE attempts SET question_snapshot=? WHERE question_id=? AND question_snapshot='{}'",(snapshot,row['id']))
                from . import rag
                rag.rebuild(db)
                if db.execute('PRAGMA foreign_key_check').fetchone():
                    invalid('恢复数据关联校验失败，已保留原数据。')
                for name,content in value['photos'].items():
                    path=store.FILES/name
                    if not path.exists() or path.read_bytes()!=content:
                        old_files[name]=path.read_bytes() if path.exists() else None
                        temporary=path.with_suffix('.tmp')
                        temporary.write_bytes(content)
                        temporary.replace(path)
        except Exception:
            for name,content in old_files.items():
                path=store.FILES/name
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)
            raise
        del STAGED[token]
        store.WORKSPACE_EPOCH+=1
        return {'ok':True,'safety_backup':safety_name,**value['summary']}
