import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronRight, Filter, Grid2X2, Image, List, Plus, RotateCcw, Search, SquarePen, Trash2 } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, post, refreshLearning } from '../api'
import { dateLabel, difficultyNames, kindNames, plainText, relativeDue, subjects } from '../lib'
import type { Chapter, ItemPage, Subject } from '../types'
import { useEditor } from '../components/Editor'
import { Empty, ErrorState, Loading, PageHeading } from '../components/ui'

export default function Library({ mistakes = false }: { mistakes?: boolean }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const [input, setInput] = useState(params.get('q') ?? '')
  const [view, setView] = useState<'grid' | 'list'>(mistakes ? 'grid' : 'list')
  const [filters, setFilters] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const edit = useEditor()
  const subject = params.get('subject') ?? ''
  const page = Number(params.get('page') ?? 1)
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.delete('page'); setParams(next, { replace: true }); setSelected([]) }
  const queryText = params.get('q') ?? ''
  useEffect(() => { setInput(queryText) }, [queryText])
  useEffect(() => { setSelected([]) }, [params, mistakes])
  useEffect(() => {
    const timer = setTimeout(() => {
      if (queryText !== input) {
        const next = new URLSearchParams(params)
        if (input) next.set('q', input); else next.delete('q')
        next.delete('page')
        setParams(next, { replace: true })
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [input, queryText, params, setParams])
  const request = new URLSearchParams(params); request.set('page_size', '12'); if (mistakes) request.set('is_mistake', 'true')
  const query = useQuery({ queryKey: ['items', request.toString()], queryFn: () => api<ItemPage>(`/items?${request}`) })
  const chapters = useQuery({ queryKey: ['chapters'], queryFn: () => api<Chapter[]>('/chapters') })
  const deleted = params.get('status') === 'deleted'
  const batch = async () => {
    if (!window.confirm(`将选中的 ${selected.length} 条内容移入回收站？复习记录会保留。`)) return
    setBusy(true)
    try { for (const id of selected) await api(`/items/${id}`, { method: 'DELETE' }); setSelected([]); refreshLearning(); toast.success('已移入回收站') }
    catch (e) { toast.error((e as Error).message); refreshLearning() } finally { setBusy(false) }
  }
  return <div className="library-page page-enter"><PageHeading eyebrow={mistakes ? 'EVERY MISTAKE, A NEW POSSIBILITY' : 'YOUR GROWING KNOWLEDGE'} title={mistakes ? '把错过的，变成会的。' : '知识，在这里生根。'} description={mistakes ? '不只记下答案，也记下下一次如何想清楚。' : '一条知识，一次积累。慢慢建立属于你的理解。'} actions={<button className="button primary" onClick={() => edit({ subject: subject as Subject || undefined, mistake: mistakes })}><Plus size={17}/>{mistakes ? '收录错题' : '记录新知'}</button>}/>
    <div className="library-toolbar panel"><div className="library-primary-filters"><div className="subject-tabs"><button className={!subject ? 'active' : ''} onClick={() => { const next = new URLSearchParams(params); next.delete('subject'); next.delete('chapter_id'); next.delete('page'); setParams(next) }}>全部科目</button>{subjects.map(s => <button key={s.id} className={subject === s.id ? 'active' : ''} onClick={() => { const next = new URLSearchParams(params); next.set('subject', s.id); next.delete('chapter_id'); next.delete('page'); setParams(next) }}><span className={`subject-dot ${s.color}`}/>{s.name}</button>)}</div><div className="view-toggle"><button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')} aria-label="列表视图"><List size={17}/></button><button className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')} aria-label="卡片视图"><Grid2X2 size={16}/></button></div></div>
      <div className="library-search-row"><div className="search-input"><Search size={18}/><input value={input} onChange={e => setInput(e.target.value)} placeholder={mistakes ? '搜索题目、错因或标签…' : '寻找一条知识…'} aria-label="搜索知识库"/>{input && <button className="text-button" onClick={() => setInput('')}>清空</button>}</div><select aria-label="排序" value={params.get('sort') ?? 'updated'} onChange={e => update('sort', e.target.value)}><option value="updated">最近更新</option><option value="created">最近收录</option><option value="due">复习时间</option><option value="title">标题顺序</option></select><button className={`button secondary filter-button ${filters ? 'selected' : ''}`} onClick={() => setFilters(!filters)}><Filter size={16}/>筛选</button></div>
      {filters && <div className="filter-row"><label>章节<select value={params.get('chapter_id') ?? ''} onChange={e => update('chapter_id', e.target.value)}><option value="">全部章节</option>{chapters.data?.filter(c => !subject || c.subject === subject).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>内容状态<select value={params.get('status') ?? 'all'} onChange={e => update('status', e.target.value)}><option value="all">全部内容</option><option value="active">已加入复习</option><option value="draft">草稿</option><option value="suspended">暂停复习</option><option value="deleted">回收站</option></select></label><label>题目难度<select value={params.get('difficulty') ?? ''} onChange={e => update('difficulty', e.target.value)}><option value="">全部难度</option>{Object.entries(difficultyNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>内容类型<select value={params.get('kind') ?? ''} onChange={e => update('kind', e.target.value)}><option value="">全部类型</option>{Object.entries(kindNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>学习状态<select value={params.get('state') ?? ''} onChange={e => update('state', e.target.value)}><option value="">全部状态</option><option value="due">到期复习</option><option value="new">待学习</option><option value="review">复习中</option><option value="learning">学习中</option><option value="relearning">重新学习</option></select></label><button className="text-button" onClick={() => { setParams(subject ? { subject } : {}); setInput('') }}>重置筛选</button></div>}
    </div>
    <div className="results-heading"><span>{deleted ? '回收站' : '共收录'} <strong>{query.data?.total ?? '—'}</strong> 条{mistakes ? '错题' : '知识'}</span>{selected.length > 0 ? <div className="selection-actions"><span>已选 {selected.length} 条</span><button className="text-button danger" disabled={busy} onClick={() => void batch()}><Trash2 size={14}/>移入回收站</button><button className="text-button" onClick={() => setSelected([])}>取消选择</button></div> : <span className="muted">{deleted ? '恢复后将保留原来的学习进度' : '每一条，都是未来的底气'}</span>}</div>
    {query.isPending ? <Loading/> : query.error ? <ErrorState error={query.error} retry={() => void query.refetch()}/> : !query.data.items.length ? <div className="panel"><Empty title={input || params.size ? '这个角落，暂时还是空的' : mistakes ? '让每一道错题，都有收获' : '你的知识花园，等待第一颗种子'} description={input || params.size ? '试试其他关键词，或者放宽筛选条件。' : mistakes ? '粘贴题目截图，写下错因。下次再遇见时，你会更有把握。' : '记录一个知识点、一条单词，或者一个值得反复思考的问题。'} icon={mistakes ? <SquarePen size={32} strokeWidth={1.3}/> : <BookOpen size={32} strokeWidth={1.3}/>} action={<button className="button primary" onClick={() => edit({ subject: subject as Subject || undefined, mistake: mistakes })}><Plus size={17}/>{mistakes ? '收录第一道错题' : '记录一条新知'}</button>}/></div> : <>
      <div className={`knowledge-items ${view}`}>{query.data.items.map(item => { const s = subjects.find(s => s.id === item.subject)!; return <article className={`knowledge-card ${view}`} key={item.id}>
        {!deleted && <label className="card-select" title="选择这条内容"><input type="checkbox" aria-label={`选择 ${item.title}`} checked={selected.includes(item.id)} onChange={e => setSelected(ids => e.target.checked ? [...ids, item.id] : ids.filter(id => id !== item.id))}/><span><Check size={12}/></span></label>}
        <Link to={`/items/${item.id}`} state={{ returnTo: location.pathname + location.search }} className="knowledge-card-link">
          {view === 'grid' && <div className={`knowledge-visual ${s.color}`}>{item.question_media.length ? <><img src={item.question_media[0].url} alt={`${item.title}题图`} loading="lazy"/><span className="image-count"><Image size={13}/>{item.question_media.length}</span></> : <><span className="visual-symbol">{s.symbol}</span><span className="visual-preview">{plainText(item.question) || '先留一个位置，等灵感到来'}</span></>}</div>}
          {view === 'list' && <div className={`list-subject-symbol ${s.color}`}>{item.question_media.length ? <img src={item.question_media[0].url} alt="题目缩略图"/> : s.symbol}</div>}
          <div className="knowledge-card-content"><div className="card-meta"><span className={`subject-badge ${s.color}`}>{s.name}</span><span>{chapters.data?.find(c => c.id === item.chapter_id)?.name ?? '未分章节'}</span>{item.is_mistake && <span className="mistake-badge">错题</span>}</div><h3>{item.title}</h3><p>{plainText(item.question) || '题目以图片形式保存'}</p><div className="card-tags">{item.tags.slice(0, 3).map(t => <span key={t}>#{t}</span>)}<span className="difficulty-tag">{difficultyNames[item.difficulty]}</span></div></div>
          <div className="knowledge-card-footer"><span className={`due-tag ${item.schedule.last_review && new Date(item.schedule.due).getTime() <= Date.now() ? 'is-due' : ''}`}>{item.status === 'draft' ? '等待补充 · 草稿' : item.status === 'suspended' ? '已暂停复习' : item.status === 'deleted' ? '已移入回收站' : relativeDue(item.schedule.due, item.schedule.state === 'new')}</span><span className="card-date">{dateLabel(item.updated_at)}</span><ChevronRight size={16}/></div>
        </Link>{deleted && <button className="button secondary restore-button" onClick={async () => { try { await post(`/items/${item.id}/restore`); refreshLearning(); toast.success('已恢复内容与学习进度') } catch (e) { toast.error((e as Error).message) } }}><RotateCcw size={15}/>恢复</button>}
      </article> })}</div>
      {query.data.total > 12 && <div className="pagination"><button className="button secondary" disabled={page <= 1} onClick={() => update('page', String(page - 1))}><ArrowLeft size={16}/>上一页</button><span>第 {page} / {Math.ceil(query.data.total / 12)} 页</span><button className="button secondary" disabled={page * 12 >= query.data.total} onClick={() => update('page', String(page + 1))}>下一页<ArrowRight size={16}/></button></div>}
    </>}
  </div>
}
