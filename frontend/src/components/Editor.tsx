import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, Crop, ImagePlus, Plus, Save, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, patch, post, refreshLearning } from '../api'
import { subjects } from '../lib'
import type { Chapter, Item, Media, Subject } from '../types'
import { Content, Modal, Spinner } from './ui'
import ImageEditor from './ImageEditor'

type EditorOptions = { item?: Item; subject?: Subject; mistake?: boolean; onClosed?: () => void }
const EditorContext = createContext<(options?: EditorOptions) => void>(() => {})
export const useEditor = () => useContext(EditorContext)

type EntryDefaults = { subject?: Subject; chapters: Partial<Record<Subject, string>> }
function readEntryDefaults(key: string): EntryDefaults {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? '{}')
    const chapters: EntryDefaults['chapters'] = {}
    for (const subject of subjects) if (typeof saved.chapters?.[subject.id] === 'string') chapters[subject.id] = saved.chapters[subject.id]
    return { subject: subjects.find(subject => subject.id === saved.subject)?.id, chapters }
  } catch { return { chapters: {} } }
}

export function EditorProvider({ children, userId }: { children: ReactNode; userId: string }) {
  const [options, setOptions] = useState<EditorOptions | null>(null)
  return <EditorContext.Provider value={(options = {}) => setOptions(options)}>{children}{options && <Editor key={options.item?.id ?? 'new'} options={options} userId={userId} onClose={() => { const onClosed = options.onClosed; setOptions(null); onClosed?.() }}/>}</EditorContext.Provider>
}

export function ContentField({ label, text, media, onText, onMedia, placeholder, rows = 5, maxFiles = 12, maxLength = 60000, disabled = false, onUploadingChange }: {
  label: string; text: string; media: Media[]; onText: (value: string) => void; onMedia: (value: Media[]) => void; placeholder: string; rows?: number
  maxFiles?: number; maxLength?: number; disabled?: boolean; onUploadingChange?: (value: boolean) => void
}) {
  const fieldId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const uploadLock = useRef(false)
  const currentMedia = useRef(media)
  const updateMedia = useRef(onMedia)
  currentMedia.current = media
  updateMedia.current = onMedia
  const [uploading, setUploading] = useState(false)
  const [drag, setDrag] = useState(false)
  const [preview, setPreview] = useState(false)
  const [editingImage, setEditingImage] = useState<Media | null>(null)
  const processing = uploading || !!editingImage
  const closeImageEditor = () => { setEditingImage(null); uploadLock.current = false; onUploadingChange?.(false) }
  const upload = async (files: File[]) => {
    if (disabled || uploadLock.current || !files.length) return
    if (files.length + currentMedia.current.length > maxFiles) { toast.error(`每个区域最多放 ${maxFiles} 张图片`); return }
    uploadLock.current = true
    setUploading(true)
    onUploadingChange?.(true)
    const added: Media[] = []
    try {
      for (const file of files) {
        if (file.size > 15 * 1024 * 1024) throw new Error('单张图片不能超过 15 MB')
        const body = new FormData(); body.append('file', file)
        added.push(await api<Media>('/media', { method: 'POST', body }))
      }
      toast.success(`已上传 ${added.length} 张图片`)
    } catch (error) { toast.error((error as Error).message) }
    finally {
      if (added.length) updateMedia.current([...currentMedia.current, ...added])
      uploadLock.current = false
      setUploading(false)
      onUploadingChange?.(false)
    }
  }
  return <div className={`content-field ${drag ? 'drag-active' : ''}`} onPaste={e => {
    const images = Array.from(e.clipboardData.files).filter(f => f.type.startsWith('image/'))
    if (images.length) { e.preventDefault(); void upload(images) }
  }} onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDrag(false) }} onDrop={e => { e.preventDefault(); setDrag(false); void upload(Array.from(e.dataTransfer.files)) }}>
    <div className="field-heading"><label htmlFor={fieldId}>{label}</label><button type="button" className="text-button" disabled={disabled} onClick={() => setPreview(!preview)}>{preview ? '继续编辑' : '预览排版'}</button></div>
    {preview ? <div className="editor-preview"><Content text={text} media={media}/>{!text && !media.length && <span className="muted">输入内容后，在这里查看排版效果</span>}</div> : <textarea id={fieldId} aria-label={label} disabled={disabled} maxLength={maxLength} value={text} onChange={e => onText(e.target.value)} placeholder={placeholder} rows={rows}/>}
    {!preview && media.length > 0 && <div className="attachment-strip">{media.map((m, i) => <div className="attachment" key={m.id}><img src={m.url} alt={`${label}图片 ${i + 1}`}/><div className="attachment-actions"><button type="button" disabled={disabled || processing} aria-label={`编辑${label}图片 ${i + 1}`} title="裁剪与旋转" onClick={() => { uploadLock.current = true; onUploadingChange?.(true); setEditingImage(m) }}><Crop size={15}/></button><button type="button" disabled={disabled || processing || i === 0} aria-label="图片向前移动" onClick={() => { const copy = [...media]; [copy[i], copy[i - 1]] = [copy[i - 1], copy[i]]; onMedia(copy) }}><ArrowLeft size={14}/></button><button type="button" disabled={disabled || processing} aria-label="移除图片" onClick={() => onMedia(media.filter(x => x.id !== m.id))}><X size={15}/></button></div><span>{i + 1}</span></div>)}</div>}
    <div className="upload-strip" tabIndex={0} aria-label={`粘贴${label}图片`}><button type="button" className="text-button" disabled={disabled || processing} onClick={() => inputRef.current?.click()}>{uploading ? <Spinner/> : <ImagePlus size={16}/>} {uploading ? '正在上传…' : '添加图片'}</button><span>支持粘贴、拖拽 · 可裁剪与旋转</span><input ref={inputRef} type="file" disabled={disabled || processing} aria-label={`${label}附件`} accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden onChange={e => { void upload(Array.from(e.target.files ?? [])); e.target.value = '' }}/></div>
    {editingImage && <ImageEditor media={editingImage} onCancel={closeImageEditor} onApply={async file => {
      setUploading(true)
      try {
        const body = new FormData(); body.append('file', file)
        const replacement = await api<Media>('/media', { method: 'POST', body })
        updateMedia.current(currentMedia.current.map(value => value.id === editingImage.id ? replacement : value))
        closeImageEditor(); toast.success('图片已更新，保存后生效')
      } finally { setUploading(false) }
    }} />}
  </div>
}

