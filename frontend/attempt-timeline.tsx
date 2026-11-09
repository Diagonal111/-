import { useId } from 'react'
import { subjectNames } from './subject-folder'
import type { AttemptSummary } from './types'
import './attempt-timeline.css'

const STATUS = { pending: '待确认', confirmed: '已确认', voided: '已撤销', outdated: '题目已更新' }
const GRADE = { correct: '正确', partial: '部分正确', incorrect: '错误', unknown: '无法判定' }
const clock = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

const dayKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`

// Calendar dates, rather than elapsed hours, keep midnight and DST boundaries correct.
export function groupByDay(items: AttemptSummary[], now = new Date()) {
  const today = dayKey(now)
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate()-1)
  const yesterdayKey = dayKey(yesterday)
  const groups = new Map<string, { key: string; label: string; items: AttemptSummary[] }>()
  for (const item of [...items].sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime())) {
    const date = new Date(item.created_at)
    const key = dayKey(date)
    if (!groups.has(key)) groups.set(key, {
      key,
      label: key===today?'今天':key===yesterdayKey?'昨天':`${date.getMonth()+1}月${date.getDate()}日`,
      items: [],
    })
    groups.get(key)!.items.push(item)
  }
  return [...groups.values()]
}

export function AttemptTimeline({ items, subjects, onOpen }: {
  items: AttemptSummary[]; subjects: string[]; onOpen: (id: string) => void;
}) {
  const id = useId()
  const names = subjectNames([...subjects, ...items.map(item=>item.subject)])
  return <ol className="attempt-timeline" aria-label="按日期排列的学习记录">
    {groupByDay(items).map(group=><li className="timeline-day" key={group.key}>
      <section aria-labelledby={`${id}-${group.key}`}>
        <h2 className="timeline-date" id={`${id}-${group.key}`}><time dateTime={group.key} title={group.key}>{group.label}</time></h2>
        <ol className="timeline-entries">
          {group.items.map(item=><li className={`timeline-entry timeline-entry-${item.status}`} key={item.id}>
            <button className="timeline-row" onClick={()=>onOpen(item.id)}>
              <time className="timeline-time" dateTime={item.created_at}>{clock.format(new Date(item.created_at))}</time>
              <span className={`timeline-subject-dot folder-tone-${names.indexOf(item.subject)%4}`} aria-hidden="true"/>
              <span className="timeline-content"><strong>{item.title}</strong><span>{item.knowledge}{item.hinted?' · 使用提示':''}<span className="timeline-subject"> · {item.subject}</span></span></span>
              <span className={`timeline-status timeline-status-${item.status}`}>{STATUS[item.status]}{item.status==='confirmed'&&item.grade?` · ${GRADE[item.grade]}`:''}</span>
            </button>
          </li>)}
        </ol>
      </section>
    </li>)}
  </ol>
}
