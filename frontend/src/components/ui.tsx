import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowRight, Leaf, LoaderCircle, RotateCw, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { clsx } from 'clsx'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import type { Media } from '../types'
import ImageViewer from './ImageViewer'

export function Logo({ small = false }: { small?: boolean }) {
  return <span className={clsx('brand', small && 'brand-small')}><span className="brand-mark"><Leaf size={small ? 20 : 25} strokeWidth={1.65}/></span><span className="brand-word">拾忆<span>SHIYI</span></span></span>
}
export function Spinner() { return <LoaderCircle className="spin" size={18}/> }
export function Loading({ text = '正在整理你的学习空间…' }: { text?: string }) { return <div className="loading-state"><Spinner/><span>{text}</span></div> }
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) { return <div className="error-state"><p>{error instanceof Error ? error.message : '加载未完成'}</p>{retry && <button className="button secondary" onClick={retry}><RotateCw size={16}/>重新加载</button>}</div> }
export function Empty({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon ?? <Leaf size={32} strokeWidth={1.3}/>}</div><h3>{title}</h3><p>{description}</p>{action}</div>
}
export function PageHeading({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="heading-actions">{actions}</div>}</div>
}
export function SectionTitle({ title, note, to }: { title: string; note?: string; to?: string }) {
  return <div className="section-title"><h2>{title}</h2>{to ? <Link to={to}>{note ?? '查看全部'}<ArrowRight size={15}/></Link> : note && <span>{note}</span>}</div>
}
export function Modal({ children, title, onClose, className = '' }: { children: ReactNode; title: string; onClose: () => void; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const el = ref.current; el?.showModal(); const previous = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { el?.close(); document.body.style.overflow = previous } }, [])
  return <dialog ref={ref} className={`modal ${className}`} aria-label={title} onCancel={e => { e.preventDefault(); onClose() }} onClick={e => { if (e.target === ref.current) onClose() }}><div className="modal-header"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={20}/></button></div>{children}</dialog>
}
export function Content({ text, media = [], className = '' }: { text?: string; media?: Media[]; className?: string }) {
  const images = useRef<HTMLDivElement>(null)
  const [viewer, setViewer] = useState<{ index: number; initialZoom: number } | null>(null)
  useEffect(() => {
    const element = images.current
    if (!element) return
    const wheel = (event: WheelEvent) => {
      if ((!event.ctrlKey && !event.metaKey) || !event.deltaY) return
      const button = (event.target as HTMLElement).closest<HTMLElement>('[data-image-index]')
      if (!button) return
      event.preventDefault()
      setViewer({ index: Number(button.dataset.imageIndex), initialZoom: event.deltaY < 0 ? 1.25 : .8 })
    }
    element.addEventListener('wheel', wheel, { passive: false })
    return () => element.removeEventListener('wheel', wheel)
  }, [media.length])
  return <div className={`rich-content ${className}`}>
    {text && <Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={{ a: props => <a {...props} target="_blank" rel="noopener noreferrer"/>, img: () => <span className="muted">[外部图片请通过附件上传]</span> }}>{text}</Markdown>}
    {media.length > 0 && <div ref={images} className="content-images">{media.map((m, i) => <button type="button" key={m.id} data-image-index={i} className="image-view" onClick={() => setViewer({ index: i, initialZoom: 1 })} aria-label={`放大图片 ${i + 1}`}><img src={m.url} alt={m.filename} loading="lazy"/><span>点击放大 · Ctrl＋滚轮缩放</span></button>)}</div>}
    {viewer !== null && media[viewer.index] && <ImageViewer media={media} index={viewer.index} initialZoom={viewer.initialZoom} onChange={index => setViewer({ index, initialZoom: 1 })} onClose={() => setViewer(null)}/>}
  </div>
}
export function Heatmap({ days }: { days: { date: string; count: number }[] }) {
  return <div className="heatmap-wrap"><div className="heatmap-labels"><span>一</span><span>三</span><span>日</span></div><div className="heatmap">{days.map(d => <div key={d.date} className={`heat-cell level-${d.count === 0 ? 0 : d.count < 5 ? 1 : d.count < 15 ? 2 : d.count < 30 ? 3 : 4}`} title={`${d.date} · ${d.count} 次复习`} aria-label={`${d.date}，${d.count} 次复习`}/>)}</div></div>
}
