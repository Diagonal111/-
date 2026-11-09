import React, { useEffect, useRef } from 'react'
import { BookOpen, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
export function Markdown({ children }: { children: string }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} components={{
    img: ({ src, alt }) => typeof src === 'string' && /^\/attachments\/[a-f0-9]{32}\.jpg$/.test(src) ? <img src={src} alt={alt || '题目图片'} /> : <span>[外部图片已省略，请查看原材料]</span>,
    a: ({ children }) => <span>{children}</span>,
  }}>{children}</ReactMarkdown></div>
}

export function Modal({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle?: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const previous = document.activeElement as HTMLElement
    ref.current?.focus()
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeRef.current()
      if (e.key === 'Tab') {
        const items=Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled):not([hidden]),textarea:not(:disabled),select:not(:disabled)')||[]).filter(el=>el.getClientRects().length>0)
        const first=items[0],last=items[items.length-1]
        if (e.shiftKey&&(document.activeElement===first||document.activeElement===ref.current)) { e.preventDefault();last?.focus() }
        else if(!e.shiftKey&&(document.activeElement===last||document.activeElement===ref.current)) { e.preventDefault();first?.focus() }
      }
    }
    window.addEventListener('keydown', close)
    const old = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', close); document.body.style.overflow = old; previous?.focus() }
  }, [])
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
      <div className="modal-head"><div><span className="eyebrow">YOUR LEARNING SPACE</span><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-btn" aria-label="关闭" onClick={onClose}><X size={20} /></button></div>
      {children}
    </div>
  </div>
}

export function Empty({ title, detail, action }: { title: string; detail: string; action?: React.ReactNode }) {
  return <div className="empty"><div className="empty-icon"><BookOpen size={28} /></div><h3>{title}</h3><p>{detail}</p>{action}</div>
}