function Editor({ options, userId, onClose }: { options: EditorOptions; userId: string; onClose: () => void }) {
  const old = options.item
  const storageKey = `shiyi-draft-${userId}`
  const defaultsKey = `shiyi-entry-defaults-${userId}`
  const [entryDefaults, setEntryDefaults] = useState(() => readEntryDefaults(defaultsKey))
  const initialSubject = old?.subject ?? options.subject ?? entryDefaults.subject ?? '408'
  const defaultForm = { title: old?.title ?? '', subject: initialSubject, chapter_id: old ? old.chapter_id ?? '' : entryDefaults.chapters[initialSubject] ?? '',
    kind: old?.kind ?? (options.mistake ? 'problem' : initialSubject === 'english' ? 'vocabulary' : 'concept'), question: old?.question ?? '', answer: old?.answer ?? '',
    difficulty: old?.difficulty ?? 'medium', tags: old?.tags.join('，') ?? '', source: old?.source ?? '',
    is_mistake: old?.is_mistake ?? options.mistake ?? false, mistake_reason: old?.mistake_reason ?? '', takeaway: old?.takeaway ?? '',
    question_media: old?.question_media ?? [] as Media[], answer_media: old?.answer_media ?? [] as Media[] }
  const [form, setForm] = useState(defaultForm)
  const [baseline, setBaseline] = useState(defaultForm)
  const [entryNumber, setEntryNumber] = useState(0)
  const titleRef = useRef<HTMLInputElement>(null)
  const saveLock = useRef(false)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState({ question: false, answer: false })
  const hasUpload = uploading.question || uploading.answer
  const [draftState, setDraftState] = useState<'pending' | 'saved' | 'unavailable'>('pending')
  const [tab, setTab] = useState('content')
  const [savedDraft, setSavedDraft] = useState<string | null>(() => { try { return !old ? localStorage.getItem(storageKey) : null } catch { return null } })
  const [newChapter, setNewChapter] = useState('')
  const [chapterOpen, setChapterOpen] = useState(false)
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline)
  const chapters = useQuery({ queryKey: ['chapters'], queryFn: () => api<Chapter[]>('/chapters') })
  const update = <K extends keyof typeof form>(key: K, value: typeof form[K]) => setForm(f => ({ ...f, [key]: value }))
  useEffect(() => {
    if (old || !dirty || busy) return
    setDraftState('pending')
    const timer = setTimeout(() => {
      try { localStorage.setItem(storageKey, JSON.stringify(form)); setDraftState('saved') }
      catch { setDraftState('unavailable') }
    }, 600)
    return () => clearTimeout(timer)
  }, [form, old, storageKey, dirty, busy])
  useEffect(() => {
    if (chapters.data && form.chapter_id && !chapters.data.some(chapter => chapter.id === form.chapter_id && chapter.subject === form.subject)) {
      setForm(value => ({ ...value, chapter_id: '' }))
      setBaseline(value => ({ ...value, chapter_id: '' }))
    }
  }, [chapters.data, form.chapter_id, form.subject])
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (hasUpload || (old && dirty)) { event.preventDefault(); return }
      if (!old && dirty) {
        try { localStorage.setItem(storageKey, JSON.stringify(form)) }
        catch { event.preventDefault() }
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [form, old, dirty, hasUpload, storageKey])
  const close = () => {
    if (busy || hasUpload) return
    if (dirty && old && !window.confirm('修改还未保存，确定关闭吗？')) return
    if (dirty && !old) {
      try { localStorage.setItem(storageKey, JSON.stringify(form)) }
      catch { if (!window.confirm('浏览器无法暂存内容。关闭会丢失未保存的输入，确定关闭吗？')) return }
    }
    onClose()
  }
  const save = async (status: string, continueEntry = false) => {
    if (saveLock.current || hasUpload) return
    if (!form.title.trim()) { toast.error('给这条知识起一个标题吧'); return }
    saveLock.current = true; setBusy(true)
    try {
      const payload = { ...form, chapter_id: form.chapter_id || null, tags: form.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean),
        question_media: form.question_media.map(m => m.id), answer_media: form.answer_media.map(m => m.id), status,
        ...(old ? { expected_version: old.version } : {}) }
      if (old) await patch(`/items/${old.id}`, payload)
      else await post('/items', payload)
      if (!old) {
        const nextDefaults = { subject: form.subject, chapters: { ...entryDefaults.chapters, [form.subject]: form.chapter_id } }
        setEntryDefaults(nextDefaults)
        try { localStorage.removeItem(storageKey); localStorage.setItem(defaultsKey, JSON.stringify(nextDefaults)) } catch { /* The knowledge was saved successfully. */ }
      }
      refreshLearning(); toast.success(status === 'draft' ? '已保存草稿，随时回来补充' : old ? '修改已保存，复习进度已保留' : '新的知识已收入，等待与你再次相遇')
      if (continueEntry && !old) {
        const next = { ...form, title: '', question: '', answer: '', question_media: [], answer_media: [], tags: '', source: '', mistake_reason: '', takeaway: '' }
        setForm(next); setBaseline(next); setSavedDraft(null); setDraftState('pending'); setTab('content')
        setChapterOpen(false); setNewChapter(''); setEntryNumber(value => value + 1)
        requestAnimationFrame(() => { titleRef.current?.focus(); titleRef.current?.closest('.modal-body')?.scrollTo({ top: 0 }) })
      } else onClose()
    } catch (error) { toast.error((error as Error).message) } finally { saveLock.current = false; setBusy(false) }
  }
  return <Modal title={old ? '编辑这条记忆' : form.is_mistake ? '收录一道错题' : '种下一颗知识的种子'} onClose={close} className="editor-modal">
    <div className="editor-top"><span className="eyebrow">{old ? 'REFINE YOUR KNOWLEDGE' : 'A SMALL STEP, A LASTING MEMORY'}</span><div className="tabs"><button disabled={busy || hasUpload} className={tab === 'content' ? 'active' : ''} onClick={() => setTab('content')}>题目与答案</button><button disabled={busy || hasUpload} className={tab === 'notes' ? 'active' : ''} onClick={() => setTab('notes')}>复盘与标记</button></div></div>
    <div className="modal-body editor-body"><fieldset className="editor-fields" disabled={busy}>
      {savedDraft && <div className="draft-banner"><span>上次还有一条未完成的记录</span><button className="text-button" onClick={() => { try { setForm(JSON.parse(savedDraft)); setSavedDraft(null); toast.success('已恢复上次内容') } catch { setSavedDraft(null) } }}>恢复内容</button><button className="icon-button" aria-label="忽略上次草稿" onClick={() => { setSavedDraft(null); localStorage.removeItem(storageKey) }}><X size={15}/></button></div>}
      {tab === 'content' ? <>
        <div className="subject-picker">{subjects.map(s => <button key={s.id} className={`subject-choice ${s.color} ${form.subject === s.id ? 'selected' : ''}`} onClick={() => setForm(f => ({ ...f, subject: s.id, chapter_id: entryDefaults.chapters[s.id] ?? '', kind: s.id === 'english' && !f.is_mistake ? 'vocabulary' : f.kind === 'vocabulary' ? 'concept' : f.kind }))}><span aria-hidden="true">{s.symbol}</span>{s.name}{form.subject === s.id && <Check size={15}/>}</button>)}</div>
        <label className="field">标题 <span className="required">*</span><input ref={titleRef} autoFocus value={form.title} maxLength={240} onChange={e => update('title', e.target.value)} placeholder="例如：Cache 映射方式与地址划分"/></label>
        <div className="form-row"><label className="field">章节<select value={form.chapter_id} onChange={e => update('chapter_id', e.target.value)}><option value="">暂不分类</option>{chapters.data?.filter(c => c.subject === form.subject).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label className="field">内容类型<select value={form.kind} onChange={e => update('kind', e.target.value)}><option value="concept">知识点</option><option value="problem">练习题</option><option value="vocabulary">单词</option><option value="expression">表达</option></select></label><button className="icon-button add-chapter" aria-label="新增章节" onClick={() => setChapterOpen(!chapterOpen)}><Plus size={18}/></button></div>
        {chapterOpen && <div className="inline-create"><input value={newChapter} aria-label="新章节名称" placeholder="新章节名称" onChange={e => setNewChapter(e.target.value)}/><button className="button secondary small" disabled={!newChapter.trim()} onClick={async () => { try { const c = await post<Chapter>('/chapters', { subject: form.subject, name: newChapter }); await chapters.refetch(); update('chapter_id', c.id); setChapterOpen(false); setNewChapter('') } catch (e) { toast.error((e as Error).message) } }}>添加</button></div>}
        <ContentField key={`question-${entryNumber}`} label="问题 / 题干" disabled={busy} onUploadingChange={v => setUploading(u => ({ ...u, question: v }))} text={form.question} media={form.question_media} onText={v => update('question', v)} onMedia={v => update('question_media', v)} placeholder="下一次复习，你希望自己回答什么？也可以直接粘贴题目截图。"/>
        <ContentField key={`answer-${entryNumber}`} label="答案 / 解析" disabled={busy} onUploadingChange={v => setUploading(u => ({ ...u, answer: v }))} text={form.answer} media={form.answer_media} onText={v => update('answer', v)} onMedia={v => update('answer_media', v)} placeholder="写下参考答案、关键步骤或判定标准。支持 Markdown 和 $LaTeX$ 公式。"/>
      </> : <>
        <div className="field"><label>题目本身的难度</label><div className="segmented difficulty-select">{[['basic', '基础'], ['medium', '中等'], ['hard', '较难']].map(([id, label]) => <button key={id} className={form.difficulty === id ? 'active' : ''} onClick={() => update('difficulty', id)}>{label}</button>)}</div><p className="field-help">用于整理和筛选。复习时的表现会单独记录。</p></div>
        <label className="switch-row"><span><strong>加入错题本</strong><small>为这道题保留错因与反思</small></span><input type="checkbox" role="switch" checked={form.is_mistake} onChange={e => update('is_mistake', e.target.checked)}/></label>
        {form.is_mistake && <><label className="field">这次为什么出错？<textarea rows={4} value={form.mistake_reason} onChange={e => update('mistake_reason', e.target.value)} placeholder="是概念混淆、条件遗漏，还是某一步没想清楚？"/></label><label className="field">留给下次自己的提醒<textarea rows={3} value={form.takeaway} onChange={e => update('takeaway', e.target.value)} placeholder="用一句话写下真正值得记住的东西"/></label></>}
        <label className="field">标签<input value={form.tags} onChange={e => update('tags', e.target.value)} placeholder="例如：高频考点，易混淆，2025真题"/><span className="field-help">用逗号分隔，最多 20 个</span></label>
        <label className="field">来源<input value={form.source} onChange={e => update('source', e.target.value)} placeholder="书名 / 页码 / 真题年份 / 链接"/></label>
      </>}
    </fieldset></div>
    <div className="modal-footer entry-footer"><span className="save-note" role="status"><Save size={14}/>{hasUpload ? '图片处理中，请稍候…' : old ? '保存后保留已有复习进度' : dirty ? draftState === 'saved' ? '输入内容已在本机暂存' : draftState === 'unavailable' ? '请及时保存为草稿' : '正在本机暂存…' : entryNumber ? `本次已连续收录 ${entryNumber} 条，可继续填写` : '科目与章节会在保存后记住'}</span><div><button className="button secondary" disabled={busy || hasUpload} onClick={() => void save('draft')}>存为草稿</button>{!old && <button className="button secondary continue-entry" disabled={busy || hasUpload} onClick={() => void save('active', true)}>保存并录下一题<ArrowRight size={16}/></button>}<button className="button primary" disabled={busy || hasUpload} onClick={() => void save(old?.status === 'suspended' ? 'suspended' : 'active')}>{busy ? <Spinner/> : old ? <Check size={16}/> : <Plus size={16}/>} {old ? '保存修改' : '收进知识库'}</button></div></div>
  </Modal>
}
