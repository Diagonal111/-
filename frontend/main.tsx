import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, Brain, CalendarDays, Check,
  CheckCircle2, ChevronDown, ChevronRight, Circle, Clock3, Database, FileImage,
  FileSpreadsheet, FileText, Flame, GraduationCap, ImagePlus, Layers3,
  History, LayoutDashboard, Leaf, Lightbulb, ListChecks, LoaderCircle, Plus, RefreshCw,
  Search, Settings2, ShieldCheck, Sparkles, Target, TrendingUp, UploadCloud, X,
} from 'lucide-react'
import { Markdown, Modal, Empty } from './ui'
import { Records } from './records'
import { BackupPanel } from './backup'
import { QuestionLibrary } from './library'
import { KnowledgeFolders, ReviewFolders } from './grouped-learning'
import 'katex/dist/katex.min.css'
import { APIError, api, setToken, uploadPhoto } from './api'
import type { AttemptDetail, Grade, Grading, ImportResult, Knowledge, Page, Plan, Question, QuestionDraft, RAGExplanation, State, Task } from './types'
import './styles.css'
import './theme.css'
import './grading-workflow.css'
import './rag-explanation.css'
import './share.css'

const SUBJECTS = ['数据结构', '计算机组成原理', '操作系统', '计算机网络']
const TYPE: Record<string, string> = { calculation: '计算题', single: '单选题', multiple: '多选题', boolean: '判断题' }
const GRADES: Record<string, string> = { correct: '正确', partial: '部分正确', incorrect: '错误', unknown: '无法判定' }
const CATEGORIES: Record<string, string> = { review: '间隔复习', weak: '薄弱巩固', new: '新知探索' }
const SUBJECT_SHORT: Record<string, string> = { 数据结构: 'DS', 计算机组成原理: 'CO', 操作系统: 'OS', 计算机网络: 'CN' }

