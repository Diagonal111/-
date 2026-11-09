import { useEffect, useState } from 'react'
import { ArrowRight, Check, RefreshCw, Search } from 'lucide-react'
import { api } from './api'
import { Empty, Markdown, Modal } from './ui'
import type { AttemptDetail, AttemptSummary, Grade, State } from './types'
import { FolderPagination } from './subject-folder'
import { AttemptTimeline } from './attempt-timeline'

const STATUS = { all: '全部记录', pending: '待确认', confirmed: '已确认', voided: '已撤销', outdated: '题目已更新' }
const GRADE: Record<string,string> = { correct: '正确', partial: '部分正确', incorrect: '错误', unknown: '无法判定' }
const PAGE_SIZE = 20
const time = (value:string) => new Date(value).toLocaleString('zh-CN', { hour12:false })

export function Records({onChanged,onResume,refreshKey}:{onChanged:()=>Promise<void>;onResume:(a:AttemptDetail)=>void;refreshKey:State}) {
  const [status,setStatus]=useState('all'), [query,setQuery]=useState('')
  const [items,setItems]=useState<AttemptSummary[]>([])
  const [page,setPage]=useState(0), [total,setTotal]=useState(0)
  const [pending,setPending]=useState<{count:number;firstId:string|null}>({count:0,firstId:null})
  const [detail,setDetail]=useState<AttemptDetail|null>(null), [grade,setGrade]=useState<Grade>('unknown')
  const [error,setError]=useState(''), [busy,setBusy]=useState(false), [revision,setRevision]=useState(0)
  const [loading,setLoading]=useState(true)
  useEffect(()=>{
    let active=true
    setLoading(true)
    const timer=setTimeout(async()=>{
      try {
        const result=await api<{items:AttemptSummary[];total:number}>(`/attempts?status=${status}&query=${encodeURIComponent(query.trim())}&limit=${PAGE_SIZE}&offset=${page*PAGE_SIZE}`)
        if(active){
          const lastPage=Math.max(0,Math.ceil(result.total/PAGE_SIZE)-1)
          if(page>lastPage){setPage(lastPage);return}
          setItems(result.items);setTotal(result.total);setError('')
        }
      }catch(e){if(active){setItems([]);setTotal(0);setError((e as Error).message)}}finally{if(active)setLoading(false)}
    },200)
    return()=>{active=false;clearTimeout(timer)}
  },[status,query,page,revision,refreshKey])
  useEffect(()=>{
    let active=true
    api<{items:AttemptSummary[];total:number}>('/attempts?status=pending&limit=1').then(result=>{
      if(active)setPending({count:result.total,firstId:result.items[0]?.id??null})
    }).catch(()=>{if(active)setPending({count:0,firstId:null})})
    return()=>{active=false}
  },[revision,refreshKey])
  const open=async(id:string)=>{setError('');try{const a=await api<AttemptDetail>(`/attempts/${id}`);setDetail(a);setGrade(a.grade||'unknown')}catch(e){setError((e as Error).message)}}
  const change=async(action:'grade'|'void'|'restore')=>{
    if(!detail)return
    setBusy(true);setError('')
    try{
      await api(`/attempts/${detail.id}/${action==='grade'?'confirm':'status'}`,action==='grade'?{grade,version:detail.version}:{action,version:detail.version})
      await onChanged();await open(detail.id);setRevision(v=>v+1)
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  const filtered=status!=='all'||!!query.trim()
  return <>
    <section className="records-page" aria-label="学习记录时间线">
      <div className="records-toolbar"><label className="search-input"><Search size={16}/><input aria-label="搜索学习记录" placeholder="搜索题目、知识点、作答" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);setLoading(true)}}/></label></div>
      <div className="records-filters" role="group" aria-label="按记录状态筛选">{Object.entries(STATUS).map(([key,label])=><button key={key} aria-pressed={status===key} onClick={()=>{if(status!==key){setStatus(key);setPage(0);setLoading(true)}}}>{label}</button>)}</div>
      {pending.count>0&&pending.firstId&&<div className="records-pending"><span><strong>{pending.count}</strong> 次作答等待确认</span><button className="text-btn" onClick={()=>{if(pending.firstId)void open(pending.firstId)}}>逐个确认<ArrowRight size={14}/></button></div>}
      {error&&!detail&&<div role="alert" className="alert error records-refresh-error"><span>{error}</span><button className="text-btn" onClick={()=>setRevision(v=>v+1)}>重新读取</button></div>}
      <details className="learning-rules"><summary>判定规则</summary><p>只有已确认且未撤销的记录参与掌握度计算。更正、撤销后会按原作答日期重算。</p></details>
      <div className="records-caption" role="status">{loading?'正在读取记录…':error?'记录暂时无法读取':`共 ${total} 次作答${filtered?' · 当前筛选':''}`}</div>
      <div className="records-timeline-body" aria-busy={loading}>
        {loading?<p className="grouped-loading" role="status">正在读取学习记录…</p>:error&&!items.length?<Empty title="暂时无法读取学习记录" detail="请点击上方“重新读取”再试一次。"/>:items.length?<AttemptTimeline items={items} subjects={refreshKey.knowledge.map(k=>k.subject)} onOpen={open}/>:<Empty title={filtered?'没有找到符合条件的记录':'还没有记录。'} detail={filtered?'试试其他关键词，或切换记录状态。':'完成一次练习后会自动归档到这里。'} action={filtered?<button className="btn soft" onClick={()=>{setQuery('');setStatus('all');setPage(0);setLoading(true)}}>查看全部记录</button>:undefined}/>}
        {!loading&&!error&&<FolderPagination page={page} count={Math.ceil(total/PAGE_SIZE)} onPage={next=>{setPage(next);setLoading(true)}} label="学习记录"/>}
      </div>
    </section>
    {detail&&<Modal wide title="查看学习记录" subtitle={`${time(detail.created_at)} · ${STATUS[detail.status]} · 原题第 ${detail.question.revision} 版`} onClose={()=>{if(!busy){setDetail(null);setError('')}}}>
      <div className="modal-body">{error&&<div className="alert error" role="alert">{error}</div>}{detail.current_revision!==detail.question.revision&&<div className="info-strip">题目已更新到第 {detail.current_revision} 版。这里保留本次作答时的题目和参考答案。</div>}
        <div className="record-grid"><section><h3>{detail.question.title}</h3><Markdown>{detail.question.body}</Markdown><div className="record-options">{detail.question.options.map((o,i)=><p key={i}>{String.fromCharCode(65+i)}. {o}</p>)}</div>{detail.question.attachments.map(p=><a key={p} href={'/attachments/'+p} target="_blank" rel="noreferrer"><img className="record-photo" src={'/attachments/'+p} alt="原题照片"/></a>)}<div className="reference-answer"><strong>当时的参考答案</strong><Markdown>{detail.question.answer||'未提供'}</Markdown><Markdown>{detail.question.explanation}</Markdown></div></section>
        <section><h3>原始作答</h3><Markdown>{detail.answer||'本次通过照片作答'}</Markdown><div className="photo-grid">{detail.photos.map(p=><a key={p} href={'/attachments/'+p} target="_blank" rel="noreferrer"><img src={'/attachments/'+p} alt="原始作答照片"/></a>)}</div>{detail.transcription_override&&<><h4>人工修正后的转写</h4><Markdown>{detail.transcription_override}</Markdown></>}
          {detail.ai_result&&<><h4>{detail.ai_result.mode==='ai'?'AI 批改建议':'原判分建议'} · {GRADE[detail.ai_result.grade]}</h4><Markdown>{detail.ai_result.summary}</Markdown>{detail.ai_result.transcription&&<details><summary>查看转写内容</summary><Markdown>{detail.ai_result.transcription}</Markdown></details>}{detail.ai_result.steps?.map((s,i)=><div className="step-review" key={i}><strong>{s.verdict}</strong><blockquote>{s.quote}</blockquote><p>{s.reason}</p></div>)}{detail.ai_result.uncertainties?.map((u,i)=><p className="warning-text" key={i}>{u}</p>)}</>}
          {detail.status==='confirmed'&&<><h4>更正最终结论</h4><div className="grade-choices">{(['correct','partial','incorrect'] as Grade[]).map(g=><button key={g} className={`${g} ${grade===g?'selected':''}`} onClick={()=>setGrade(g)}>{grade===g&&<Check size={14}/>} {GRADE[g]}</button>)}</div><button className="btn primary" disabled={busy||grade===detail.grade} onClick={()=>change('grade')}><Check size={15}/>保存更正</button></>}
          {detail.status==='outdated'&&<p className="inline-note">这次未确认的作答对应旧题，请从题库打开最新版本重新作答。</p>}
        </section></div>
        {detail.revisions.length>0&&<details className="history-block"><summary>结论与状态修订记录（{detail.revisions.length} 次）</summary>{detail.revisions.map(r=><div key={r.version}><span>{time(r.confirmed_at)}</span><span>v{r.version} · {r.action==='void'?'撤销记录':r.action==='restore'?'恢复记录':`确认：${GRADE[r.grade]}`}</span></div>)}</details>}
      </div>
      <div className="modal-actions"><span className="subtle">撤销保留原文与照片，可随时恢复。</span>{detail.status==='pending'&&<button className="btn primary" disabled={busy} onClick={()=>{setDetail(null);onResume(detail)}}>继续批改 / 确认<ArrowRight size={15}/></button>}{(detail.status==='confirmed'||detail.status==='pending')&&<button className="btn secondary" disabled={busy} onClick={()=>change('void')}>撤销本次记录</button>}{detail.status==='voided'&&<button className="btn primary" disabled={busy} onClick={()=>change('restore')}><RefreshCw size={15}/>恢复记录</button>}<button className="btn secondary" disabled={busy} onClick={()=>setDetail(null)}>关闭</button></div>
    </Modal>}
  </>
}
