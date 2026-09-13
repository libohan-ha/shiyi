import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { Check, Crop, RotateCcw, RotateCw, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Media } from '../types'
import { Modal, Spinner } from './ui'

type Rect = { x: number; y: number; width: number; height: number }
type Point = { x: number; y: number }
type Handle = 'nw' | 'ne' | 'sw' | 'se'
type Gesture = { start: Point; initial: Rect; mode: 'draw' | 'move' | Handle }
const fullImage: Rect = { x: 0, y: 0, width: 1, height: 1 }
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value))

export default function ImageEditor({ media, onApply, onCancel }: {
  media: Media; onApply: (file: File) => Promise<void>; onCancel: () => void
}) {
  const source = useRef<HTMLImageElement | null>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const gesture = useRef<Gesture | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [turns, setTurns] = useState(0)
  const [crop, setCrop] = useState<Rect>(fullImage)
  const [drawing, setDrawing] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const rotated = turns % 2 ? { width: size.height, height: size.width } : size
  const minWidth = rotated.width ? Math.min(1, 16 / rotated.width) : .01
  const minHeight = rotated.height ? Math.min(1, 16 / rotated.height) : .01

  useEffect(() => {
    const image = new Image()
    image.onload = () => { source.current = image; setSize({ width: image.naturalWidth, height: image.naturalHeight }) }
    image.onerror = () => setError(true)
    image.src = media.url
    return () => { image.onload = null; image.onerror = null; source.current = null }
  }, [media.url])

  useEffect(() => {
    const element = canvas.current
    if (!element || !source.current || !size.width) return
    const scale = Math.min(1, 1400 / Math.max(rotated.width, rotated.height))
    element.width = Math.round(rotated.width * scale)
    element.height = Math.round(rotated.height * scale)
    const context = element.getContext('2d')!
    context.translate(element.width / 2, element.height / 2)
    context.rotate(turns * Math.PI / 2)
    context.drawImage(source.current, -size.width * scale / 2, -size.height * scale / 2, size.width * scale, size.height * scale)
  }, [size, rotated.width, rotated.height, turns])

  const point = (event: PointerEvent<HTMLDivElement>): Point => {
    const bounds = stage.current!.getBoundingClientRect()
    return { x: clamp((event.clientX - bounds.left) / bounds.width, 0, 1), y: clamp((event.clientY - bounds.top) / bounds.height, 0, 1) }
  }
  const begin = (event: PointerEvent<HTMLDivElement>) => {
    if (busy || !size.width || event.button !== 0 || !event.isPrimary) return
    event.preventDefault()
    const handle = (event.target as HTMLElement).closest<HTMLElement>('[data-handle]')?.dataset.handle as Handle | undefined
    const inside = (event.target as HTMLElement).closest('.crop-selection')
    gesture.current = { start: point(event), initial: crop, mode: handle ?? (!drawing && inside ? 'move' : 'draw') }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const drag = gesture.current
    if (!drag) return
    const next = point(event)
    if (drag.mode === 'move') {
      setCrop({ ...drag.initial, x: clamp(drag.initial.x + next.x - drag.start.x, 0, 1 - drag.initial.width),
        y: clamp(drag.initial.y + next.y - drag.start.y, 0, 1 - drag.initial.height) })
      return
    }
    const anchor = drag.mode === 'draw' ? drag.start : {
      x: drag.mode.endsWith('w') ? drag.initial.x + drag.initial.width : drag.initial.x,
      y: drag.mode.startsWith('n') ? drag.initial.y + drag.initial.height : drag.initial.y,
    }
    if (Math.abs(next.x - anchor.x) < minWidth || Math.abs(next.y - anchor.y) < minHeight) return
    setCrop({ x: Math.min(anchor.x, next.x), y: Math.min(anchor.y, next.y), width: Math.abs(next.x - anchor.x), height: Math.abs(next.y - anchor.y) })
  }
  const end = () => { gesture.current = null; setDrawing(false) }
  const rotate = (clockwise: boolean) => {
    setTurns(value => (value + (clockwise ? 1 : 3)) % 4)
    setCrop(rect => clockwise ? { x: 1 - rect.y - rect.height, y: rect.x, width: rect.height, height: rect.width }
      : { x: rect.y, y: 1 - rect.x - rect.width, width: rect.height, height: rect.width })
  }
  const inset = (side: 'left' | 'right' | 'top' | 'bottom', value: number) => {
    if (!Number.isFinite(value)) return
    setCrop(rect => {
      if (side === 'left') { const x = clamp(value / 100, 0, rect.x + rect.width - minWidth); return { ...rect, x, width: rect.width + rect.x - x } }
      if (side === 'right') return { ...rect, width: clamp(1 - value / 100 - rect.x, minWidth, 1 - rect.x) }
      if (side === 'top') { const y = clamp(value / 100, 0, rect.y + rect.height - minHeight); return { ...rect, y, height: rect.height + rect.y - y } }
      return { ...rect, height: clamp(1 - value / 100 - rect.y, minHeight, 1 - rect.y) }
    })
  }
  const apply = async () => {
    if (busy || !source.current) return
    setBusy(true)
    try {
      const left = Math.round(crop.x * rotated.width), top = Math.round(crop.y * rotated.height)
      const width = Math.max(1, Math.round((crop.x + crop.width) * rotated.width) - left)
      const height = Math.max(1, Math.round((crop.y + crop.height) * rotated.height) - top)
      // Keep canvas export within mobile browser limits, including very large photos.
      const scale = Math.min(1, 4096 / Math.max(width, height))
      const output = document.createElement('canvas')
      output.width = Math.max(1, Math.round(width * scale)); output.height = Math.max(1, Math.round(height * scale))
      const context = output.getContext('2d')
      if (!context) throw new Error('图片处理未完成，请重试或换一张图片')
      context.scale(scale, scale)
      context.translate(rotated.width / 2 - left, rotated.height / 2 - top)
      context.rotate(turns * Math.PI / 2)
      context.drawImage(source.current, -size.width / 2, -size.height / 2)
      const blob = await new Promise<Blob>((resolve, reject) => output.toBlob(value => value ? resolve(value) : reject(new Error('图片导出失败，请重试')), 'image/webp', .96))
      if (blob.size > 15 * 1024 * 1024) throw new Error('处理后的图片超过 15 MB，请缩小裁剪范围')
      const filename = `${media.filename.replace(/\.[^.]+$/, '')}-edited.${blob.type === 'image/webp' ? 'webp' : 'png'}`
      await onApply(new File([blob], filename, { type: blob.type }))
    } catch (failure) { toast.error((failure as Error).message) }
    finally { setBusy(false) }
  }
  const percent = (value: number) => Math.max(0, Math.round(value * 1000) / 10)
  return <Modal title="裁剪与旋转图片" className="image-editor-modal" onClose={() => { if (!busy) onCancel() }}>
    <div className="modal-body image-editor-body">
      <div className="image-editor-toolbar">
        <button className={`button secondary small ${drawing ? 'selected' : ''}`} aria-pressed={drawing} disabled={busy || !size.width} onClick={() => setDrawing(true)}><Crop size={16}/>框选范围</button>
        <button className="button secondary small" disabled={busy || !size.width} onClick={() => rotate(false)} aria-label="向左旋转 90 度"><RotateCcw size={16}/>左转</button>
        <button className="button secondary small" disabled={busy || !size.width} onClick={() => rotate(true)} aria-label="向右旋转 90 度"><RotateCw size={16}/>右转</button>
        <button className="text-button" disabled={busy} onClick={() => { setTurns(0); setCrop(fullImage); setDrawing(true) }}><Undo2 size={15}/>重置</button>
      </div>
      <p className="field-help">拖动框选要保留的内容；拖动选区可移动，拖动四角可调整大小。</p>
      {error ? <p role="alert">图片加载失败，请关闭后重新打开。</p> : !size.width ? <div className="loading-state"><Spinner/>正在打开图片…</div> : <div className="crop-workspace">
        <div className={`crop-stage ${drawing ? 'is-drawing' : ''}`} ref={stage} style={{ aspectRatio: `${rotated.width} / ${rotated.height}`, width: `min(100%, ${Math.round(rotated.width / rotated.height * 420)}px)` }}
          onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={() => { if (gesture.current) setCrop(gesture.current.initial); end() }} onLostPointerCapture={end}>
          <canvas ref={canvas} aria-label="待裁剪的图片"/>
          <div className="crop-selection" style={{ left: `${crop.x * 100}%`, top: `${crop.y * 100}%`, width: `${crop.width * 100}%`, height: `${crop.height * 100}%` }}>
            <div className="crop-grid"/>
            {(['nw', 'ne', 'sw', 'se'] as const).map(handle => <span key={handle} data-handle={handle} className={`crop-handle ${handle}`} aria-hidden="true"/>)}
          </div>
        </div>
      </div>}
      {!!size.width && <><div className="crop-dimensions" aria-live="polite">保留约 {Math.round(rotated.width * crop.width)} × {Math.round(rotated.height * crop.height)} 像素</div>
        <details className="crop-precision"><summary>精确调整裁剪范围</summary><fieldset disabled={busy} className="crop-insets">
          {([{ side: 'left', label: '左侧裁去', value: crop.x }, { side: 'top', label: '顶部裁去', value: crop.y },
            { side: 'right', label: '右侧裁去', value: 1 - crop.x - crop.width }, { side: 'bottom', label: '底部裁去', value: 1 - crop.y - crop.height }] as const).map(({ side, label, value }) =>
            <label key={side} className="field">{label}（%）<input type="number" min={0} max={99.9} step={.1} value={percent(value)} onChange={event => inset(side, Number(event.target.value))}/></label>)}
        </fieldset></details></>}
    </div>
    <div className="modal-footer"><span className="save-note">应用后仍需保存题目；取消可保留原图。</span><div><button className="button secondary" disabled={busy} onClick={onCancel}>取消</button><button className="button primary" disabled={busy || !size.width || error} onClick={() => void apply()}>{busy ? <Spinner/> : <Check size={16}/>} {busy ? '正在处理…' : '应用修改'}</button></div></div>
  </Modal>
}
