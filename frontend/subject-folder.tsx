import { useId, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import './subject-folder.css'

const SUBJECTS = ['数据结构', '计算机组成原理', '操作系统', '计算机网络']

export const subjectNames = (names: string[]) => [...SUBJECTS, ...Array.from(new Set(names)).filter(name=>!SUBJECTS.includes(name))]

type Props = {
  subject: string; index: number; open: boolean; onToggle: () => void;
  description: string; badge: string; metrics: { label: string; value: ReactNode }[];
  children: ReactNode
}

export function SubjectFolder({ subject, index, open, onToggle, description, badge, metrics, children }: Props) {
  const id = useId()
  return <section className={`subject-folder folder-tone-${index % 4} ${open?'is-open':''}`}>
    <h2 className="folder-heading"><button className="folder-toggle" onClick={onToggle} aria-expanded={open} aria-controls={id} aria-label={`${open?'收起':'展开'}${subject}`}>
      <span className="folder-top"><span className="folder-subject-dot" aria-hidden="true"/><span className="folder-title"><strong>{subject}</strong><span>{description}</span></span></span>
      <span className="folder-metrics">{metrics.map((metric, index)=><span className={index===0?'folder-metric-primary':'folder-metric-secondary'} key={metric.label}><strong>{metric.value}</strong><span>{metric.label}</span></span>)}</span>
      <span className="folder-bottom"><span className="folder-badge">{badge}</span><span className="folder-affordance" aria-hidden="true"><ChevronDown size={15}/></span></span>
    </button></h2>
    <div id={id} hidden={!open} className="folder-content">{open&&children}</div>
  </section>
}

export function FolderPagination({ page, count, onPage, label = '内容' }: {page:number;count:number;onPage:(page:number)=>void;label?:string}) {
  if (count<=1) return null
  return <div className="folder-pagination" aria-label={`${label}分页`}><button className="btn secondary" disabled={page===0} onClick={()=>onPage(page-1)}>上一页</button><span aria-live="polite">第 {page+1} / {count} 页</span><button className="btn secondary" disabled={page>=count-1} onClick={()=>onPage(page+1)}>下一页</button></div>
}
