import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react'
import { ArrowLeft, ArrowRight, Maximize, ZoomIn, ZoomOut } from 'lucide-react'
import type { Media } from '../types'
import { Modal } from './ui'
import './image-viewer.css'

const MAX_SCALE = 8
const ZOOM_STEP = 1.25
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value))
type Point = { x: number; y: number }
type View = Point & { scale: number | null }

function ImageSurface({ media, initialZoom }: { media: Media; initialZoom: number }) {
  const viewport = useRef<HTMLDivElement>(null)
  const drag = useRef<{ pointerId: number; start: Point; offset: Point } | null>(null)
  const initialized = useRef(false)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [bounds, setBounds] = useState({ width: 0, height: 0 })
  const [view, setView] = useState<View>({ scale: null, x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(false)
  const ready = !!(size.width && bounds.width && bounds.height) && !error
  const fit = ready ? Math.min(1, bounds.width / size.width, bounds.height / size.height) : 1
  const minScale = Math.min(fit, .1)
  const scale = view.scale ?? fit

  const constrain = useCallback((point: Point, nextScale: number): Point => {
    const maxX = Math.max(0, (size.width * nextScale - bounds.width) / 2)
    const maxY = Math.max(0, (size.height * nextScale - bounds.height) / 2)
    return { x: clamp(point.x, -maxX, maxX), y: clamp(point.y, -maxY, maxY) }
  }, [size, bounds])
  const offset = constrain(view, scale)
  const canDrag = ready && (size.width * scale > bounds.width || size.height * scale > bounds.height)

  useEffect(() => {
    const element = viewport.current!
    const observer = new ResizeObserver(() => setBounds({ width: element.clientWidth, height: element.clientHeight }))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!ready || initialized.current) return
    initialized.current = true
    if (initialZoom !== 1) setView({ scale: clamp(fit * initialZoom, minScale, MAX_SCALE), x: 0, y: 0 })
  }, [ready, fit, minScale, initialZoom])

  const zoom = useCallback((factor: number, point: Point = { x: 0, y: 0 }) => {
    if (!ready) return
    setView(current => {
      const oldScale = current.scale ?? fit
      const nextScale = clamp(oldScale * factor, minScale, MAX_SCALE)
      const oldOffset = constrain(current, oldScale)
      const ratio = nextScale / oldScale
      return { scale: nextScale, ...constrain({
        x: point.x - (point.x - oldOffset.x) * ratio,
        y: point.y - (point.y - oldOffset.y) * ratio,
      }, nextScale) }
    })
  }, [ready, fit, minScale, constrain])

  useEffect(() => {
    const element = viewport.current!
    const wheel = (event: WheelEvent) => {
      // React's delegated wheel listeners are passive; a native listener is needed
      // to prevent Ctrl+wheel from zooming the entire browser page.
      event.preventDefault()
      if (!event.deltaY) return
      const rect = element.getBoundingClientRect()
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1
      zoom(Math.exp(clamp(-event.deltaY * unit * .002, -.5, .5)), {
        x: event.clientX - rect.left - element.clientWidth / 2,
        y: event.clientY - rect.top - element.clientHeight / 2,
      })
    }
    element.addEventListener('wheel', wheel, { passive: false })
    return () => element.removeEventListener('wheel', wheel)
  }, [zoom])

  const begin = (event: PointerEvent<HTMLDivElement>) => {
    if (!canDrag || event.button !== 0 || !event.isPrimary) return
    event.preventDefault()
    event.currentTarget.focus({ preventScroll: true })
    drag.current = { pointerId: event.pointerId, start: { x: event.clientX, y: event.clientY }, offset }
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragging(true)
  }
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const gesture = drag.current
    if (!gesture || gesture.pointerId !== event.pointerId) return
    const next = constrain({ x: gesture.offset.x + event.clientX - gesture.start.x, y: gesture.offset.y + event.clientY - gesture.start.y }, scale)
    setView({ scale, ...next })
  }
  const end = () => { drag.current = null; setDragging(false) }
  const reset = () => setView({ scale: null, x: 0, y: 0 })

  return <>
    <div className="image-zoom-toolbar" role="group" aria-label="图片缩放">
      <button type="button" className="icon-button" aria-label="缩小图片" title="缩小图片" disabled={!ready || scale <= minScale} onClick={() => zoom(1 / ZOOM_STEP)}><ZoomOut size={19}/></button>
      <output className="image-zoom-value" aria-label="图片缩放比例" aria-live="polite">{ready ? `${Math.round(scale * 100)}%` : '—'}</output>
      <button type="button" className="icon-button" aria-label="放大图片" title="放大图片" disabled={!ready || scale >= MAX_SCALE} onClick={() => zoom(ZOOM_STEP)}><ZoomIn size={19}/></button>
      <button type="button" className="button secondary small" disabled={!ready} onClick={() => setView({ scale: 1, x: 0, y: 0 })}>原始大小</button>
      <button type="button" className="button secondary small" disabled={!ready} onClick={reset}><Maximize size={15}/>适应窗口</button>
    </div>
    <div ref={viewport} className={`image-zoom-viewport${canDrag ? ' can-drag' : ''}${dragging ? ' is-dragging' : ''}`} role="region" aria-label="图片查看区域" tabIndex={0}
      onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
      onKeyDown={event => {
        if (event.ctrlKey || event.metaKey || event.altKey || !ready) return
        if (event.key === '+' || event.key === '=') zoom(ZOOM_STEP)
        else if (event.key === '-') zoom(1 / ZOOM_STEP)
        else if (event.key === '0') reset()
        else if (event.key === '1') setView({ scale: 1, x: 0, y: 0 })
        else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
          const delta = { x: event.key === 'ArrowLeft' ? 60 : event.key === 'ArrowRight' ? -60 : 0, y: event.key === 'ArrowUp' ? 60 : event.key === 'ArrowDown' ? -60 : 0 }
          setView({ scale, ...constrain({ x: offset.x + delta.x, y: offset.y + delta.y }, scale) })
        } else return
        event.preventDefault()
        event.stopPropagation()
      }}>
      {error ? <p role="alert">图片加载失败，请关闭后重新打开。</p> : <>
        {!size.width && <p role="status">正在打开图片…</p>}
        <img src={media.url} alt={media.filename} draggable={false}
          onLoad={event => setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} onError={() => setError(true)}
          style={{ width: size.width || undefined, height: size.height || undefined, visibility: ready ? 'visible' : 'hidden', transform: `translate(-50%, -50%) translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}/>
      </>}
    </div>
    <p className="image-zoom-hint">滚轮或 Ctrl＋滚轮缩放 · 放大后拖动查看 · Esc 关闭</p>
  </>
}

export default function ImageViewer({ media, index, initialZoom = 1, onChange, onClose }: {
  media: Media[]; index: number; initialZoom?: number; onChange: (index: number) => void; onClose: () => void
}) {
  return <Modal title={`图片 ${index + 1} / ${media.length}`} onClose={onClose} className="lightbox image-viewer">
    <ImageSurface key={media[index].id} media={media[index]} initialZoom={initialZoom}/>
    {media.length > 1 && <div className="lightbox-controls">
      <button type="button" className="button secondary" disabled={index === 0} onClick={() => onChange(index - 1)}><ArrowLeft size={16}/>上一张</button>
      <button type="button" className="button secondary" disabled={index === media.length - 1} onClick={() => onChange(index + 1)}>下一张<ArrowRight size={16}/></button>
    </div>}
  </Modal>
}
