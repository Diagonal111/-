import { useId, useState } from 'react'
import { ArrowRight, Search } from 'lucide-react'
import { Empty } from './ui'
import { FolderPagination, subjectNames } from './subject-folder'
import type { Question } from './types'
import './review-queue.css'

const PAGE_SIZE = 12
const TYPES: Record<string,string> = { calculation: '计算题', single: '单选题', multiple: '多选题', boolean: '判断题' }
const FILTERS = { all: '全部待练', due: '到期复习', error: '历史错题' }
const GROUPS = [
  { key: 'overdue', label: '逾期' },
  { key: 'today', label: '今天到期' },
  { key: 'later', label: '之后' },
  { key: 'history', label: '历史错题' },
] as const
type GroupKey = typeof GROUPS[number]['key']

function groupKey(question: Question, date: string): GroupKey {
  const dueDate = question.review?.due_date
  if (!dueDate) return 'history'
  return dueDate < date ? 'overdue' : dueDate === date ? 'today' : 'later'
}

export function dueLabel(dueDate: string | undefined, date: string) {
  if (!dueDate) return '历史错题'
  if (dueDate === date) return '今天'
  if (dueDate < date) {
    // ISO calendar dates use UTC here so daylight-saving changes cannot add a day.
    const days = Math.round((Date.parse(`${date}T00:00:00Z`)-Date.parse(`${dueDate}T00:00:00Z`))/86400000)
    return `逾期 ${days} 天`
  }
  const [, month, day] = dueDate.split('-')
  return `${Number(month)}月${Number(day)}日`
}

export function groupReviewQueue(questions: Question[], date: string, names = subjectNames(questions.map(q=>q.subject))) {
  return GROUPS.map(group=>({ ...group, questions: questions.filter(q=>groupKey(q,date)===group.key).sort((a,b)=>
    (a.review?.due_date||'').localeCompare(b.review?.due_date||'') || names.indexOf(a.subject)-names.indexOf(b.subject)
  ) }))
}

export function ReviewQueue({ questions, date, onOpen, onLibrary }: {
  questions: Question[]; date: string; onOpen: (id:string)=>void; onLibrary: ()=>void;
}) {
  const id = useId()
  const [query,setQuery] = useState('')
  const [filter,setFilter] = useState<keyof typeof FILTERS>('all')
  const [subject,setSubject] = useState('')
  const [page,setPage] = useState(0)
  const names = subjectNames(questions.map(q=>q.subject))
  const due = (q:Question)=>!!q.review&&q.review.due_date<=date
  const candidates = questions.filter(q=>q.review&&(q.review.had_error||due(q)))
  const selectedSubject = names.includes(subject)?subject:''
  const keyword = query.trim().toLowerCase()
  const filtered = candidates.filter(q=>
    (filter==='all'||filter==='due'&&due(q)||filter==='error'&&q.review?.had_error) &&
    (!selectedSubject||q.subject===selectedSubject) &&
    `${q.subject} ${q.title} ${q.knowledge} ${q.body}`.toLowerCase().includes(keyword)
  )
  const groups = groupReviewQueue(filtered,date,names)
  const queue = groups.flatMap(group=>group.questions)
  const count = Math.ceil(queue.length/PAGE_SIZE)
  const safePage = Math.min(page,Math.max(0,count-1))
  const visibleIds = new Set(queue.slice(safePage*PAGE_SIZE,(safePage+1)*PAGE_SIZE).map(q=>q.id))
  const overdue = groups[0].questions.length
  const today = groups[1].questions.length
  const pointCount = new Set(queue.map(q=>q.knowledge_id)).size
  const hasFilters = filter!=='all'||!!selectedSubject||!!keyword
  const reset = ()=>{setQuery('');setFilter('all');setSubject('');setPage(0)}

  return <section className="review-queue" aria-label="按紧迫度排列的复习队列">
    <div className="review-toolbar">
      <div className="review-filters" role="group" aria-label="按复习分类筛选">{Object.entries(FILTERS).map(([key,label])=><button key={key} aria-pressed={filter===key} onClick={()=>{setFilter(key as keyof typeof FILTERS);setPage(0)}}>{label}</button>)}</div>
      <div className="review-search-tools">
        <select aria-label="筛选复习科目" value={selectedSubject} onChange={e=>{setSubject(e.target.value);setPage(0)}}><option value="">全部科目</option>{names.filter(name=>candidates.some(q=>q.subject===name)).map(name=><option key={name} value={name}>{name}</option>)}</select>
        <label className="search-input"><Search size={16}/><input aria-label="搜索错题与复习" placeholder="搜索科目、题目或知识点" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}}/></label>
      </div>
    </div>
    <div className="review-summary">
      <p role="status">{hasFilters&&<span>当前筛选： </span>}今天到期 <strong>{today}</strong> 道，逾期 <strong className={overdue?'review-overdue-count':undefined}>{overdue}</strong> 道 · 涉及 {pointCount} 个知识点</p>
      <button className="btn primary" disabled={!queue.length} onClick={()=>{if(queue[0])onOpen(queue[0].id)}}>开始复习<ArrowRight size={15}/></button>
    </div>
    <details className="learning-rules"><summary>判定规则</summary><p>按到期时间整理到期复习与历史错题；当天订正不会替代下一次独立复习。到期与历史错题可能重叠，题目只收录一次。</p></details>
    {queue.length?<>
      <div className="review-groups">{groups.map(group=>{
        const shown=group.questions.filter(q=>visibleIds.has(q.id))
        return shown.length>0&&<section className={`review-group review-group-${group.key}`} key={group.key} aria-labelledby={`${id}-${group.key}`}>
          <h2 id={`${id}-${group.key}`}>{group.label}</h2>
          <ul>{shown.map(q=><li key={q.id}>
            <button className="review-queue-row" onClick={()=>onOpen(q.id)}>
              <span className={`review-subject-dot folder-tone-${names.indexOf(q.subject)%4}`} aria-hidden="true"/>
              <span className="review-question"><strong>{q.title}</strong><span>{q.subject} · {TYPES[q.type]||q.type}{!q.verified?' · 答案待核实':''}</span></span>
              <span className={`review-date-label${group.key==='overdue'?' is-overdue':''}`}>{dueLabel(q.review?.due_date,date)}</span>
            </button>
          </li>)}</ul>
        </section>
      })}</div>
      <FolderPagination page={safePage} count={count} onPage={setPage} label="复习队列"/>
    </>:<div className="review-empty"><Empty title={hasFilters?'没有找到相关待练题。':'今天没有要复习的题。'} detail={hasFilters?'试试其他关键词、科目或复习分类。':'可以去题库挑几道新题。'} action={hasFilters?<button className="btn secondary" onClick={reset}>查看全部待练</button>:<button className="btn secondary" onClick={onLibrary}>去题库</button>}/></div>}
  </section>
}
