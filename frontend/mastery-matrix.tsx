import { useId, useState, type CSSProperties } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { Empty } from './ui'
import { subjectNames } from './subject-folder'
import type { Knowledge } from './types'
import './mastery-matrix.css'

export function MasteryMatrix({ knowledge, onPointClick }: {
  knowledge: Knowledge[]; onPointClick?: (point: Knowledge)=>void;
}) {
  const id = useId()
  const [query,setQuery] = useState('')
  const [expanded,setExpanded] = useState<string|null>(null)
  const names = subjectNames(knowledge.map(k=>k.subject))
  const keyword = query.trim().toLowerCase()
  const matches = (point:Knowledge)=>`${point.subject} ${point.name} ${point.chapter}`.toLowerCase().includes(keyword)
  const rows = names.map(subject=>{
    const points = knowledge.filter(k=>k.subject===subject)
    const practiced = points.filter(k=>k.evidence>0)
    return { subject, points, practiced, mastery: practiced.length?Math.round(practiced.reduce((sum,k)=>sum+k.mastery,0)/practiced.length):null }
  }).filter(row=>row.points.length>0)
  const pointWidth = Math.max(240,...rows.map(row=>row.points.length*28-6))
  const matchCount = knowledge.filter(matches).length

  return <section className="mastery-matrix" aria-label="知识点覆盖情况">
    <div className="matrix-toolbar"><label className="search-input"><Search size={16}/><input aria-label="搜索知识点" placeholder="搜索科目、章节或知识点" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
    <details className="learning-rules"><summary>判定规则</summary><p>掌握度来自已确认作答；证据不足时显示“证据较少”，未练习的知识点显示“待评估”。科目表现仅汇总有作答证据的知识点，不代表整科掌握度或考试正确率。</p></details>
    {knowledge.length>0?<>
      {keyword&&<p className="matrix-search-result" role="status">{matchCount?`匹配 ${matchCount} 个知识点，其余方格已淡化。`:'没有匹配的知识点。试试科目名称或更短的关键词。'}<button className="text-btn" onClick={()=>setQuery('')}>清除搜索</button></p>}
      <div className="matrix-scroll" role="region" aria-label="知识点覆盖矩阵，可横向滚动" tabIndex={0}>
        <ul className="matrix-rows" style={{'--matrix-point-width':`${pointWidth}px`} as CSSProperties}>
          {rows.map(({subject,points,practiced,mastery})=>{
            const open = expanded===subject
            const shown = points.filter(matches)
            const subjectIndex = names.indexOf(subject)
            return <li className="matrix-subject" key={subject}>
              <section aria-labelledby={`${id}-subject-${subjectIndex}`}>
                <div className="matrix-row">
                  <h2 id={`${id}-subject-${subjectIndex}`}><button className="matrix-subject-toggle" onClick={()=>setExpanded(open?null:subject)} aria-expanded={open} aria-controls={`${id}-details-${subjectIndex}`}><span className={`matrix-subject-dot folder-tone-${subjectIndex%4}`} aria-hidden="true"/><span>{subject}</span><ChevronDown size={12} aria-hidden="true"/></button></h2>
                  <span className={`matrix-mastery${mastery===null?' is-unassessed':''}`} aria-label={mastery===null?'待评估':`已练知识点表现 ${mastery}%`}>{mastery===null?'待评估':`${mastery}%`}</span>
                  <ul className="matrix-points" aria-label={`${subject}的知识点覆盖情况`}>{points.map(point=>{
                    const state = !practiced.length?'unassessed':point.evidence===0?'untouched':point.mastery>=50?'strong':'weak'
                    const label = `${point.name} · 表现 ${point.evidence>0?`${point.mastery}%`:'待评估'} · ${point.question_count} 题`
                    return <li key={point.id}><button className={`matrix-point matrix-point-${state}${keyword&&!matches(point)?' is-dimmed':''}`} title={label} aria-label={label} onClick={()=>onPointClick?.(point)}/></li>
                  })}</ul>
                  <span className="matrix-practiced">{practiced.length}/{points.length} 已练</span>
                </div>
                <div className="matrix-details" id={`${id}-details-${subjectIndex}`} hidden={!open}>
                  {open&&<>
                    <div className="folder-content-heading">知识点掌握情况<span>{shown.length} 个{keyword?'匹配结果':'知识点'}</span></div>
                    <ul className="knowledge-folder-list">{shown.map(k=><li className="knowledge-item" key={k.id}><div><strong>{k.name}</strong><span className={k.evidence===0?'muted':k.mastery<50?'warning-text':'green-text'}>{k.status}</span></div><div className="progress-track"><span style={{width:k.evidence?`${k.mastery}%`:'0%'}}/></div><div className="knowledge-meta"><span>{k.evidence?`表现指标 ${k.mastery}% · 有效证据 ${k.evidence}`:'等待首次独立作答'}</span><span>{k.question_count} 题{k.due_count>0&&` · ${k.due_count} 到期`}</span></div></li>)}</ul>
                    {!shown.length&&<p className="matrix-details-empty">这一科没有匹配的知识点，试试其他关键词。</p>}
                  </>}
                </div>
              </section>
            </li>
          })}
        </ul>
      </div>
      <ul className="matrix-legend" aria-label="方格状态说明"><li><span className="matrix-legend-square matrix-point-strong" aria-hidden="true"/>表现 ≥50%</li><li><span className="matrix-legend-square matrix-point-weak" aria-hidden="true"/>已练但较弱</li><li><span className="matrix-legend-square matrix-point-untouched" aria-hidden="true"/>未练习</li><li><span className="matrix-legend-square matrix-point-unassessed" aria-hidden="true"/>整科待评估</li></ul>
      <p className="matrix-note"><span className="matrix-mobile-hint">左右滑动查看完整矩阵。 </span>点击科目名可展开知识点详情。</p>
    </>:<div className="matrix-empty"><Empty title="还没有知识点。" detail="导入题目后会自动建立索引。"/></div>}
  </section>
}