function App() {
  const [data, setData] = useState<State | null>(null)
  const [page, setPage] = useState<Page>('today')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [budget, setBudget] = useState(60)
  const [busy, setBusy] = useState('')
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null)
  const [resumeAttempt, setResumeAttempt] = useState<AttemptDetail|null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [editQuestion, setEditQuestion] = useState<Question | null>(null)
  const [startOpen, setStartOpen] = useState(false)
  const [allTasks, setAllTasks] = useState(false)

  const refresh = async (initial = false) => {
    let next = await api<State>('/bootstrap')
    setToken(next.token)
    if (initial && !next.plan && next.questions.some(q => q.verified)) {
      await api('/plans/generate', { budget: next.budget })
      next = await api<State>('/bootstrap')
    }
    setData(next)
    if (initial) setBudget(next.budget)
  }
  useEffect(() => { refresh(true).catch(e => setError(e.message)) }, [])
  useEffect(() => { if (notice) { const id = window.setTimeout(() => setNotice(''), 5500); return () => clearTimeout(id) } }, [notice])

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setError('')
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  const regenerate = () => run('plan', async () => {
    await api('/plans/generate', { budget }); await refresh(); setNotice('已根据最新学习记录重新安排，历史计划仍保留。')
  })

  if (!data) return <div className="loading-page"><div className="brand-logo"><Layers3 size={28} /></div><h2>拾知</h2><p>{error || '正在打开你的学习空间…'}</p>{error ? <button className="btn primary" onClick={() => refresh(true).catch(e => setError(e.message))}>重新连接</button> : <LoaderCircle className="spin" />}</div>
  const date = new Date(data.date + 'T12:00:00+08:00')
  const dateText = date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long', timeZone: 'Asia/Shanghai' })
  const titles: Record<Page, string> = { today: '今日学习', questions: '我的题库', knowledge: '知识地图', mistakes: '错题与复习', settings: '学习设置', records: '学习记录' }
  const startOwn = async () => { await api('/workspace/start', {}); setStartOpen(false); await refresh(); setPage('questions'); setNotice('已开启你的个人题库，可以导入第一份学习材料。') }
  return <div className={`app ${data.share_mode?'share-view':''}`}>
    <aside className="sidebar">
      <a href="#" className="brand" onClick={e => { e.preventDefault(); setPage('today') }}><div className="brand-logo"><Layers3 size={25} strokeWidth={1.7} /></div><div><strong>拾知<span>SHIZHI</span></strong><small>每一点进步，都算数</small></div></a>
      <div className="space-label"><span className="workspace-dot" />我的学习空间<ChevronDown size={13} /></div>
      <div className="nav-label">学习工作台</div>
      <nav>{([
        ['today', LayoutDashboard, '今日学习'], ['questions', BookOpen, '我的题库'],
        ['knowledge', Brain, '知识地图'], ['mistakes', ListChecks, '错题与复习'], ['records', History, '学习记录'],
      ] as const).map(([id, Icon, label]) => <button key={id} aria-label={label} className={`nav-item ${page === id ? 'active' : ''}`} onClick={() => setPage(id)}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{id === 'mistakes' && data.stats.mistakes > 0 && <small>{data.stats.mistakes}</small>}</button>)}</nav>
      <div className="sidebar-card"><div className="small-orbit"><Leaf size={21} /></div><strong>慢慢来，比较快。</strong><p>让每一次复习，<br />都发生在刚好的时候。</p><button onClick={() => setImportOpen(true)}>添加学习材料<Plus size={14} /></button></div>
      <div className="sidebar-bottom"><button aria-label="设置与数据" className={`nav-item ${page === 'settings' ? 'active' : ''}`} onClick={() => setPage('settings')}><Settings2 size={19} /><span>设置与数据</span></button><div className="local-status"><span /><div>本地学习空间<small>学习记录保存在这台电脑</small></div><ShieldCheck size={17} /></div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">学习工作台<ChevronRight size={13} /><strong>{titles[page]}</strong></div><div className="topbar-right"><span className="date"><CalendarDays size={15} />{dateText}</span><span className={`mode-pill ${data.demo_mode ? '' : 'personal'}`}>{data.share_mode ? '分享演示空间' : data.demo_mode ? '示例学习档案' : '个人学习档案'}</span><div className="avatar">知</div></div></header>
      <main className="main-content">
        {error && <div className="alert error" role="alert"><span>{error}</span><button className="icon-btn" onClick={() => setError('')} aria-label="关闭错误"><X size={16} /></button></div>}
        <div className="page-heading"><div>{!(['knowledge', 'mistakes', 'records'] as Page[]).includes(page)&&<span className="eyebrow">{page === 'today' ? 'A LITTLE PROGRESS, EVERY DAY' : 'MAKE KNOWLEDGE YOUR OWN'}</span>}<h1>{titles[page]}<span className="heading-dot">.</span></h1><p>{page === 'today' ? '不必一次学会所有，只需走好今天这一步。' : page === 'questions' ? '把散落的题目，整理成属于你的知识积累。' : page === 'knowledge' ? '看见已有的积累，也找到下一步的方向。' : page === 'mistakes' ? '错过一次的题目，值得一次更有准备的重逢。' : page === 'records' ? '回看每次思考，也为判断保留修正的余地。' : '让工具适合你的节奏。'}</p></div>{!data.share_mode&&<button className="btn primary" onClick={() => setImportOpen(true)}><Plus size={17} />导入题目</button>}</div>
        {data.share_mode&&<div className="share-banner"><ShieldCheck size={19}/><div><strong>欢迎体验拾知 · 演示空间</strong>这里使用示例题与模拟历史，访客共同体验这份演示数据。可以答题、自评和查看学习变化；AI 调用、材料上传及管理功能已关闭。</div></div>}

        {page === 'today' && <>
          <section className="hero"><div className="hero-content"><span className="hero-label"><span />为你的 408 学习定制</span><h2>今天的努力，<br />有迹可循。</h2><p>从掌握情况出发，照顾遗忘的节奏。<br />让每一道题，都成为更扎实的一步。</p><button className="hero-button" onClick={() => { const t = data.plan?.tasks.find(t => t.status !== 'done'); if (t) setActiveQuestion(t.question_id); else document.getElementById('today-plan')?.scrollIntoView({ behavior: 'smooth' }) }}>{data.plan?.tasks.some(t => t.status !== 'done') ? '开始今天的学习' : '查看今日安排'}<ArrowUpRight size={18} /></button></div>
            <div className="hero-visual" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" /><div className="orbit orbit-four" /><div className="floating-leaf"><Leaf size={23} /></div><div className="time-disc"><span>为专注留一点时间</span><strong>{data.plan?.total_minutes || budget}<small>min</small></strong><div><span />今日学习节奏</div></div><div className="hero-chip"><CheckCircle2 size={15} />有计划，也有余地</div><span className="tiny-star">✳</span></div>
          </section>

          <section className="stats-grid">
            {[
              { title: '今日待复习', value: data.stats.due, unit: '题', icon: RefreshCw, class: 'sage', detail: '照顾记忆的保鲜期', trend: '到期优先' },
              { title: '需要再巩固', value: data.stats.mistakes, unit: '题', icon: Target, class: 'peach', detail: '从每一次错误中生长', trend: '错题追踪' },
              { title: '已探索知识点', value: data.stats.practiced, unit: `/ ${data.stats.knowledge_count}`, icon: Brain, class: 'lavender', detail: '一次练习，一点积累', trend: '持续更新' },
              { title: '今天已完成', value: data.stats.done_today, unit: '次', icon: CheckCircle2, class: 'sand', detail: '每一点进步，都算数', trend: '已确认' },
            ].map(s => <article className="stat-card" key={s.title}><div className="stat-top"><span>{s.title}</span><div className={`stat-icon ${s.class}`}><s.icon size={18} /></div></div><div className="stat-number">{s.value}<small>{s.unit}</small></div><div className="stat-foot"><span>{s.detail}</span><small>{s.trend}</small></div></article>)}
          </section>

          <div className="dashboard-grid"><div className="dashboard-main">
            <section className="panel plan-panel" id="today-plan"><div className="section-head"><div><h2><span className="section-icon"><ListChecks size={18} /></span>今天，学这些<span className="count-pill">{data.plan?.tasks.length || 0} 项</span></h2><p>根据掌握度、错题与复习间隔安排</p></div><div className="plan-controls"><label className="time-select"><Clock3 size={14} /><select aria-label="今天可用时间" value={budget} onChange={e => setBudget(Number(e.target.value))}>{[10,20,30,45,60,90,120].map(n => <option value={n} key={n}>{n} 分钟</option>)}</select><ChevronDown size={12} /></label><button className="icon-btn bordered" title="重新安排计划" aria-label="重新安排计划" disabled={!!busy} onClick={regenerate}><RefreshCw size={16} className={busy === 'plan' ? 'spin' : ''} /></button></div></div>
              {data.plan?.stale&&<div className="info-strip">学习记录或题目已更新，可点击右上角重新安排剩余任务。</div>}
              {data.plan?.tasks.length ? <>
                <div className="plan-summary"><div><span className="legend-dot review" />复习 {data.plan.tasks.filter(t => t.category === 'review').length}<span className="legend-dot weak" />巩固 {data.plan.tasks.filter(t => t.category === 'weak').length}<span className="legend-dot new" />新知 {data.plan.tasks.filter(t => t.category === 'new').length}</div><span>预计 {data.plan.total_minutes} / {data.plan.budget} 分钟</span></div>
                <div className="task-list">{data.plan.tasks.slice(0, allTasks ? undefined : 4).map((task, i) => <TaskCard key={task.id} task={task} index={i} onOpen={() => setActiveQuestion(task.question_id)} />)}</div>
                {data.plan.tasks.length>4&&<button className="show-all-tasks" onClick={()=>setAllTasks(!allTasks)}>{allTasks?'收起任务':`展开其余 ${data.plan.tasks.length-4} 项学习任务`}<ChevronDown size={13} className={allTasks?'rotate':''}/></button>}
                <div className="plan-footer"><span><Leaf size={14} />含 {data.plan.buffer_minutes} 分钟操作缓冲{data.plan.break_minutes > 0 && ` · ${data.plan.break_minutes} 分钟休息`}</span><span>{data.plan.tasks.filter(t => t.status === 'done').length}/{data.plan.tasks.length} 已完成</span></div>
                {data.plan.backlog > 0 && <div className="backlog">还有 {data.plan.backlog} 道到期题未排入。今天先按自己的节奏完成即可。</div>}
              </> : <Empty title="从第一道题开始" detail="导入一些题目，或体验示例题库，系统就能为你安排学习。" action={<button className="btn soft" onClick={() => setImportOpen(true)}><UploadCloud size={16} />导入学习材料</button>} />}
            </section>

            <section className="insight-card"><div className="insight-icon"><Sparkles size={20} /></div><div><div className="insight-title">为什么这样安排？<span>{data.plan?.summary ? 'AI 解读' : '规则解读'}</span></div><p>{data.plan?.summary?.summary || (data.stats.due > 0 ? `先照顾 ${data.stats.due} 道到期题的记忆，再留一点空间巩固薄弱点、探索新知识。计划只使用你已核实的题目与学习记录。` : '从少量基础题开始，建立真实的学习记录。随着独立作答增多，推荐会逐渐贴合你的掌握情况。')}</p>{data.plan?.tasks.length ? <button className="text-btn" disabled={!!busy} onClick={() => data.ai.configured ? run('explain', async () => { await api(`/plans/${data.plan!.id}/explain`, {}); await refresh(); setNotice('已生成 AI 计划解读。') }) : setPage('settings')}>{busy === 'explain' ? '正在生成…' : data.ai.configured ? '用 AI 解读这份计划' : '连接 AI，获得个性化解读'}<ArrowRight size={14} /></button> : null}</div></section>
          </div><aside className="dashboard-side">
            <section className="panel knowledge-preview"><div className="section-head compact"><h2>知识生长中<span className="sprout">↗</span></h2><button className="icon-btn" title="查看知识地图" onClick={() => setPage('knowledge')}><ArrowUpRight size={17} /></button></div><p className="subtle">记录掌握，也尊重未知</p>{SUBJECTS.map((s, i) => {
              const points = data.knowledge.filter(k => k.subject === s && k.evidence > 0)
              const value = points.length ? Math.round(points.reduce((v, k) => v + k.mastery, 0) / points.length) : 0
              return <div className="subject-progress" key={s}><div><span><i className={`subject-symbol s${i}`}>{SUBJECT_SHORT[s]}</i>{s}</span><strong>{points.length ? `${value}%` : '待评估'}</strong></div><div className="progress-track"><span style={{ width: `${value}%` }} className={`progress-${i}`} /></div></div>
            })}<div className="evidence-note"><Circle size={10} />指标来自已练知识点，非考试正确率</div></section>
            <section className="panel week-panel"><div className="section-head compact"><h2>最近 7 天</h2><TrendingUp size={17} className="muted" /></div><div className="week-total"><strong>{data.stats.week.reduce((v,d)=>v+d.count,0)}</strong><span>次已确认作答</span></div><div className="week-chart">{data.stats.week.map((d,i) => <div className={`day-column ${i===6?'today':''}`} key={d.date}><div className="day-bar-wrap"><span className="bar-value">{d.count || ''}</span><div className="day-bar" style={{height:Math.max(5, d.count / Math.max(1,...data.stats.week.map(d=>d.count)) * 65)}} /></div><small>{i===6?'今天':['日','一','二','三','四','五','六'][new Date(d.date+'T12:00:00').getDay()]}</small></div>)}</div><div className="week-note"><Flame size={14} />积累的每一步，都有回声</div></section>
            {data.demo_mode && <div className="demo-note"><div><GraduationCap size={19} /><strong>先体验，再开始</strong></div><p>当前展示原创示例题与模拟历史。你可以体验作答，或开启自己的题库。</p><button className="text-btn" onClick={() => setStartOpen(true)}>开始我的学习<ArrowRight size={14} /></button></div>}
          </aside></div>
        </>}

        {page === 'questions' && <QuestionLibrary questions={data.questions} date={data.date} onOpen={setActiveQuestion} onImport={()=>setImportOpen(true)} onManual={()=>setManualOpen(true)} />}

        {page === 'mistakes' && <ReviewFolders questions={data.questions} date={data.date} onOpen={setActiveQuestion} onLibrary={()=>setPage('questions')} />}

        {page === 'knowledge' && <KnowledgeFolders knowledge={data.knowledge} />}

        {page==='records'&&<Records refreshKey={data} onChanged={refresh} onResume={a=>{setResumeAttempt(a);setActiveQuestion(a.question_id)}}/>}

        {page==='settings'&&!data.share_mode&&<Settings data={data} onSaved={async()=>{await refresh();setNotice('设置已保存。API Key 仅在本次后台运行期间保留。')}} onStart={()=>setStartOpen(true)} onRestored={async()=>{await refresh(true);setNotice('备份已恢复，恢复前的数据也已自动备份。')}}/>}

        <footer className="page-footer"><span><Leaf size={13}/>拾知 · 把知识一点点变成自己的</span><span><span className="online-dot"/>本地运行<span className="footer-separator">/</span>{data.share_mode?'演示自评 · AI 已关闭':data.ai.configured?'AI 已连接配置':'AI 尚未配置'}</span></footer>
      </main>
    </div>
    {notice&&<div className="toast" role="status"><CheckCircle2 size={18}/>{notice}<button className="icon-btn" onClick={()=>setNotice('')} aria-label="关闭通知"><X size={15}/></button></div>}
    {activeQuestion&&<StudyModal id={activeQuestion} resume={resumeAttempt} data={data} onClose={()=>{setActiveQuestion(null);setResumeAttempt(null)}} onChanged={refresh} onSettings={()=>{setActiveQuestion(null);setResumeAttempt(null);setPage('settings')}} onEdit={q=>{setActiveQuestion(null);setResumeAttempt(null);setEditQuestion(q);setManualOpen(true)}}/>}
    {!data.share_mode&&importOpen&&<ImportModal data={data} onClose={()=>setImportOpen(false)} onDone={async(count)=>{setImportOpen(false);await refresh(true);setPage('questions');setNotice(`已入库 ${count} 道题目。示例历史不会混入你的个人记录。`)}}/>}
    {!data.share_mode&&manualOpen&&<ManualModal data={data} initial={editQuestion} onClose={()=>{setManualOpen(false);setEditQuestion(null)}} onDone={async()=>{setManualOpen(false);setEditQuestion(null);await refresh(true);setNotice('题目已保存。')}}/>}
    {!data.share_mode&&startOpen&&<Modal title="开始自己的学习" subtitle="清空示例题目与示例作答，保留 AI 配置和知识点分类。" onClose={()=>setStartOpen(false)}><div className="modal-body"><p>此操作也会移除你在示例题目上的体验记录。之后可以导入自己的 Excel、Word 或题目照片。</p></div><div className="modal-actions"><button className="btn secondary" onClick={()=>setStartOpen(false)}>继续体验</button><button className="btn primary" onClick={()=>run('start',startOwn)} disabled={!!busy}>开启个人题库<ArrowRight size={16}/></button></div></Modal>}
  </div>
}

