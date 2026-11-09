import React, { useEffect, useRef, useState } from 'react'
import { ArrowDownToLine, ArrowLeft, ArrowRight, BookOpen, ChevronLeft, ChevronRight, Clock3, Network, Plus, Search, Sparkles, UploadCloud, Workflow, Cpu, Layers3 } from 'lucide-react'
import type { Question } from './types'
import { Empty } from './ui'
import './library.css'

const BOOKS = [
  { subject: '数据结构', code: 'DS', english: 'DATA STRUCTURES', caption: '从结构出发，让思路有序。', icon: Workflow },
  { subject: '计算机组成原理', code: 'CO', english: 'COMPUTER ORGANIZATION', caption: '走进计算机的运转之中。', icon: Cpu },
  { subject: '操作系统', code: 'OS', english: 'OPERATING SYSTEMS', caption: '理解每一次调度与协作。', icon: Layers3 },
  { subject: '计算机网络', code: 'CN', english: 'COMPUTER NETWORKS', caption: '连接知识，也连接世界。', icon: Network },
]
const TYPES: Record<string, string> = { calculation: '计算题', single: '单选题', multiple: '多选题', boolean: '判断题' }
const PAGE_SIZE = 7
const matches = (q: Question, query: string) => `${q.subject} ${q.title} ${q.body} ${q.knowledge}`.toLowerCase().includes(query.trim().toLowerCase())

type Props = { questions: Question[]; date: string; onOpen: (id: string) => void; onImport: () => void; onManual: () => void }

