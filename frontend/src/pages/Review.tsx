import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, ChevronDown, Eye, Leaf, Pause, Pencil, RotateCcw, SkipForward, Sprout, Trash2, X } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, post, refreshLearning } from '../api'
import { createRequestId, dateLabel, intervalLabel, percent, stepLines, subjectName, subjects } from '../lib'
import type { Item, Media, Preview, Queue, Rating, Review, Step, Throughput } from '../types'
import { ContentField, useEditor } from '../components/Editor'
import { Content, ErrorState, Loading, Spinner } from '../components/ui'
import '../review-feedback.css'

export default function ReviewPage() {
  const [params] = useSearchParams()
  return <ReviewSession key={params.toString()}/>
}

function ReviewSession() {
  const [params, setParams] = useSearchParams()
  const subject = params.get('subject') ?? ''
  const singleId = params.get('item')
  const [completed, setCompleted] = useState<Review[]>([])
  const [skipped, setSkipped] = useState<string[]>([])
  const [paused, setPaused] = useState(false)
  const [transition, setTransition] = useState(false)
  const [undoBusy, setUndoBusy] = useState(false)
  const [pinned, setPinned] = useState<Item | null>(null)
  const [working, setWorking] = useState(false)
  const [handled, setHandled] = useState<string[]>([])
  const edit = useEditor()
  const navigate = useNavigate()
  const queue = useQuery({ queryKey: ['queue', subject || 'all'], queryFn: () => api<Queue>(`/reviews/due${subject ? `?subject=${subject}` : ''}`), refetchInterval: 30000, enabled: !singleId })
  const single = useQuery({ queryKey: ['item', singleId], queryFn: () => api<Item>(`/items/${singleId}`), enabled: !!singleId })
  const candidate = singleId ? completed.length ? undefined : single.data : queue.data?.items.find(i => !skipped.includes(i.id) && !handled.includes(i.id + ':' + i.schedule.version))
  const current = pinned ?? candidate
  useEffect(() => { if (!pinned && candidate && !transition && !undoBusy) setPinned(candidate) }, [pinned, candidate, transition, undoBusy])
  const remaining = singleId ? current ? 1 : 0 : (queue.data?.due_count ?? 0) + (queue.data?.new_available ?? 0)
  const progress = completed.length ? completed.length / (completed.length + remaining) : 0
  const lastBlocker = [...completed].reverse().find(review => review.independent_completed === false && review.blocker)
  const onRated = async (review: Review) => {
    setTransition(true)
    setCompleted(history => [...history, review])
    if (current) setHandled(versions => [...versions, current.id + ':' + current.schedule.version])
    refreshLearning()
    if (!singleId) await queue.refetch()
    setPinned(null)
    setTransition(false)
  }
  const undo = async () => {
    const previous = completed[completed.length - 1]
    if (!previous || undoBusy || working) return
    setUndoBusy(true)
    try { await post(`/reviews/${previous.id}/undo`); setCompleted(c => c.slice(0, -1)); setSkipped([]); refreshLearning(); await Promise.all([queue.refetch(), singleId ? single.refetch() : Promise.resolve()]); setPinned(null); setHandled([]); setPaused(false); toast.success('已撤销上次评分，记忆状态已恢复') }
    catch (e) { toast.error((e as Error).message) } finally { setUndoBusy(false) }
  }
  const editCurrent = async () => {
    const item = current
    if (!item || working || undoBusy || transition) return
    try {
      // The review queue omits the answer, so load the full item before editing.
      const full = await api<Item>(`/items/${item.id}`)
      edit({ item: full, onClosed: async () => {
        // Saving bumps item.version, so refresh the pinned card to keep the
        // content and the optimistic-lock version in sync.
        try { setPinned(await api<Item>(`/items/${item.id}`)) }
        catch { setPinned(null) }
        if (!singleId) await queue.refetch()
      }})
    } catch (e) { toast.error((e as Error).message) }
  }
  const deleteCurrent = async () => {
    const item = current
    if (!item || working || undoBusy || transition) return
    if (!window.confirm('将这条内容移入回收站？学习记录会保留。')) return
    try {
      await api(`/items/${item.id}`, { method: 'DELETE' })
      setHandled(versions => [...versions, item.id + ':' + item.schedule.version])
      setPinned(null)
      refreshLearning()
      if (singleId) navigate('/')
      else await queue.refetch()
      toast.success('已移入回收站')
    } catch (e) { toast.error((e as Error).message) }
  }
  return <div className="review-page page-enter"><div className="review-top"><Link to="/" className="back-link"><ArrowLeft size={16}/>回到今日</Link><span className="eyebrow">ONE MEMORY AT A TIME</span><div className="review-scope"><select aria-label="复习科目" value={subject} disabled={!!singleId || working || undoBusy || transition} onChange={e => { setParams(e.target.value ? { subject: e.target.value } : {}); setSkipped([]); setCompleted([]) }}><option value="">全部科目</option>{subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select><ChevronDown size={14}/></div></div>
    <div className="session-progress"><div><span style={{ width: `${progress * 100}%` }}/></div><span>本次已完成 <b>{completed.length}</b> 条{remaining > 0 && ` · 还有 ${remaining} 条`}</span></div>
    {(singleId ? single.isPending : queue.isPending) || transition || undoBusy ? <Loading text="正在翻开下一条记忆…"/> : (singleId ? single.error : queue.error) ? <ErrorState error={singleId ? single.error : queue.error} retry={() => void (singleId ? single.refetch() : queue.refetch())}/> : current ? <><div hidden={paused}><ReviewCard key={`${current.id}-${current.version}-${current.schedule.version}`} item={current} active={!paused} onWorking={setWorking} onRated={onRated} onConflict={async () => { await (singleId ? single.refetch() : queue.refetch()); setPinned(null) }} onSkip={() => { setPinned(null); if (singleId) setParams({}); else setSkipped(ids => [...ids, current.id]) }} onEdit={() => void editCurrent()} onDelete={() => void deleteCurrent()}/></div>{paused && <div className="review-complete panel"><div className="complete-art"><Pause size={36} strokeWidth={1.5}/></div><span className="eyebrow">TAKE YOUR TIME</span><h1>休息一下，也很好。</h1><p>这次已经完成 {completed.length} 次复习。回来后，我们继续。</p><button className="button primary" onClick={() => setPaused(false)}>继续复习<ArrowRight size={17}/></button></div>}</> : <div className="review-complete panel"><div className="complete-art"><Sprout size={52} strokeWidth={1.15}/><span className="complete-spark">✦</span></div><span className="eyebrow">A LITTLE MORE ROOTED</span><h1>{completed.length ? '今天的努力，已悄悄生根。' : skipped.length ? '给难题，留一点时间。' : '此刻，一切正好。'}</h1><p>{completed.length ? `你刚刚完成了 ${completed.length} 次认真回忆。给自己一点肯定，再从容地往前。` : skipped.length ? `你暂时跳过了 ${skipped.length} 条内容。它们仍然保留在待复习列表里。` : '现在没有可以开始的复习。你可以记录新知，也可以安心休息。'}</p>{queue.data?.next_due && <div className="next-review-note"><Leaf size={17}/>下一次相遇：{dateLabel(queue.data.next_due, true)}</div>}{queue.data && queue.data.new_count > 0 && queue.data.new_available === 0 && <p className="field-help">还有 {queue.data.new_count} 条待学内容，今天的新学额度已用完。可在设置中调整。</p>}{lastBlocker && <div className="saved-blocker-note"><p>卡点已保存。等你有空，可以去详情把它提炼成一个小任务；现在安心休息也很好。</p><Link className="text-button" to={`/items/${lastBlocker.item_id}`}>查看卡点与详情<ArrowRight size={15}/></Link></div>}<div className="complete-actions"><Link to="/" className="button primary">回到今日<ArrowRight size={17}/></Link>{skipped.length > 0 && <button className="button secondary" onClick={() => setSkipped([])}>再看看跳过的内容</button>}<Link to="/library" className="button secondary">逛逛知识库</Link></div></div>}
    <div className="review-bottom"><button className="text-button" disabled={!completed.length || undoBusy || working || transition} onClick={() => void undo()}><RotateCcw size={15}/>{undoBusy ? '正在撤销…' : '撤销上次评分'}</button><span><Leaf size={14}/>如实记录，才会遇见恰好的下一次。</span>{current && <button className="text-button" disabled={working || undoBusy || transition} onClick={() => setPaused(!paused)}>{paused ? <ArrowRight size={15}/> : <Pause size={15}/>} {paused ? '继续' : '休息一下'}</button>}</div>
  </div>
}

const ratingOptions: { id: Rating; label: string; note: string; shortcut: number }[] = [
  { id: 'again', label: '忘记', note: '没有独立想起', shortcut: 1 },
  { id: 'hard', label: '困难', note: '想起了，但很费力', shortcut: 2 },
  { id: 'good', label: '良好', note: '正常回忆或完成', shortcut: 3 },
  { id: 'easy', label: '轻松', note: '迅速且轻松', shortcut: 4 },
]

function ReviewCard({ item, active, onWorking, onRated, onSkip, onConflict, onEdit, onDelete }: {
  item: Item; active: boolean; onWorking: (value: boolean) => void
  onRated: (review: Review) => Promise<void>; onSkip: () => void; onConflict: () => Promise<void>
  onEdit: () => void; onDelete: () => void
}) {
  const cardRef = useRef<HTMLElement>(null)
  const [revealed, setRevealed] = useState(false)
  useEffect(() => {
    if (!revealed || !window.matchMedia('(max-width: 700px)').matches) return
    const frame = requestAnimationFrame(() => cardRef.current?.querySelector('.revealed-answer')?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
    return () => cancelAnimationFrame(frame)
  }, [revealed])
  const [answerOpen, setAnswerOpen] = useState(false)
  const [answer, setAnswer] = useState('')
  const [independentCompleted, setIndependentCompleted] = useState<boolean | null>(null)
  const [blocker, setBlocker] = useState('')
  // 贯通率: first attempt lists steps line by line; later attempts tick off the steps that were missed.
  const [doneText, setDoneText] = useState('')
  const [missText, setMissText] = useState('')
  const [ticks, setTicks] = useState<Record<number, boolean>>({})
  const throughputQuery = useQuery({ queryKey: ['throughput', item.id], queryFn: () => api<Throughput>(`/items/${item.id}/throughput`), enabled: revealed })
  const previous = throughputQuery.data?.latest?.steps ?? null
  const steps: Step[] = previous
    ? independentCompleted === true ? [...previous.map(step => ({ text: step.text, done: true })), ...stepLines(doneText).map(text => ({ text, done: true }))]
      : [...previous.map((step, index) => ({ text: step.text, done: ticks[index] ?? step.done })), ...stepLines(missText).map(text => ({ text, done: false }))]
    : independentCompleted === true ? stepLines(doneText).map(text => ({ text, done: true }))
      : independentCompleted === false ? [...stepLines(doneText).map(text => ({ text, done: true })), ...stepLines(missText).map(text => ({ text, done: false }))] : []
  const stepsValid = steps.length <= 30
  const missedSteps = steps.filter(step => !step.done).length
  const rate = steps.length ? (steps.length - missedSteps) / steps.length : null
  // Every card kind records whether it was completed independently.
  const isProblem = true
  const feedbackAllows = useCallback((rating: Rating) => !isProblem || (stepsValid && (independentCompleted === true
    ? rating !== 'again'
    : independentCompleted === false && rating === 'again' && (!!blocker.trim() || missedSteps > 0) && blocker.length <= 2000)), [isProblem, independentCompleted, blocker, missedSteps, stepsValid])
  const [media, setMedia] = useState<Media[]>([])
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [conflict, setConflict] = useState(false)
  useEffect(() => { onWorking(busy || uploading || retry); return () => onWorking(false) }, [busy, uploading, retry, onWorking])
  const busyRef = useRef(false)
  const pending = useRef<Record<string, unknown> | null>(null)
  const activeTime = useRef({ accumulated: 0, since: 0 })
  const detail = useQuery({ queryKey: ['item', item.id], queryFn: () => api<Item>(`/items/${item.id}`), enabled: revealed })
  const preview = useQuery({ queryKey: ['preview', item.id, item.schedule.version], queryFn: () => api<Preview>(`/items/${item.id}/preview`), enabled: revealed })
  useEffect(() => {
    const pauseTimer = () => {
      const value = activeTime.current
      if (value.since) { value.accumulated += performance.now() - value.since; value.since = 0 }
    }
    const visibility = () => {
      pauseTimer()
      if (active && !document.hidden) activeTime.current.since = performance.now()
    }
    visibility()
    document.addEventListener('visibilitychange', visibility)
    return () => { pauseTimer(); document.removeEventListener('visibilitychange', visibility) }
  }, [active])
  const submit = useCallback(async (rating: Rating) => {
    if (busyRef.current || uploading || !active || conflict || !revealed || !detail.data || !preview.data || !feedbackAllows(rating)) return
    busyRef.current = true; setBusy(true)
    const time = activeTime.current
    const duration = Math.round(Math.min(86400000, time.accumulated + (time.since ? performance.now() - time.since : 0)))
    const payload = pending.current ?? { request_id: createRequestId(), rating, expected_version: item.schedule.version, expected_item_version: item.version,
      duration_ms: duration, answer_text: answer, answer_media: media.map(m => m.id),
      ...(isProblem ? { independent_completed: independentCompleted, blocker: independentCompleted === false ? blocker.trim() : '', steps } : {}) }
    pending.current = payload
    try { const response = await post<{ review: Review }>(`/items/${item.id}/reviews`, payload); pending.current = null; setRetry(false); await onRated(response.review) }
    catch (e) { const uncertain = e instanceof ApiError && (e.status === 0 || e.status >= 500); setRetry(uncertain); if (!uncertain) pending.current = null; if (e instanceof ApiError && e.status === 409) { setConflict(true); refreshLearning() } toast.error((e as Error).message) }
    finally { busyRef.current = false; setBusy(false) }
  }, [revealed, detail.data, preview.data, item, answer, media, onRated, uploading, active, conflict, feedbackAllows, isProblem, independentCompleted, blocker, steps])
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (!active || e.ctrlKey || e.metaKey || e.altKey || document.querySelector('dialog[open]') || (e.target as HTMLElement).closest('input,textarea,select,button,a,[contenteditable],dialog')) return
      if (e.code === 'Space' && !revealed) { e.preventDefault(); setRevealed(true) }
      const option = ratingOptions.find(r => String(r.shortcut) === e.key)
      if (option && revealed && !retry) { e.preventDefault(); void submit(option.id) }
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [revealed, submit, retry, active])
  return <section ref={cardRef} className="review-card panel"><div className="review-card-meta"><div><span className={`subject-badge ${subjects.find(s => s.id === item.subject)?.color}`}>{subjectName(item.subject)}</span>{item.is_mistake && <span className="mistake-badge">错题重做</span>}{item.schedule.state === 'new' && <span className="new-badge">初次学习</span>}</div><div className="review-card-tools"><button className="icon-button" title="编辑这条内容" aria-label="编辑这条内容" disabled={busy || retry || uploading} onClick={onEdit}><Pencil size={15}/></button><button className="icon-button danger" title="移入回收站" aria-label="移入回收站" disabled={busy || retry || uploading} onClick={onDelete}><Trash2 size={15}/></button><button className="text-button" disabled={busy || retry || uploading} onClick={onSkip}><SkipForward size={15}/>暂时跳过</button></div></div><div className="review-question"><span className="eyebrow">TAKE A MOMENT TO RECALL</span><h1>{item.title}</h1><Content text={item.question} media={item.question_media}/></div>
    {!revealed && <div className="recall-hint"><span className="hint-dot"/><p>{item.subject === 'english' ? '试着独立回忆，再翻开答案。' : '可以在纸上完成，也可以在这里记录思路。'}</p></div>}
    <div className="my-answer"><button className="text-button" disabled={busy || retry || uploading} onClick={() => setAnswerOpen(!answerOpen)}>{answerOpen ? <X size={15}/> : <PlusIcon/>}{answerOpen ? '收起我的解答' : '记录我的解答 / 上传解题照片'}<span>选填</span></button>{answerOpen && <ContentField label="我的解答" maxFiles={8} maxLength={30000} disabled={busy || retry} onUploadingChange={setUploading} text={answer} media={media} onText={setAnswer} onMedia={setMedia} placeholder="写下思考过程，或者上传纸上的解答。" rows={3}/>}</div>
    {revealed && <div className="revealed-answer">{detail.isPending ? <Loading text="展开参考答案…"/> : detail.error ? <ErrorState error={detail.error} retry={() => void detail.refetch()}/> : <><div className="answer-divider"><span><Check size={15}/>参考答案</span></div><Content text={detail.data.answer} media={detail.data.answer_media}/>{detail.data.takeaway && <div className="review-takeaway"><Leaf size={18}/><div><strong>上次留给自己的提醒</strong><Content text={detail.data.takeaway}/></div></div>}</>}</div>}
    {revealed && isProblem && <fieldset className="problem-feedback" disabled={busy || retry || uploading || conflict || !detail.data}>
      <legend>这次是否独立完成？</legend>
      {throughputQuery.data?.first && <p className="throughput-history">第一次贯通率 <b>{percent(throughputQuery.data.first.throughput)}</b>{throughputQuery.data.attempts > 1 && <> · 上次 <b>{percent(throughputQuery.data.latest?.throughput)}</b></>}<span>已记录 {throughputQuery.data.attempts} 次</span></p>}
      <p className="field-help">以翻开答案前的尝试为准，需要提示或答案才完成，也算未独立完成。</p>
      <div className="feedback-choices">
        <label className={independentCompleted === true ? 'selected' : ''}><input type="radio" name="independent-completed" checked={independentCompleted === true} onChange={() => setIndependentCompleted(true)}/>已独立完成</label>
        <label className={independentCompleted === false ? 'selected' : ''}><input type="radio" name="independent-completed" checked={independentCompleted === false} onChange={() => setIndependentCompleted(false)}/>未独立完成</label>
      </div>
      {independentCompleted === true && <div className="throughput-steps">
        <div className="throughput-head"><span>这次的贯通率</span><strong>{percent(rate)}</strong><small>{steps.length ? `${steps.length} / ${steps.length} 步` : '把做题步骤记下来，之后复盘可以对照'}</small></div>
        {previous ? <>
          <ul className="step-checklist">{previous.map((step, index) => <li key={index} className="done"><label><input type="checkbox" checked disabled/>{step.text}{!step.done && <em>这次做出来了</em>}</label></li>)}</ul>
          <label className="field" htmlFor="steps-extra">补充的步骤（选填，一行一步）</label>
          <textarea id="steps-extra" rows={2} value={doneText} onChange={e => setDoneText(e.target.value)} placeholder="这次多走了哪一步？写在这里。"/>
        </> : <>
          <label className="field" htmlFor="steps-done-all">我做出来的步骤（选填，一行一步）</label>
          <textarea id="steps-done-all" rows={3} value={doneText} onChange={e => setDoneText(e.target.value)} placeholder={'统一单位\n求出组数\n算标记位'}/>
        </>}
        {!stepsValid && <p className="field-help">最多记录 30 步，请合并一些步骤。</p>}
      </div>}
      {independentCompleted === false && <div className="throughput-steps">
        <div className="throughput-head"><span>这次的贯通率</span><strong>{percent(rate)}</strong><small>{steps.length ? `${steps.length - missedSteps} / ${steps.length} 步` : '按步骤拆开，先收下做出来的部分'}</small></div>
        {previous ? <>
          <p className="field-help">上次的步骤都在这里，这次做出来的打个钩。</p>
          <ul className="step-checklist">{previous.map((step, index) => { const done = ticks[index] ?? step.done; return <li key={index} className={done ? 'done' : ''}><label><input type="checkbox" checked={done} onChange={e => setTicks(t => ({ ...t, [index]: e.target.checked }))}/>{step.text}{!step.done && done && <em>这次做出来了</em>}</label></li> })}</ul>
          <label className="field" htmlFor="steps-new-miss">新发现的卡住步骤（选填，一行一个）</label>
          <textarea id="steps-new-miss" rows={2} value={missText} onChange={e => setMissText(e.target.value)} placeholder="这次又卡在了别的地方？写在这里。"/>
        </> : <>
          <label className="field" htmlFor="steps-done">我做出来的（一行一步）</label>
          <textarea id="steps-done" rows={3} value={doneText} onChange={e => setDoneText(e.target.value)} placeholder={'统一单位\n求出组数'}/>
          <label className="field" htmlFor="steps-miss">我没做出来的（一行一步）</label>
          <textarea id="steps-miss" rows={2} value={missText} onChange={e => setMissText(e.target.value)} placeholder="算标记位"/>
        </>}
        {!stepsValid && <p className="field-help">最多记录 30 步，请合并一些步骤。</p>}
      </div>}
      {independentCompleted === false && <div className="feedback-blocker">
        <label className="field" htmlFor="review-blocker">主要卡点{missedSteps > 0 && <small>（选填，留空就用没做出来的步骤）</small>}</label>
        <textarea id="review-blocker" rows={3} maxLength={2000} required={!missedSteps} value={blocker} aria-describedby="blocker-help" onChange={e => setBlocker(e.target.value)} placeholder="是哪一个概念、条件或步骤卡住了？先记下最主要的一点。"/>
        <p id="blocker-help" className="field-help">{!blocker.trim() && !missedSteps ? '先写下主要卡点或没做出来的步骤，再选「忘记」。' : '这次选「忘记」。卡点会保存在历史中，之后可按需提炼小任务。'}<span>{blocker.length} / 2000</span></p>
      </div>}
    </fieldset>}
    <ReviewActions active={active}>{!revealed ? <>
      <button className="button primary reveal-button" onClick={() => setRevealed(true)}><Eye size={18}/>查看答案<span>空格</span></button><p>先独立尝试，再给这次回忆一个真实的评价。</p>
    </> : <>
      <div className="rating-prompt"><h3>给这次回忆一个真实的评价</h3><p>{!isProblem ? '需要提示或答案才能完成，请选「忘记」。' : independentCompleted === null ? '请先选择这次是否独立完成。' : independentCompleted ? '已独立完成，请按费力程度选择「困难 / 良好 / 轻松」。' : '未独立完成，记下步骤或卡点后选择「忘记」。'}</p></div>
      {preview.error && <ErrorState error={preview.error} retry={() => void preview.refetch()}/>}
      <div className="rating-buttons">{ratingOptions.map(r => <button key={r.id} className={`rating-button ${r.id}`} disabled={busy || uploading || !detail.data || !preview.data || retry || conflict || !feedbackAllows(r.id)} onClick={() => void submit(r.id)}><div><strong>{r.label}</strong><kbd>{r.shortcut}</kbd></div><span>{r.note}</span><small>{preview.data ? preview.data.ratings[r.id].next_day ? '明天' : intervalLabel(preview.data.ratings[r.id].interval_seconds) : '计算中…'}</small></button>)}</div>
      {(preview.data?.ratings.again.next_day || preview.data?.ratings.hard.next_day) && <p className="next-day-help">只有「忘记 / 困难」的短间隔移到明天；「良好」仍可能在 10 分钟后复习。</p>}
      {conflict && <div className="retry-review"><p>这条知识的内容或复习状态已变化，请重新加载后继续。</p><button className="button secondary" onClick={() => void onConflict()}>重新加载这条知识</button></div>}
      {uploading && <p role="status">解答照片上传中，完成后即可评分。</p>}
      {retry && <div className="retry-review"><p>未能确认保存结果。请重试这次提交，系统会避免重复记分。</p><button className="button primary" disabled={busy} onClick={() => void submit(pending.current?.rating as Rating)}>{busy ? <Spinner/> : <RotateCcw size={16}/>}重试保存</button></div>}
      {busy && <div className="review-saving"><Spinner/>正在保存这次回忆…</div>}
    </>}</ReviewActions>
  </section>
}
function PlusIcon() { return <span style={{ fontSize: 20, lineHeight: 1 }}>+</span> }

function ReviewActions({ active, children }: { active: boolean; children: ReactNode }) {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 700px)').matches)
  const dock = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const media = window.matchMedia('(max-width: 700px)')
    const update = () => setMobile(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    const element = dock.current
    if (!mobile || !active || !element) return
    const update = () => document.body.style.setProperty('--review-dock-height', `${element.getBoundingClientRect().height}px`)
    const observer = new ResizeObserver(update)
    observer.observe(element); update()
    return () => { observer.disconnect(); document.body.style.removeProperty('--review-dock-height') }
  }, [mobile, active])
  const controls = <div ref={dock} className={`review-rating-area ${mobile ? 'review-dock' : ''}`} role="region" aria-label="复习操作">{children}</div>
  return mobile ? active ? createPortal(controls, document.body) : null : controls
}