function TaskCard({task,index,onOpen}:{task:Task;index:number;onOpen:()=>void}) {
  const [expanded,setExpanded]=useState(false)
  return <article className={`task-card ${task.status==='done'?'completed':''}`}><div className="task-number">{task.status==='done'?<Check size={17}/>:String(index+1).padStart(2,'0')}</div><div className="task-content"><div className="task-meta"><span className={`tag ${task.category}`}>{CATEGORIES[task.category]}</span><span>{task.subject}</span><span className="task-type">{TYPE[task.type]}</span></div><h3><button onClick={onOpen}>{task.title}</button></h3><div className="task-reason"><span className="reason-dot"/>{task.reasons[0]}{task.reasons.length>1&&<span> · {task.reasons[1]}</span>}</div><button className="reason-toggle" onClick={()=>setExpanded(!expanded)}><Lightbulb size={12}/>{expanded?'收起推荐依据':'为什么推荐'}<ChevronDown size={11} className={expanded?'rotate':''}/></button>{expanded&&<div className="reason-detail"><p>知识点：{task.knowledge} · 优先级：{task.priority}</p><div>{Object.entries(task.factors).map(([key,value])=><span key={key}>{key} {Math.round(value*100)}%</span>)}</div><p>这些数值用于排序，不代表考试答对概率。</p></div>}</div><div className="task-end"><span><Clock3 size={13}/>{task.minutes} 分钟</span><button className={`task-open ${task.status==='done'?'done':''}`} aria-label={`学习：${task.title}`} onClick={onOpen}>{task.status==='done'?<CheckCircle2 size={18}/>:<ArrowUpRight size={18}/>}</button></div></article>
}