export function QuestionLibrary({ questions, date, onOpen, onImport, onManual }: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [lifting, setLifting] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [chapter, setChapter] = useState('')
  const [page, setPage] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const reader = useRef<HTMLElement>(null)
  const bookButtons = useRef(new Map<string, HTMLButtonElement>())
  const returnFocus = useRef<string | null>(null)
  // The delay lets the chosen book leave the shelf before the reading view unfolds.
  useEffect(() => {
    if (!lifting) return
    const timer = window.setTimeout(() => { setSelected(lifting); setLifting(null); setChapter(''); setPage(0) }, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 340)
    return () => window.clearTimeout(timer)
  }, [lifting])
  useEffect(() => {
    if (selected) {
      heading.current?.focus({ preventScroll: true })
      const top = reader.current?.getBoundingClientRect().top
      if (top !== undefined && (top < 0 || top > window.innerHeight / 2)) reader.current?.scrollIntoView({ block: 'start' })
    }
    else if (returnFocus.current) { bookButtons.current.get(returnFocus.current)?.focus(); returnFocus.current = null }
  }, [selected])

  const books = [...BOOKS, ...Array.from(new Set(questions.map(q => q.subject))).filter(s => !BOOKS.some(b => b.subject === s)).map(subject => ({ subject, code: '＋', english: 'MY COLLECTION', caption: '每一页，都是新的积累。', icon: BookOpen }))]
  const current = books.find(b => b.subject === selected)
  const subjectQuestions = questions.filter(q => q.subject === selected)
  const chapters = Array.from(new Set(subjectQuestions.map(q => q.knowledge)))
  const visible = subjectQuestions.filter(q => matches(q, query) && (!chapter || q.knowledge === chapter))
  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const closeBook = () => { returnFocus.current = selected; setSelected(null); setQuery(''); setChapter(''); setPage(0) }
  const changeQuery = (value: string) => { setQuery(value); setPage(0) }

  if (current) return <section ref={reader} className={`library-reader book-tone-${books.indexOf(current) % 4}`} aria-label={`${current.subject}题册`}>
    <div className="reader-toolbar"><button className="btn secondary" onClick={closeBook}><ArrowLeft size={15} />放回书架</button><span><BookOpen size={15} />正在翻阅 · {current.subject}</span><button className="text-btn" onClick={onImport}><Plus size={14} />添加题目</button></div>
    <div className="open-book">
      <aside className="book-contents">
        <span className="book-volume">408 / {current.code}</span><current.icon size={30} strokeWidth={1.2} />
        <h2 ref={heading} tabIndex={-1}>{current.subject}</h2><p>{subjectQuestions.length} 道题目 · {chapters.length} 个知识点</p>
        <div className="contents-label">目 录 <span>CONTENTS</span></div>
        <nav aria-label="题册知识点目录"><button className={!chapter ? 'active' : ''} onClick={()=>{setChapter('');setPage(0)}}><span>全部题目</span><small>{subjectQuestions.length}</small></button>{chapters.map((name, i) => <button className={chapter === name ? 'active' : ''} key={name} onClick={()=>{setChapter(name);setPage(0)}}><i>{String(i + 1).padStart(2, '0')}</i><span>{name}</span><small>{subjectQuestions.filter(q=>q.knowledge===name).length}</small></button>)}</nav>
        <div className="contents-foot"><span>拾知 · 我的学习藏书</span><span>{current.code}</span></div>
      </aside>
      <div className="book-question-page">
        <div className="book-running-head"><span>{current.english}</span><span>练习题册</span></div>
        <div className="book-page-heading"><div><span className="eyebrow">PRACTICE & PROGRESS</span><h3>{chapter || '从这一页开始'}</h3><p>{query.trim() ? `找到 ${visible.length} 道相关题目` : `共 ${visible.length} 道题目，选择一道开始思考。`}</p></div><span className="page-flourish" aria-hidden="true">{current.code}</span></div>
        <label className="search-input book-search"><Search size={15} /><input aria-label="搜索本书题目" placeholder="搜索本书的题目、知识点" value={query} onChange={e=>changeQuery(e.target.value)} />{query&&<button onClick={()=>changeQuery('')} aria-label="清除搜索">清除</button>}</label>
        <div className="book-exercises" key={`${chapter}-${safePage}`}>
          {visible.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE).map((q, i) => <button className="book-exercise" key={q.id} onClick={()=>onOpen(q.id)}><span className="exercise-index">{String(safePage * PAGE_SIZE + i + 1).padStart(2,'0')}</span><div><span className="exercise-meta">{TYPES[q.type] || q.type}<span>·</span>{q.knowledge}</span><strong>{q.title}</strong><span className="exercise-status">{!q.verified ? '答案待核实' : q.review && q.review.due_date <= date ? '到期复习' : q.review?.had_error ? '值得再练一次' : '答案已核实'}</span></div><span className="exercise-time"><Clock3 size={11}/>{q.minutes} min</span><ArrowRight size={16}/></button>)}
          {!visible.length&&<Empty title={subjectQuestions.length ? '这一页暂时没有匹配的题目' : '这本书，等你写下第一页'} detail={subjectQuestions.length ? '试试其他关键词，或切换左侧知识点。' : '导入 Excel、Word 或题目照片，题目会按科目整理到书中。'} action={subjectQuestions.length ? <button className="btn soft" onClick={()=>{changeQuery('');setChapter('')}}>查看全部题目</button> : <button className="btn soft" onClick={onImport}><UploadCloud size={15}/>导入题目</button>}/>}
        </div>
        <div className="book-pagination"><button aria-label="上一页" disabled={safePage===0} onClick={()=>setPage(safePage-1)}><ChevronLeft size={15}/>上一页</button><span aria-live="polite">{safePage+1} <i>/</i> {pageCount}</span><button aria-label="下一页" disabled={safePage>=pageCount-1} onClick={()=>setPage(safePage+1)}>下一页<ChevronRight size={15}/></button></div>
      </div>
      <div className="opening-cover" aria-hidden="true"><span>{current.code}</span><strong>{current.subject}</strong><BookOpen size={36}/></div>
    </div>
  </section>

  const matchingBooks = books.filter(b => !query.trim() || b.subject.toLowerCase().includes(query.trim().toLowerCase()) || questions.some(q=>q.subject===b.subject&&matches(q,query)))
  return <section className="library-shelf" aria-label="科目书架">
    <div className="library-tools"><label className="search-input"><Search size={16}/><input aria-label="搜索书架" placeholder="搜索科目、题目或知识点" value={query} onChange={e=>changeQuery(e.target.value)}/></label><button className="btn secondary" onClick={onManual}><Plus size={15}/>手动录题</button><a className="text-btn" href="/api/template" download><ArrowDownToLine size={14}/>Excel 模板</a></div>
    <div className="shelf-room">
      <div className="shelf-heading"><div><span className="eyebrow">THE PERSONAL COLLECTION</span><h2>知识，值得好好收藏。</h2><p>挑一本，翻开今天的积累。</p></div><span className="shelf-total"><BookOpen size={16}/>{books.length} 本藏书<span>·</span>{questions.length} 道题目</span></div>
      <div className="bookshelf" aria-busy={!!lifting}>
        {matchingBooks.map(book => {
          const items = questions.filter(q=>q.subject===book.subject)
          const due = items.filter(q=>q.review&&q.review.due_date<=date).length
          return <div className="shelf-slot" key={book.subject}>
            <button ref={el=>{if(el)bookButtons.current.set(book.subject,el);else bookButtons.current.delete(book.subject)}} className={`shelf-book book-tone-${books.indexOf(book)%4} ${lifting===book.subject?'is-lifting':''}`} onClick={()=>{if(!lifting)setLifting(book.subject)}} aria-label={`翻开${book.subject}，${items.length}道题目`} aria-disabled={!!lifting}>
              <span className="book-paper" aria-hidden="true"/><span className="book-cover"><span className="cover-topline">拾知题册<span>408</span></span><span className="cover-emblem"><book.icon size={38} strokeWidth={1}/></span><strong>{book.subject==='计算机组成原理'?<>计算机<br/>组成原理</>:book.subject}</strong><span className="cover-english">{book.english}</span><span className="cover-rule"/><span className="cover-bottom"><span>{String(books.indexOf(book)+1).padStart(2,'0')} / {book.code}</span><span>{items.length} 题</span></span><span className="cover-open"><BookOpen size={14}/>点击翻开</span></span>
            </button>
            <div className="shelf-book-label"><strong>{book.subject}</strong><span>{query.trim()?`${items.filter(q=>matches(q,query)).length} 道匹配`:due?`${due} 道等待复习`:items.length?'每一题，都是一点积累':'等待你的第一份材料'}</span></div>
          </div>
        })}
        {!matchingBooks.length&&<div className="shelf-no-results"><Empty title="书架上没有找到相关内容" detail="试试科目名称、题目标题或知识点。" action={<button className="btn soft" onClick={()=>changeQuery('')}>查看全部藏书</button>}/></div>}
      </div>
      <div className="shelf-foot"><span><Sparkles size={14}/>把一本书读薄，再把知识读厚。</span><span>悬停轻提 · 点击翻开</span></div>
    </div>
    <button className="library-import" onClick={onImport}><span className="library-import-icon"><UploadCloud size={22}/></span><span><strong>让下一份材料，也成为你的藏书</strong><small>导入 Excel、Word 或题目照片，AI 帮你识别整理。</small></span><ArrowRight size={18}/></button>
    <span className="library-announcement" role="status">{lifting?`正在取出${lifting}…`:''}</span>
  </section>
}