function StudyModal({id,resume,data,onClose,onChanged,onSettings,onEdit}:{id:string;resume:AttemptDetail|null;data:State;onClose:()=>void;onChanged:()=>Promise<void>;onSettings:()=>void;onEdit:(q:Question)=>void}) {
  const [q,setQ]=useState<Question|null>(null)
  const [answer,setAnswer]=useState('')
  const [choices,setChoices]=useState<string[]>([])
  const [photos,setPhotos]=useState<string[]>([])
  const [hinted,setHinted]=useState(false)
  const [reveal,setReveal]=useState(false)
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const [attempt,setAttempt]=useState<{id:string;version:number}|null>(null)
  const [result,setResult]=useState<Grading|null>(null)
  const [rag,setRag]=useState<RAGExplanation|null>(null)
  const [grade,setGrade]=useState<Grade>('unknown')
  const [correctedText,setCorrectedText]=useState('')
  const [confirmed,setConfirmed]=useState<{knowledge:Knowledge;review:ReviewPreview}|null>(null)
  const inputRef=useRef<HTMLInputElement>(null)
  const started=useRef(Date.now())
  useEffect(()=>{
    setRag(null)
    if(resume){setQ(resume.question);setAnswer(resume.answer);setChoices(resume.answer.split(','));setPhotos(resume.photos);setHinted(resume.hinted);setAttempt({id:resume.id,version:resume.version});setResult(resume.ai_result);setGrade(resume.ai_result?.grade||'unknown');setCorrectedText(resume.transcription_override||resume.ai_result?.transcription||'')}
    else api<Question>(`/questions/${id}`).then(setQ).catch(e=>setError(e.message))
  },[id,resume])
  const perform=async(name:string,fn:()=>Promise<void>)=>{setBusy(name);setError('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy('')}}
  const addPhotos=(files:FileList|null)=>{if(!files)return;const selected=Array.from(files);if(photos.length+selected.length>8){setError('一次作答最多上传 8 张照片。');return}perform('upload',async()=>{const names:string[]=[];for(const file of selected)names.push(await uploadPhoto(file));setPhotos(v=>[...v,...names])})}
  const submit=()=>perform('grade',async()=>{
    if(!q)return
    const current=await api('/attempts',{question_id:id,revision:q.revision,answer:q.type==='calculation'?answer:choices.join(','),photos,hinted,elapsed:Math.max(1,Math.round((Date.now()-started.current)/60000))})
    setAttempt({id:current.id,version:0})
    let grading:Grading=current.result
    if(!grading&&data.ai.configured)grading=await api(`/attempts/${current.id}/grade`,{})
    if(!grading)grading={mode:'manual',transcription:answer,grade:'unknown',summary:'尚未配置 AI。请对照参考解答，自行确认本次表现。',steps:[],uncertainties:[]}
    setResult(grading);setGrade(grading.grade);setCorrectedText(grading.transcription||'')
  })
  const confirm=()=>perform('confirm',async()=>{
    if(!attempt||grade==='unknown')return
    const next=await api(`/attempts/${attempt.id}/confirm`,{grade,version:attempt.version})
    setConfirmed(next);await onChanged()
  })
  return <Modal wide title={q?.title||'正在打开题目…'} subtitle={q?`${q.subject} / ${q.knowledge} · ${TYPE[q.type]} · 预计 ${q.minutes} 分钟`:''} onClose={onClose}><div className="study-layout"><div className="study-question">{q&&<><div className="question-label"><span className="tag neutral">{TYPE[q.type]}</span><span>{q.source} · 第 {q.revision} 版</span>{!data.share_mode&&<button className="text-btn" onClick={()=>onEdit(q)}>编辑题目</button>}</div><Markdown>{q.body}</Markdown>{q.attachments.length>0&&<div className="question-photos">{q.attachments.map(p=><a href={'/attachments/'+p} target="_blank" rel="noreferrer" key={p}><img src={'/attachments/'+p} alt="题目原图，点击放大"/></a>)}</div>}
      {!q.verified&&<div className="inline-note"><Lightbulb size={16}/><span>参考答案尚未核实，暂不用于学习状态计算。<button onClick={()=>onEdit(q)}>完善题目与答案</button></span></div>}
      {q.type!=='calculation'&&<div className="answer-options">{(q.type==='boolean'?['正确','错误']:q.options).map((option,i)=>{const key=q.type==='boolean'?option:String.fromCharCode(65+i);return <button disabled={!!attempt} key={key} className={`answer-option ${choices.includes(key)?'chosen':''}`} onClick={()=>setChoices(v=>q.type==='multiple'?v.includes(key)?v.filter(a=>a!==key):[...v,key].sort():[key])}><span>{q.type==='boolean'?(i===0?'✓':'×'):key}</span><Markdown>{option}</Markdown>{choices.includes(key)&&<Check size={16}/>}</button>})}</div>}
      <div className="reference-block"><button className="text-btn" onClick={()=>{setReveal(!reveal);if(!attempt&&!reveal)setHinted(true)}}><BookOpen size={14}/>{reveal?'收起参考解答':'查看参考解答'}<ChevronDown size={14}/></button>{reveal&&<div className="reference-answer"><strong>参考答案{!q.verified&&'（尚未核实）'}</strong><Markdown>{q.answer||'原材料未提供答案。'}</Markdown><Markdown>{q.explanation||''}</Markdown></div>}{data.ai.configured&&<button className="text-btn rag-trigger" disabled={!!busy} onClick={()=>{if(!attempt)setHinted(true);perform('rag',async()=>setRag(await api<RAGExplanation>(`/questions/${q.id}/explain`,{})))}}><Sparkles size={14}/>{busy==='rag'?'正在检索相关题目…':rag?'重新生成错题讲解':'用题库讲解这道题'}</button>}{rag&&<div className="rag-panel"><div className="rag-answer"><strong>基于你的题库</strong><p>{rag.answer}</p></div>{rag.citations.length>0&&<div className="rag-sources"><span>引用依据 · {rag.retrieved_count} 道相关题</span>{rag.citations.map(source=><div key={source.question_id}><b>{source.title}</b><small>{source.knowledge}{source.reason?` · ${source.reason}`:''}</small></div>)}</div>}{rag.recommendations.length>0&&<div className="rag-recommendations"><span>建议再练</span>{rag.recommendations.map(item=><span className="tag neutral" key={item.question_id}>{item.title}</span>)}</div>}{rag.uncertainties.length>0&&<div className="rag-uncertainties">{rag.uncertainties.map((item,i)=><p key={i}>{item}</p>)}</div>}</div>}</div>
      {q.history&&q.history.length>0&&<div className="history-block"><span className="eyebrow">最近的练习足迹</span>{q.history.slice(0,4).map(h=><div key={h.id}><span>{h.created_at.slice(0,10)}</span><span className={`grade-text ${h.grade}`}>{h.status==='confirmed'?GRADES[h.grade]:h.status==='voided'?'已撤销':h.status==='outdated'?'题目已更新':'待确认'}{h.hinted?' · 使用提示':''}</span></div>)}</div>}
    </>}</div><div className="study-answer">
      {error&&<div className="alert error" role="alert">{error}</div>}
      {!result&&!confirmed&&<><h3><FileText size={17}/>我的作答</h3>{q?.type==='calculation'?<><textarea className="answer-textarea" value={answer} disabled={!!attempt} onChange={e=>setAnswer(e.target.value)} placeholder="在这里写下解题过程，或拍照上传纸面答案…" aria-label="解题过程"/><input ref={inputRef} hidden type="file" accept="image/png,image/jpeg" multiple onChange={e=>{addPhotos(e.target.files);e.target.value=''}}/><button className="photo-upload" disabled={!!busy||!!attempt} onClick={()=>inputRef.current?.click()}><ImagePlus size={24}/><strong>{busy==='upload'?'正在保存照片…':'上传作答照片'}</strong><span>支持多张 JPG / PNG，每张不超过 12 MB</span></button><div className="photo-grid">{photos.map((p,i)=><div key={p}><img src={'/attachments/'+p} alt={`作答照片 ${i+1}`}/>{!attempt&&<button className="photo-remove" aria-label={`移除照片 ${i+1}`} onClick={()=>setPhotos(v=>v.filter(n=>n!==p))}><X size={12}/></button>}</div>)}</div></>:<p className="answer-prompt">{choices.length?`已选择：${choices.join('、')}`:'先在左侧选择你的答案，再提交判分。'}</p>}
        <label className="checkbox-line"><input type="checkbox" checked={hinted} disabled={!!attempt} onChange={e=>setHinted(e.target.checked)}/>我使用了提示、看过答案，或这次是猜对的</label>
        {q?.type==='calculation'&&!data.ai.configured&&<div className="inline-note"><Sparkles size={15}/><span>{data.share_mode?'演示空间支持输入过程、查看参考解答后自评。AI 调用与照片上传已关闭。':<>连接 AI 后支持照片转写与分步批改。当前可查看答案后自评。<button onClick={onSettings}>去配置</button></>}</span></div>}
        {attempt&&!result?<><div className="inline-note">作答已保存，批改尚未完成。可重试 AI，或转为自评。</div><div className="button-row"><button className="btn primary" disabled={!!busy} onClick={()=>perform('grade',async()=>{const r=await api<Grading>(`/attempts/${attempt.id}/grade`,{});setResult(r);setGrade(r.grade);setCorrectedText(r.transcription||'')})}>重试批改</button><button className="btn secondary" onClick={()=>{setResult({mode:'manual',transcription:answer,grade:'unknown',summary:'请对照参考解答自行评估。'});setReveal(true)}}>转为自评</button></div></>:<button className="btn primary full" disabled={!!busy||(!answer.trim()&&!photos.length&&!choices.length)} onClick={submit}>{busy==='grade'?<><LoaderCircle size={16} className="spin"/>正在处理作答…</>:<>{q?.type==='calculation'?(data.ai.configured?'提交 AI 批改':'提交并自评'):'提交答案'}<ArrowRight size={16}/></>}</button>}
      </>}
      {result?.mode==='ai'&&!confirmed&&<details className="transcription"><summary>识别文字有误？修正后重新批改</summary><textarea aria-label="修正作答转写" className="answer-textarea" value={correctedText} onChange={e=>setCorrectedText(e.target.value)}/><button className="btn secondary full" disabled={!!busy||!correctedText.trim()} onClick={()=>perform('grade',async()=>{if(!attempt)return;const next=await api(`/attempts/${attempt.id}/transcription`,{text:correctedText,version:attempt.version},'PATCH');setAttempt({...attempt,version:next.version});setResult(null);const r=await api<Grading>(`/attempts/${attempt.id}/grade`,{});setResult(r);setGrade(r.grade);setCorrectedText(r.transcription||correctedText)})}>按修正内容重新批改</button></details>}
      {result&&!confirmed&&<div className="grading"><div className="grading-heading"><Sparkles size={18}/><h3>{result.mode==='ai'?'AI 批改建议':result.mode==='objective'?'客观题判分':'作答自评'}</h3><span className="tag neutral">待确认</span></div>{result.workflow&&result.workflow.length>0&&<ol className="workflow-steps">{result.workflow.map((step,i)=><li key={i}>{step.step}</li>)}</ol>}<p className="grading-summary">{result.summary}</p>{result.transcription&&<details className="transcription"><summary>查看识别 / 提交内容</summary><Markdown>{result.transcription}</Markdown></details>}{result.steps?.map((s,i)=><div className="step-review" key={i}><div><span className="step-index">{i+1}</span><strong>{s.verdict}</strong></div><blockquote>{s.quote}</blockquote><p>{s.reason}</p></div>)}{result.uncertainties?.length? <div className="alert warning">{result.uncertainties.map((s,i)=><p key={i}>{s}</p>)}</div>:null}<div className="reference-answer"><strong>参考答案</strong><Markdown>{q?.answer||'未提供'}</Markdown><Markdown>{q?.explanation||''}</Markdown></div><h4>确认这次的表现</h4><p className="subtle">你可以修正 AI 的判断，只有确认后才更新学习记录。</p><div className="grade-choices">{(['correct','partial','incorrect'] as Grade[]).map(g=><button key={g} className={`${g} ${grade===g?'selected':''}`} onClick={()=>setGrade(g)}>{grade===g&&<Check size={14}/>} {GRADES[g]}</button>)}</div>{!q?.verified&&<div className="alert warning">参考答案尚未核实，本次可保留查看，暂不能更新掌握度。</div>}<button className="btn primary full" onClick={confirm} disabled={!!busy||grade==='unknown'||!q?.verified}>{busy==='confirm'?<LoaderCircle size={16} className="spin"/>:<CheckCircle2 size={16}/>}确认并更新学习记录</button></div>}
      {confirmed&&<div className="completion"><div className="success-mark"><Check size={32}/></div><span className="eyebrow">ONE STEP FORWARD</span><h2>这一点进步，记下了。</h2><p>本次表现：{GRADES[grade]}</p><div className="result-stat"><span>{confirmed.knowledge.name}</span><strong>{confirmed.knowledge.status}<small>表现指标 {confirmed.knowledge.mastery}% · 证据 {confirmed.knowledge.evidence}</small></strong></div><div className="result-stat"><span>下次独立复习</span><strong>{confirmed.review?.due_date||'待安排'}</strong></div><p className="subtle">当天订正不会代替跨日独立复习。</p><button className="btn primary full" onClick={onClose}>回到学习空间<ArrowRight size={16}/></button></div>}
    </div></div></Modal>
}
type ReviewPreview={due_date:string}

function DraftEditor({draft,knowledge,onChange}:{draft:QuestionDraft;knowledge:Knowledge[];onChange:(q:QuestionDraft)=>void}) {
  const patch=(value:Partial<QuestionDraft>)=>onChange({...draft,...value})
  return <div className="draft-editor"><label>题目标题<input value={draft.title} onChange={e=>patch({title:e.target.value})} placeholder="给这道题一个简短标题"/></label><div className="form-row"><label>题型<select value={draft.type} onChange={e=>patch({type:e.target.value,options:e.target.value==='boolean'?['正确','错误']:draft.options,verified:false})}>{Object.entries(TYPE).map(([key,v])=><option key={key} value={key}>{v}</option>)}</select></label><label>知识点<select value={draft.knowledge_id} onChange={e=>patch({knowledge_id:e.target.value})}>{SUBJECTS.map(s=><optgroup label={s} key={s}>{knowledge.filter(k=>k.subject===s).map(k=><option value={k.id} key={k.id}>{k.name}</option>)}</optgroup>)}</select></label><label className="minutes-field">预计分钟<input type="number" min="1" max="90" value={draft.minutes} onChange={e=>patch({minutes:Number(e.target.value)})}/></label></div><label>题干<textarea rows={5} value={draft.body} onChange={e=>patch({body:e.target.value,verified:false})} placeholder="输入完整题干，支持 Markdown 和 $LaTeX$ 公式"/></label>{(draft.type==='single'||draft.type==='multiple')&&<label>选项（每行一项，不必填写 A/B 前缀）<textarea rows={4} value={draft.options.join('\n')} onChange={e=>patch({options:e.target.value.split('\n'),verified:false})}/></label>}{draft.attachments?.length>0&&<div className="draft-images">{draft.attachments.map(p=><a href={'/attachments/'+p} target="_blank" rel="noreferrer" key={p}><img src={'/attachments/'+p} alt="材料原图，点击放大"/></a>)}</div>}<label>参考答案 {draft.type==='single'?'（例如 B）':draft.type==='multiple'?'（例如 A,B）':draft.type==='boolean'?'（正确 / 错误）':''}<textarea rows={2} value={draft.answer} onChange={e=>patch({answer:e.target.value,verified:false})}/></label><label>参考解析<textarea rows={3} value={draft.explanation} onChange={e=>patch({explanation:e.target.value})}/></label><label className="checkbox-line verification"><input type="checkbox" checked={draft.verified} disabled={!draft.answer.trim()} onChange={e=>patch({verified:e.target.checked})}/><span>我已校对题干、选项及参考答案，允许用于判分和学习计划</span></label>{draft.warnings?.map((w,i)=><div className="inline-note" key={i}><Lightbulb size={14}/>{w}</div>)}</div>
}

const blankDraft=():QuestionDraft=>({title:'',body:'',type:'calculation',options:[],answer:'',explanation:'',knowledge_id:'cache',minutes:12,verified:false,attachments:[],source:'手动录入'})

function ManualModal({data,initial,onClose,onDone}:{data:State;initial:Question|null;onClose:()=>void;onDone:()=>Promise<void>}) {
  const [draft,setDraft]=useState<QuestionDraft>(()=>initial?{...initial}:blankDraft())
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  return <Modal title={initial?'完善这道题':'收下一道好题'} subtitle={initial?'保存为新版本。旧作答保留原题与原答案；未完成作答需重新提交。':'保存到个人题库。首次录题会自动结束示例模式。'} onClose={onClose}><div className="modal-body">{error&&<div className="alert error">{error}</div>}<DraftEditor draft={draft} knowledge={data.knowledge} onChange={setDraft}/></div><div className="modal-actions"><button className="btn secondary" onClick={onClose}>取消</button><button className="btn primary" disabled={busy||!draft.title.trim()||!draft.body.trim()} onClick={async()=>{setBusy(true);setError('');try{await api(initial?`/questions/${initial.id}`:'/questions',draft,initial?'PATCH':'POST');await onDone()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>{busy?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>}保存题目</button></div></Modal>
}

function ImportModal({data,onClose,onDone}:{data:State;onClose:()=>void;onDone:(count:number)=>Promise<void>}) {
  const [result,setResult]=useState<ImportResult|null>(null)
  const [pending,setPending]=useState<ImportResult[]>([])
  const [index,setIndex]=useState(0)
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const fileRef=useRef<HTMLInputElement>(null)
  const current=useRef<ImportResult|null>(null), version=useRef(0), saved=useRef(''), queue=useRef<Promise<void>>(Promise.resolve()), failed=useRef(false)
  const [saveState,setSaveState]=useState('')
  const [conflict,setConflict]=useState(false), [discard,setDiscard]=useState(false)
  current.current=result
  const begin=(value:ImportResult)=>{version.current=value.version; saved.current=JSON.stringify(value.items); failed.current=false;setConflict(false);setDiscard(false);setError('');setSaveState('已保存');setResult(value);setIndex(0)}
  const persist=()=>{
    const task=queue.current.then(async()=>{
      const value=current.current
      if(!value)return
      const contents=JSON.stringify(value.items)
      if(saved.current===contents)return
      setSaveState('正在保存…')
      try{
        const response=await api<{version:number}>(`/imports/${value.id}`,{items:value.items,version:version.current},'PATCH')
        version.current=response.version;saved.current=contents;failed.current=false;setSaveState(JSON.stringify(current.current?.items)===contents?'已保存':'有未保存修改')
      }catch(e){failed.current=true;setConflict(e instanceof APIError&&e.status===409);setSaveState('保存失败');setError((e as Error).message);throw e}
    })
    queue.current=task.catch(()=>{})
    return task
  }
  useEffect(()=>{
    const protect=(e:BeforeUnloadEvent)=>{if(current.current&&JSON.stringify(current.current.items)!==saved.current){e.preventDefault();e.returnValue=''}}
    window.addEventListener('beforeunload',protect)
    return()=>window.removeEventListener('beforeunload',protect)
  },[])
  const reloadSaved=async()=>{setBusy('reload');try{const drafts=await api<ImportResult[]>('/imports');const next=drafts.find(v=>v.id===result?.id);if(next)begin(next);else{setResult(null);setPending(drafts);setError('此批题目已入库，请在题库查看。');setConflict(false)}}catch(e){setError((e as Error).message)}finally{setBusy('')}}
  const serialized=result?JSON.stringify(result.items):''
  useEffect(()=>{
    if(!result||failed.current||serialized===saved.current)return
    setSaveState('有未保存修改')
    const timer=setTimeout(()=>{persist().catch(()=>{})},700)
    return()=>clearTimeout(timer)
  },[serialized,result?.id])
  useEffect(()=>{api<ImportResult[]>('/imports').then(setPending).catch(()=>{})},[])
  const processFile=async(file:File)=>{setBusy('recognize');setError('');try{const form=new FormData();form.append('file',file);begin(await api<ImportResult>('/imports',form))}catch(e){setError((e as Error).message)}finally{setBusy('')}}
  const save=async()=>{if(!result)return;setBusy('save');setError('');try{await persist();const value=current.current!;const response=await api(`/imports/${value.id}/confirm`,{items:value.items,version:version.current});await onDone(response.count)}catch(e){setError((e as Error).message)}finally{setBusy('')}}
  const leave=async(back=false)=>{if(busy)return;setBusy('draft');setError('');try{await persist();if(back){setResult(null);setSaveState('');setPending(await api<ImportResult[]>('/imports'))}else onClose()}catch(e){setError((e as Error).message)}finally{setBusy('')}}
  const change=(draft:QuestionDraft)=>{if(result)setResult({...result,items:result.items.map((q,i)=>i===index?draft:q)})}
  return <Modal wide={!!result} title={result?'把识别结果，校对成自己的题库':'让好题，有处安放'} subtitle={result?`${result.name} · ${result.items.length} 道待校对题目`:'上传 Excel、Word 或题目照片，整理后再确认入库。'} onClose={()=>{void leave()}}><div className="modal-body">{error&&<div className="alert error">{error}</div>}{conflict&&<div className="alert warning"><p>其他页面保存了更新的草稿。可以保留当前内容继续查看，或重新载入已保存的版本。</p>{discard?<><p>重新载入会放弃本页未保存的修改。</p><button className="btn secondary" disabled={!!busy} onClick={reloadSaved}>确认放弃修改并重新载入</button></>:<button className="btn secondary" onClick={()=>setDiscard(true)}>重新载入已保存版本</button>}</div>}{!result?<><input type="file" hidden ref={fileRef} accept=".xlsx,.docx,.jpg,.jpeg,.png" onChange={e=>{if(e.target.files?.[0])processFile(e.target.files[0]);e.target.value=''}}/><button className={`import-dropzone ${busy?'processing':''}`} disabled={!!busy} onClick={()=>fileRef.current?.click()} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy&&e.dataTransfer.files[0])processFile(e.dataTransfer.files[0])}}>{busy?<LoaderCircle size={40} className="spin"/>:<UploadCloud size={40} strokeWidth={1.3}/>}<h3>{busy?'正在读取与整理材料…':'点击选择，或把文件拖到这里'}</h3><p>{busy?'复杂图片可能需要一两分钟，请保持页面打开。':'支持 .xlsx / .docx / JPG / PNG，单文件不超过 12 MB'}</p></button><div className="import-types"><span><FileSpreadsheet size={18}/>Excel 题库</span><span><FileText size={18}/>Word 资料</span><span><FileImage size={18}/>题目照片</span></div><div className="inline-note"><Sparkles size={17}/><span>{data.ai.configured?'非标准文档和照片将发送到你配置的模型识别，结果需要校对。':'尚未配置 AI。标准 Excel 模板可直接导入；Word 和照片先保存为待整理草稿。'}</span></div><a className="text-btn template-link" href="/api/template" download><ArrowDownToLine size={15}/>下载 Excel 示例模板</a>{pending.length>0&&<div className="pending-imports"><h4>继续上次的校对</h4>{pending.map(p=><button key={p.id} onClick={()=>{begin(p)}}><FileText size={15}/>{p.name}<span>{p.items.length} 题</span><ArrowRight size={15}/></button>)}</div>}</>:<div className="import-review"><aside className="import-item-list"><span className="eyebrow">待整理题目</span>{result.items.map((q,i)=><button className={index===i?'selected':''} key={i} onClick={()=>setIndex(i)}><span>{String(i+1).padStart(2,'0')}</span><strong>{q.title||'未命名题目'}</strong>{q.verified&&<CheckCircle2 size={14}/>}</button>)}<button className="add-draft" onClick={()=>{setResult({...result,items:[...result.items,blankDraft()]});setIndex(result.items.length)}} disabled={result.items.length>=30}><Plus size={14}/>添加拆分题目</button>{result.warnings.map((w,i)=><p className="import-warning" key={i}>{w}</p>)}</aside><div className="import-editor"><fieldset disabled={!!busy} className="editor-fieldset"><DraftEditor draft={result.items[index]} knowledge={data.knowledge} onChange={change}/></fieldset>{result.items.length>1&&<button className="text-btn warning-text" onClick={()=>{setResult({...result,items:result.items.filter((_,i)=>i!==index)});setIndex(Math.max(0,index-1))}}>移除此条草稿</button>}</div></div>}</div>{result&&<div className="modal-actions"><span className="subtle">{saveState} · 已核实 {result.items.filter(q=>q.verified).length} / {result.items.length} · 未核实题目仅保存，暂不进入计划</span><button className="btn secondary" disabled={!!busy} onClick={()=>leave(true)}>返回上传</button><button className="btn secondary" disabled={!!busy} onClick={()=>leave()}>保存并关闭</button><button className="btn primary" disabled={!!busy||conflict||result.items.some(q=>!q.title.trim()||!q.body.trim())} onClick={save}>{busy?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>}确认入库</button></div>}</Modal>
}

function Settings({data,onSaved,onStart,onRestored}:{data:State;onSaved:()=>Promise<void>;onStart:()=>void;onRestored:()=>Promise<void>}) {
  const [url,setUrl]=useState(data.ai.base_url)
  const [model,setModel]=useState(data.ai.model)
  const [key,setKey]=useState('')
  const [jsonMode,setJsonMode]=useState(data.ai.json_mode)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  return <div className="settings-layout"><section className="panel settings-card"><div className="section-head"><div><h2><Sparkles size={19}/>连接 AI</h2><p>使用支持图片输入的 Chat Completions 兼容服务</p></div><span className={`tag ${data.ai.configured?'sage':'neutral'}`}>{data.ai.configured?'已配置':'待配置'}</span></div><div className="settings-body">{error&&<div className="alert error">{error}</div>}<label>API 基础地址<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://你的模型服务/v1"/><small>填写服务商提供的基础地址，程序会追加 /chat/completions。</small></label><label>模型名称<input value={model} onChange={e=>setModel(e.target.value)} placeholder="填写 API 模型 ID，如 deepseek-flash"/><small>DeepSeek 官方 Flash 模型填写 deepseek-flash，不能用 ds 或带空格的显示名称。照片功能还需模型支持图片输入。</small></label><label>API Key<input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} placeholder={data.ai.has_key?'已提供密钥；留空继续使用':'输入 API Key'}/><small>仅在本次后台运行期间保留，不写入数据库；也可通过 STUDY_API_KEY 环境变量提供。</small></label><label className="checkbox-line"><input type="checkbox" checked={jsonMode} onChange={e=>setJsonMode(e.target.checked)}/>请求 JSON 输出模式（服务不支持时可关闭）</label><div className="inline-note"><ShieldCheck size={17}/><span>调用时，相关题目与照片将发送到这个模型服务。掌握度、复习日期和选题仍由本地程序计算。</span></div><button className="btn primary" disabled={busy||!url} onClick={async()=>{setBusy(true);setError('');try{await api('/settings/ai',{base_url:url,model,api_key:key,json_mode:jsonMode});setKey('');await onSaved()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>{busy?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>}保存配置</button></div></section><div><section className="panel settings-card"><div className="section-head"><h2><Database size={18}/>学习数据</h2></div><div className="settings-body"><div className="data-line"><span>存储位置</span><strong>这台电脑 · SQLite</strong></div><div className="data-line"><span>当前题库</span><strong>{data.questions.length} 道题目</strong></div><div className="data-line"><span>时区</span><strong>Asia/Shanghai</strong></div><a href="/api/export" className="btn secondary full" download><ArrowDownToLine size={16}/>导出数据与照片备份</a><p className="subtle">导出包含题目、作答、照片与校对草稿，不包含 API Key。</p></div></section><BackupPanel onRestored={onRestored}/>{data.demo_mode&&<section className="panel settings-card"><div className="section-head"><h2><GraduationCap size={18}/>示例模式</h2></div><div className="settings-body"><p>示例题为原创演示内容，学习历史为模拟记录。正式导入题目时会自动结束示例模式。</p><button className="btn secondary" onClick={onStart}>清空示例，开始学习<ArrowRight size={15}/></button></div></section>}<div className="settings-footnote"><Leaf size={19}/><p>工具负责安排，<br/>成长按你的节奏发生。</p></div></div></div>
}

createRoot(document.getElementById('root')!).render(<App />)
